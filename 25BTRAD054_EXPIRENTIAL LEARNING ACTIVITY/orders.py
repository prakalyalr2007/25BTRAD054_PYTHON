from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app, g
from database import query_db, execute_db, get_db
from auth import login_required

orders_bp = Blueprint('orders', __name__)


def generate_unique_token():
    """Generate a clean, high-visibility sequential token number like #T101, #T102."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    # Count orders created today
    count_row = query_db(
        "SELECT COUNT(*) as count FROM orders WHERE date(created_at) = date('now', 'localtime')",
        one=True
    )
    daily_count = (count_row['count'] if count_row else 0) + 1
    
    # Prefix T with 3 digit zero-padded daily sequence, e.g. #T101, #T102
    token = f"#T{100 + daily_count}"
    
    # Ensure absolute uniqueness across the database
    exists = query_db('SELECT id FROM orders WHERE token = ?', (token,), one=True)
    counter = 1
    while exists:
        token = f"#T{100 + daily_count}_{counter}"
        exists = query_db('SELECT id FROM orders WHERE token = ?', (token,), one=True)
        counter += 1
        
    return token


def calculate_estimated_wait_time(items_count=1):
    """Calculate estimated preparation and wait time based on queue depth."""
    # Count active orders in Received or Preparing stage
    active_row = query_db(
        "SELECT COUNT(*) as count FROM orders WHERE status IN ('Received', 'Preparing')",
        one=True
    )
    active_count = active_row['count'] if active_row else 0

    base_time = current_app.config.get('BASE_PREP_MINUTES', 10)
    queue_offset = current_app.config.get('MINS_PER_ACTIVE_ORDER', 3) * active_count
    item_offset = max(1, items_count) * 1  # 1 min per item

    return int(base_time + queue_offset + item_offset)


def get_cart_details():
    """Retrieve full item models and calculate subtotal, GST (5%), and total for current cart."""
    cart = session.get('cart', {})
    cart_items = []
    subtotal = 0.0

    if cart:
        item_ids = [int(k) for k in cart.keys() if str(k).isdigit()]
        if item_ids:
            placeholders = ','.join(['?'] * len(item_ids))
            items = query_db(f'SELECT * FROM menu_items WHERE id IN ({placeholders})', item_ids)
            item_map = {item['id']: item for item in items}

            for item_id_str, qty in cart.items():
                item_id = int(item_id_str)
                if item_id in item_map:
                    item = item_map[item_id]
                    item_qty = int(qty)
                    line_subtotal = round(item['price'] * item_qty, 2)
                    subtotal += line_subtotal
                    cart_items.append({
                        'id': item['id'],
                        'name': item['name'],
                        'category': item['category'],
                        'price': item['price'],
                        'is_veg': item['is_veg'],
                        'is_available': item['is_available'],
                        'image_emoji': item['image_emoji'],
                        'quantity': item_qty,
                        'subtotal': line_subtotal
                    })

    tax_rate = current_app.config.get('TAX_RATE', 0.05)
    tax = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax, 2)

    return {
        'cart_items': cart_items,
        'subtotal': round(subtotal, 2),
        'tax': tax,
        'tax_rate_percent': int(tax_rate * 100),
        'total': total,
        'item_count': sum(item['quantity'] for item in cart_items)
    }


@orders_bp.route('/cart')
def view_cart():
    """Display student's current cart and checkout summary."""
    cart_data = get_cart_details()
    return render_template('student/cart.html', **cart_data)


