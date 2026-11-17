from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from database import query_db, execute_db
from auth import login_required, staff_required

queue_bp = Blueprint('queue', __name__)

NEXT_STAGE_MAP = {
    'Received': 'Preparing',
    'Preparing': 'Ready',
    'Ready': 'Collected'
}


@queue_bp.route('/staff/queue')
@login_required
@staff_required
def staff_queue():
    """Live order management queue sorted by time (earliest first)."""
    filter_status = request.args.get('status', 'active').strip()

    # Query active or specific status orders
    if filter_status == 'active':
        orders = query_db(
            '''SELECT o.*, u.name as customer_name, u.email as customer_email,
                      (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
               FROM orders o
               JOIN users u ON o.user_id = u.id
               WHERE o.status IN ('Received', 'Preparing', 'Ready')
               ORDER BY 
                 CASE o.status
                   WHEN 'Received' THEN 1
                   WHEN 'Preparing' THEN 2
                   WHEN 'Ready' THEN 3
                 END,
                 o.created_at ASC'''
        )
    elif filter_status == 'completed':
        orders = query_db(
            '''SELECT o.*, u.name as customer_name, u.email as customer_email,
                      (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
               FROM orders o
               JOIN users u ON o.user_id = u.id
               WHERE o.status IN ('Collected', 'Cancelled')
               ORDER BY o.updated_at DESC
               LIMIT 50'''
        )
    else:
        orders = query_db(
            '''SELECT o.*, u.name as customer_name, u.email as customer_email,
                      (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
               FROM orders o
               JOIN users u ON o.user_id = u.id
               WHERE o.status = ?
               ORDER BY o.created_at ASC''',
            (filter_status,)
        )

    # Fetch order items for each order in the queue
    order_list = []
    for order in orders:
        items = query_db(
            '''SELECT item_name, price, quantity, subtotal
               FROM order_items
               WHERE order_id = ?''',
            (order['id'],)
        )
        order_dict = dict(order)
        order_dict['order_items'] = items
        order_dict['next_status'] = NEXT_STAGE_MAP.get(order['status'])
        order_list.append(order_dict)

    # Get menu items for stock toggle management
    menu_items = query_db('SELECT id, name, category, price, is_veg, is_available FROM menu_items ORDER BY category, name')

    # Status counts for header metrics
    counts = {
        'received': query_db("SELECT COUNT(*) as c FROM orders WHERE status = 'Received'", one=True)['c'],
        'preparing': query_db("SELECT COUNT(*) as c FROM orders WHERE status = 'Preparing'", one=True)['c'],
        'ready': query_db("SELECT COUNT(*) as c FROM orders WHERE status = 'Ready'", one=True)['c'],
        'collected': query_db("SELECT COUNT(*) as c FROM orders WHERE status = 'Collected'", one=True)['c'],
    }
    counts['total_active'] = counts['received'] + counts['preparing'] + counts['ready']

    return render_template(
        'staff/queue.html',
        orders=order_list,
        menu_items=menu_items,
        filter_status=filter_status,
        counts=counts
    )


@queue_bp.route('/staff/order/<int:order_id>/advance', methods=['POST'])
@login_required
@staff_required
def advance_order(order_id):
    """Advance an order to its next logical stage (Received -> Preparing -> Ready -> Collected)."""
    order = query_db('SELECT id, token, status FROM orders WHERE id = ?', (order_id,), one=True)
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('queue.staff_queue'))

    current_status = order['status']
    next_status = NEXT_STAGE_MAP.get(current_status)

    if not next_status:
        flash(f'Order {order["token"]} is currently "{current_status}" and cannot be advanced further.', 'warning')
        return redirect(url_for('queue.staff_queue'))

    execute_db(
        'UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (next_status, order_id)
    )
    flash(f'Order {order["token"]} updated to "{next_status}".', 'success')
    return redirect(request.referrer or url_for('queue.staff_queue'))


@queue_bp.route('/staff/order/<int:order_id>/status', methods=['POST'])
@login_required
@staff_required
def set_order_status(order_id):
    """Explicitly change the order status (e.g., mark Cancelled or Collected)."""
    new_status = request.form.get('status', '').strip()
    if new_status not in ['Received', 'Preparing', 'Ready', 'Collected', 'Cancelled']:
        flash('Invalid status provided.', 'danger')
        return redirect(url_for('queue.staff_queue'))

    order = query_db('SELECT token FROM orders WHERE id = ?', (order_id,), one=True)
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('queue.staff_queue'))

    execute_db(
        'UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (new_status, order_id)
    )
    flash(f'Order {order["token"]} marked as "{new_status}".', 'info')
    return redirect(request.referrer or url_for('queue.staff_queue'))


@queue_bp.route('/staff/menu/<int:item_id>/toggle-stock', methods=['POST'])
@login_required
@staff_required
def toggle_item_stock(item_id):
    """Toggle menu item between Available (1) and Sold Out (0)."""
    item = query_db('SELECT id, name, is_available FROM menu_items WHERE id = ?', (item_id,), one=True)
    if not item:
        flash('Menu item not found.', 'danger')
        return redirect(url_for('queue.staff_queue'))

    new_stock = 0 if item['is_available'] == 1 else 1
    execute_db('UPDATE menu_items SET is_available = ? WHERE id = ?', (new_stock, item_id))

    status_str = "Available" if new_stock == 1 else "Sold Out"
    flash(f'"{item["name"]}" is now marked as {status_str}.', 'success')
    return redirect(request.referrer or url_for('queue.staff_queue'))


@queue_bp.route('/api/staff/queue-data')
@login_required
@staff_required
def api_queue_data():
    """Live API endpoint for polling the active queue without full page refresh."""
    orders = query_db(
        '''SELECT o.id, o.token, o.status, o.total, o.estimated_wait_minutes, o.created_at,
                  u.name as customer_name
           FROM orders o
           JOIN users u ON o.user_id = u.id
           WHERE o.status IN ('Received', 'Preparing', 'Ready')
           ORDER BY 
             CASE o.status
               WHEN 'Received' THEN 1
               WHEN 'Preparing' THEN 2
               WHEN 'Ready' THEN 3
             END,
             o.created_at ASC'''
    )
    return jsonify([{
        'id': o['id'],
        'token': o['token'],
        'status': o['status'],
        'total': o['total'],
        'wait_minutes': o['estimated_wait_minutes'],
        'created_at': str(o['created_at']),
        'customer_name': o['customer_name'],
        'next_status': NEXT_STAGE_MAP.get(o['status'])
    } for o in orders])
