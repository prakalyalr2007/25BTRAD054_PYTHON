import csv
import io
from datetime import datetime
from flask import Blueprint, render_template, make_response, jsonify, current_app
from database import query_db
from auth import login_required, admin_required

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/admin/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard featuring live KPIs, top selling dishes, and hourly trends."""
    # Today's orders count and revenue
    today_stats = query_db(
        '''SELECT COUNT(*) as total_orders,
                  COALESCE(SUM(total), 0) as total_revenue,
                  COALESCE(SUM(subtotal), 0) as subtotal_revenue,
                  COALESCE(SUM(tax), 0) as total_tax
           FROM orders
           WHERE date(created_at) = date('now', 'localtime')
             AND status != 'Cancelled' ''',
        one=True
    )

    # All-time stats
    all_time_stats = query_db(
        '''SELECT COUNT(*) as total_orders,
                  COALESCE(SUM(total), 0) as total_revenue
           FROM orders
           WHERE status != 'Cancelled' ''',
        one=True
    )

    # Live queue count
    live_queue_count = query_db(
        "SELECT COUNT(*) as count FROM orders WHERE status IN ('Received', 'Preparing', 'Ready')",
        one=True
    )['count']

    # Top 5 selling dishes (by total quantity sold)
    top_dishes = query_db(
        '''SELECT oi.item_name,
                  SUM(oi.quantity) as total_qty,
                  ROUND(SUM(oi.subtotal), 2) as total_sales,
                  mi.category,
                  mi.is_veg,
                  mi.image_emoji
           FROM order_items oi
           JOIN orders o ON oi.order_id = o.id
           LEFT JOIN menu_items mi ON oi.menu_item_id = mi.id
           WHERE o.status != 'Cancelled'
           GROUP BY oi.item_name
           ORDER BY total_qty DESC
           LIMIT 5'''
    )

    # Recent 10 orders for quick preview table
    recent_orders = query_db(
        '''SELECT o.*, u.name as customer_name,
                  (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
           FROM orders o
           JOIN users u ON o.user_id = u.id
           ORDER BY o.created_at DESC
           LIMIT 10'''
    )

    # Category performance
    category_sales = query_db(
        '''SELECT mi.category,
                  COUNT(oi.id) as orders_count,
                  COALESCE(SUM(oi.quantity), 0) as items_sold,
                  ROUND(COALESCE(SUM(oi.subtotal), 0), 2) as total_revenue
           FROM menu_items mi
           LEFT JOIN order_items oi ON mi.id = oi.menu_item_id
           LEFT JOIN orders o ON oi.order_id = o.id AND o.status != 'Cancelled'
           GROUP BY mi.category'''
    )

    return render_template(
        'admin/dashboard.html',
        today_stats=today_stats,
        all_time_stats=all_time_stats,
        live_queue_count=live_queue_count,
        top_dishes=top_dishes,
        recent_orders=recent_orders,
        category_sales=category_sales
    )


@reports_bp.route('/api/reports/chart-data')
@login_required
@admin_required
def chart_data():
    """Provide structured JSON data for Chart.js (orders per hour, top dishes, categories)."""
    # 1. Orders per hour today (08:00 to 20:00 canteen operating hours or full 24h)
    hourly_rows = query_db(
        '''SELECT strftime('%H', created_at) as hour,
                  COUNT(*) as order_count,
                  COALESCE(SUM(total), 0) as revenue
           FROM orders
           WHERE date(created_at) = date('now', 'localtime')
             AND status != 'Cancelled'
           GROUP BY hour
           ORDER BY hour ASC'''
    )

    # Map all operational hours (8 AM to 8 PM)
    hours_labels = [f"{h:02d}:00" for h in range(8, 21)]
    hourly_counts = {f"{h:02d}": 0 for h in range(8, 21)}
    hourly_revenues = {f"{h:02d}": 0.0 for h in range(8, 21)}

    for row in hourly_rows:
        hr = row['hour']
        if hr in hourly_counts:
            hourly_counts[hr] = row['order_count']
            hourly_revenues[hr] = round(row['revenue'], 2)

    # 2. Top 5 selling dishes
    top_dishes_rows = query_db(
        '''SELECT oi.item_name,
                  SUM(oi.quantity) as total_qty,
                  ROUND(SUM(oi.subtotal), 2) as total_sales
           FROM order_items oi
           JOIN orders o ON oi.order_id = o.id
           WHERE o.status != 'Cancelled'
           GROUP BY oi.item_name
           ORDER BY total_qty DESC
           LIMIT 5'''
    )
    dish_labels = [row['item_name'] for row in top_dishes_rows]
    dish_quantities = [row['total_qty'] for row in top_dishes_rows]
    dish_revenues = [row['total_sales'] for row in top_dishes_rows]

    # 3. Category distribution
    cat_rows = query_db(
        '''SELECT mi.category,
                  COALESCE(SUM(oi.quantity), 0) as items_sold
           FROM menu_items mi
           LEFT JOIN order_items oi ON mi.id = oi.menu_item_id
           LEFT JOIN orders o ON oi.order_id = o.id AND o.status != 'Cancelled'
           GROUP BY mi.category'''
    )
    category_labels = [row['category'] for row in cat_rows]
    category_quantities = [row['items_sold'] for row in cat_rows]

    return jsonify({
        'hourly': {
            'labels': hours_labels,
            'orders': [hourly_counts[f"{h:02d}"] for h in range(8, 21)],
            'revenues': [hourly_revenues[f"{h:02d}"] for h in range(8, 21)]
        },
        'top_dishes': {
            'labels': dish_labels,
            'quantities': dish_quantities,
            'revenues': dish_revenues
        },
        'categories': {
            'labels': category_labels,
            'quantities': category_quantities
        }
    })


@reports_bp.route('/admin/reports/export-csv')
@login_required
@admin_required
def export_csv():
    """Generate and stream a CSV sales report containing all orders and ordered items."""
    orders = query_db(
        '''SELECT o.id, o.token, u.name as customer_name, u.email as customer_email,
                  o.status, o.subtotal, o.tax, o.total, o.created_at,
                  (SELECT GROUP_CONCAT(item_name || ' (x' || quantity || ')', '; ')
                   FROM order_items WHERE order_id = o.id) as items_summary
           FROM orders o
           JOIN users u ON o.user_id = u.id
           ORDER BY o.created_at DESC'''
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Header Row
    writer.writerow([
        'Order ID',
        'Token Number',
        'Customer Name',
        'Customer Email',
        'Status',
        'Subtotal (INR)',
        'GST 5% (INR)',
        'Total (INR)',
        'Items Ordered',
        'Order Date & Time'
    ])

    total_subtotal = 0.0
    total_tax = 0.0
    grand_total = 0.0

    for order in orders:
        if order['status'] != 'Cancelled':
            total_subtotal += order['subtotal']
            total_tax += order['tax']
            grand_total += order['total']

        writer.writerow([
            order['id'],
            order['token'],
            order['customer_name'],
            order['customer_email'],
            order['status'],
            f"{order['subtotal']:.2f}",
            f"{order['tax']:.2f}",
            f"{order['total']:.2f}",
            order['items_summary'] or 'None',
            order['created_at']
        ])

    # Summary Row
    writer.writerow([])
    writer.writerow([
        'SUMMARY (Excl. Cancelled)',
        '',
        '',
        '',
        f'{len(orders)} Orders',
        f"{total_subtotal:.2f}",
        f"{total_tax:.2f}",
        f"{grand_total:.2f}",
        '',
        ''
    ])

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"canteen_sales_report_{timestamp}.csv"

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return response