@orders_bp.route('/cart/add', methods=['POST'])
def add_to_cart():
    """Add a menu item to the session cart."""
    try:
        item_id = int(request.form.get('item_id', 0))
        quantity = int(request.form.get('quantity', 1))
    except ValueError:
        flash('Invalid item or quantity.', 'danger')
        return redirect(request.referrer or url_for('menu.browse_menu'))

    if quantity <= 0:
        flash('Quantity must be at least 1.', 'warning')
        return redirect(request.referrer or url_for('menu.browse_menu'))

    # Check if item exists and is available
    item = query_db('SELECT id, name, is_available FROM menu_items WHERE id = ?', (item_id,), one=True)
    if not item:
        flash('Item not found.', 'danger')
        return redirect(request.referrer or url_for('menu.browse_menu'))

    if not item['is_available']:
        flash(f'Sorry, "{item["name"]}" is currently sold out.', 'warning')
        return redirect(request.referrer or url_for('menu.browse_menu'))

    if 'cart' not in session or not isinstance(session['cart'], dict):
        session['cart'] = {}

    cart = session['cart']
    current_qty = cart.get(str(item_id), 0)
    cart[str(item_id)] = current_qty + quantity
    session.modified = True

    flash(f'Added {quantity}x "{item["name"]}" to your cart.', 'success')
    return redirect(request.referrer or url_for('menu.browse_menu'))


@orders_bp.route('/cart/update', methods=['POST'])
def update_cart():
    """Update item quantity or remove if set to 0."""
    try:
        item_id = str(int(request.form.get('item_id', 0)))
        quantity = int(request.form.get('quantity', 0))
    except ValueError:
        flash('Invalid request parameters.', 'danger')
        return redirect(url_for('orders.view_cart'))

    cart = session.get('cart', {})
    if item_id in cart:
        if quantity > 0:
            cart[item_id] = quantity
            flash('Cart quantity updated.', 'info')
        else:
            del cart[item_id]
            flash('Item removed from cart.', 'info')
        session['cart'] = cart
        session.modified = True

    return redirect(url_for('orders.view_cart'))


@orders_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    """Remove a specific item from the cart."""
    cart = session.get('cart', {})
    item_key = str(item_id)
    if item_key in cart:
        del cart[item_key]
        session['cart'] = cart
        session.modified = True
        flash('Item removed from cart.', 'info')
    return redirect(url_for('orders.view_cart'))


@orders_bp.route('/cart/clear', methods=['POST'])
def clear_cart():
    """Clear all items from current cart."""
    session['cart'] = {}
    session.modified = True
    flash('Your cart has been cleared.', 'info')
    return redirect(url_for('orders.view_cart'))


@orders_bp.route('/order/checkout', methods=['POST'])
@login_required
def checkout():
    """Process order placement, allocate unique token, and set estimated wait time."""
    cart_data = get_cart_details()
    cart_items = cart_data['cart_items']

    if not cart_items:
        flash('Your cart is empty. Please add items before checking out.', 'warning')
        return redirect(url_for('menu.browse_menu'))

    # Verify no sold out items are in the cart
    for item in cart_items:
        if not item['is_available']:
            flash(f'Item "{item["name"]}" is currently sold out. Please remove it from your cart.', 'danger')
            return redirect(url_for('orders.view_cart'))

    special_instructions = request.form.get('special_instructions', '').strip()
    user_id = session['user_id']
    token = generate_unique_token()
    wait_time = calculate_estimated_wait_time(cart_data['item_count'])

    db = get_db()
    cursor = db.cursor()

    try:
        # Create order
        cursor.execute(
            '''INSERT INTO orders (user_id, token, subtotal, tax, total, status, estimated_wait_minutes, special_instructions)
               VALUES (?, ?, ?, ?, ?, 'Received', ?, ?)''',
            (user_id, token, cart_data['subtotal'], cart_data['tax'], cart_data['total'], wait_time, special_instructions)
        )
        order_id = cursor.lastrowid

        # Insert order items
        order_items_data = [
            (order_id, item['id'], item['name'], item['price'], item['quantity'], item['subtotal'])
            for item in cart_items
        ]
        cursor.executemany(
            '''INSERT INTO order_items (order_id, menu_item_id, item_name, price, quantity, subtotal)
               VALUES (?, ?, ?, ?, ?, ?)''',
            order_items_data
        )

        db.commit()

        # Clear session cart
        session['cart'] = {}
        session.modified = True

        flash(f'Order placed successfully! Your Token is {token}.', 'success')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    except Exception as e:
        db.rollback()
        flash(f'An error occurred while placing your order: {str(e)}', 'danger')
        return redirect(url_for('orders.view_cart'))


@orders_bp.route('/orders')
@login_required
def order_history():
    """List customer's past and current orders."""
    user_id = session['user_id']
    # If staff/admin visits orders page, show all orders or their orders
    if session.get('role') in ['staff', 'admin']:
        orders = query_db(
            '''SELECT o.*, u.name as customer_name, u.email as customer_email,
                      (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
               FROM orders o
               JOIN users u ON o.user_id = u.id
               ORDER BY o.created_at DESC'''
        )
    else:
        orders = query_db(
            '''SELECT o.*,
                      (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
               FROM orders o
               WHERE o.user_id = ?
               ORDER BY 
                 CASE 
                   WHEN o.status IN ('Received', 'Preparing', 'Ready') THEN 0 
                   ELSE 1 
                 END,
                 o.created_at DESC''',
            (user_id,)
        )

    return render_template('student/order_history.html', orders=orders)


@orders_bp.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    """View detailed order status with token ticket styling."""
    user_id = session['user_id']
    user_role = session.get('role')

    order = query_db(
        '''SELECT o.*, u.name as customer_name, u.email as customer_email, u.username
           FROM orders o
           JOIN users u ON o.user_id = u.id
           WHERE o.id = ?''',
        (order_id,),
        one=True
    )

    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('orders.order_history'))

    # Ensure ownership or staff/admin access
    if user_role == 'student' and order['user_id'] != user_id:
        flash('You are not authorized to view this order.', 'danger')
        return redirect(url_for('orders.order_history'))

    items = query_db(
        '''SELECT oi.*, mi.image_emoji, mi.is_veg
           FROM order_items oi
           LEFT JOIN menu_items mi ON oi.menu_item_id = mi.id
           WHERE oi.order_id = ?''',
        (order_id,)
    )

    return render_template('student/order_detail.html', order=order, items=items)


@orders_bp.route('/api/order/<int:order_id>/status')
@login_required
def api_order_status(order_id):
    """API endpoint for live polling the order status without full page reload."""
    user_id = session['user_id']
    user_role = session.get('role')

    order = query_db(
        'SELECT id, token, status, estimated_wait_minutes, user_id, updated_at FROM orders WHERE id = ?',
        (order_id,),
        one=True
    )

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if user_role == 'student' and order['user_id'] != user_id:
        return jsonify({'error': 'Unauthorized'}), 403

    return jsonify({
        'id': order['id'],
        'token': order['token'],
        'status': order['status'],
        'estimated_wait_minutes': order['estimated_wait_minutes'],
        'can_cancel': (order['status'] == 'Received'),
        'updated_at': str(order['updated_at'])
    })


@orders_bp.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    """Cancel an order only if it is still in the 'Received' stage."""
    user_id = session['user_id']
    user_role = session.get('role')

    order = query_db('SELECT id, user_id, status, token FROM orders WHERE id = ?', (order_id,), one=True)
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('orders.order_history'))

    # Check ownership unless staff/admin
    if user_role == 'student' and order['user_id'] != user_id:
        flash('You are not authorized to cancel this order.', 'danger')
        return redirect(url_for('orders.order_history'))

    # Strictly check status
    if order['status'] != 'Received':
        flash(f'Order {order["token"]} cannot be cancelled because it is already "{order["status"]}".', 'warning')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    execute_db(
        "UPDATE orders SET status = 'Cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (order_id,)
    )
    flash(f'Order {order["token"]} has been successfully cancelled.', 'info')
    return redirect(url_for('orders.order_detail', order_id=order_id))
