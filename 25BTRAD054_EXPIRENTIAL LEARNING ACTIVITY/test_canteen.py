import csv
import io
import pytest
from database import query_db


def test_login_and_auth(client, auth):
    """Test 1: Verify login with valid/invalid credentials, session persistence, and logout."""
    # 1. Invalid login attempt
    resp = auth.login('student', 'wrongpassword')
    assert b'Invalid username or password' in resp.data

    # 2. Valid Student login
    resp = auth.login('student', 'student123')
    assert resp.status_code == 200
    assert b'Alex Student' in resp.data

    # 3. Logout
    resp = auth.logout()
    assert b'You have been logged out safely' in resp.data

    # 4. Valid Staff login
    resp = auth.login('staff', 'staff123')
    assert resp.status_code == 200
    assert b'Live Queue' in resp.data
    auth.logout()

    # 5. Valid Admin login
    resp = auth.login('admin', 'admin123')
    assert resp.status_code == 200
    assert b'Analytics' in resp.data
    auth.logout()


def test_place_order_and_billing(client, auth, app):
    """Test 2: Verify cart addition, 5% GST computation, token generation, and order persistence."""
    auth.login('student', 'student123')

    with app.app_context():
        # Get sample menu items (e.g. Masala Dosa: 70.0, Masala Chai: 20.0)
        item1 = query_db("SELECT id, price FROM menu_items WHERE name = 'Masala Dosa'", one=True)
        item2 = query_db("SELECT id, price FROM menu_items WHERE name = 'Assam Masala Chai'", one=True)

    assert item1 is not None and item2 is not None

    # Add 2 Dosas and 1 Chai to Cart
    client.post('/cart/add', data={'item_id': item1['id'], 'quantity': 2}, follow_redirects=True)
    client.post('/cart/add', data={'item_id': item2['id'], 'quantity': 1}, follow_redirects=True)

    # View cart and check GST calculations:
    # Subtotal = (70 * 2) + (20 * 1) = 140 + 20 = 160.00
    # Tax = 160 * 0.05 = 8.00
    # Total = 168.00
    cart_resp = client.get('/cart')
    assert b'160.00' in cart_resp.data
    assert b'8.00' in cart_resp.data
    assert b'168.00' in cart_resp.data

    # Place order
    checkout_resp = client.post('/order/checkout', data={
        'special_instructions': 'Extra crispy please'
    }, follow_redirects=True)
    
    assert checkout_resp.status_code == 200
    assert b'Order placed successfully!' in checkout_resp.data
    assert b'Digital Token Ticket' in checkout_resp.data
    assert b'#T10' in checkout_resp.data  # Token format verification
    assert b'Received' in checkout_resp.data

    # Verify order in database
    with app.app_context():
        order = query_db("SELECT * FROM orders ORDER BY id DESC LIMIT 1", one=True)
        assert order is not None
        assert order['subtotal'] == 160.00
        assert order['tax'] == 8.00
        assert order['total'] == 168.00
        assert order['status'] == 'Received'
        assert order['special_instructions'] == 'Extra crispy please'
        assert order['token'].startswith('#T')

        # Check order items
        order_items = query_db("SELECT * FROM order_items WHERE order_id = ?", (order['id'],))
        assert len(order_items) == 2


def test_order_status_transitions_and_cancellation(client, auth, app):
    """Test 3: Verify staff stage advancement and student cancellation rules."""
    # 1. Place an order as student
    auth.login('student', 'student123')
    with app.app_context():
        item = query_db("SELECT id FROM menu_items LIMIT 1", one=True)
    client.post('/cart/add', data={'item_id': item['id'], 'quantity': 1})
    client.post('/order/checkout', data={}, follow_redirects=True)
    
    with app.app_context():
        order = query_db("SELECT * FROM orders ORDER BY id DESC LIMIT 1", one=True)
        order_id = order['id']
        assert order['status'] == 'Received'

    # 2. Staff advances order: Received -> Preparing
    auth.logout()
    auth.login('staff', 'staff123')
    advance_resp = client.post(f'/staff/order/{order_id}/advance', follow_redirects=True)
    assert advance_resp.status_code == 200
    with app.app_context():
        updated_order = query_db("SELECT status FROM orders WHERE id = ?", (order_id,), one=True)
        assert updated_order['status'] == 'Preparing'

    # 3. Staff advances order: Preparing -> Ready
    client.post(f'/staff/order/{order_id}/advance', follow_redirects=True)
    with app.app_context():
        updated_order = query_db("SELECT status FROM orders WHERE id = ?", (order_id,), one=True)
        assert updated_order['status'] == 'Ready'

    # 4. Staff advances order: Ready -> Collected
    client.post(f'/staff/order/{order_id}/advance', follow_redirects=True)
    with app.app_context():
        updated_order = query_db("SELECT status FROM orders WHERE id = ?", (order_id,), one=True)
        assert updated_order['status'] == 'Collected'

    # 5. Cancellation tests:
    # A) Attempt to cancel an order that is already Collected -> Must be rejected!
    auth.logout()
    auth.login('student', 'student123')
    cancel_resp = client.post(f'/order/{order_id}/cancel', follow_redirects=True)
    assert b'cannot be cancelled' in cancel_resp.data

    # B) Place a fresh order and cancel it while still in 'Received' stage -> Must succeed!
    client.post('/cart/add', data={'item_id': item['id'], 'quantity': 1})
    client.post('/order/checkout', data={}, follow_redirects=True)
    with app.app_context():
        fresh_order = query_db("SELECT * FROM orders ORDER BY id DESC LIMIT 1", one=True)
        assert fresh_order['status'] == 'Received'
        fresh_order_id = fresh_order['id']

    cancel_resp2 = client.post(f'/order/{fresh_order_id}/cancel', follow_redirects=True)
    assert b'has been successfully cancelled' in cancel_resp2.data
    with app.app_context():
        cancelled_order = query_db("SELECT status FROM orders WHERE id = ?", (fresh_order_id,), one=True)
        assert cancelled_order['status'] == 'Cancelled'


def test_role_protection(client, auth):
    """Test 4: Verify role-based access control stops unauthorized role access."""
    # 1. Unauthenticated guest trying to access protected order page
    resp = client.get('/orders', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']

    # 2. Student trying to access Staff Queue -> 403 Forbidden
    auth.login('student', 'student123')
    resp = client.get('/staff/queue')
    assert resp.status_code == 403
    assert b'Access Denied' in resp.data

    # 3. Student trying to access Admin Dashboard -> 403 Forbidden
    resp = client.get('/admin/dashboard')
    assert resp.status_code == 403
    assert b'Access Denied' in resp.data

    # 4. Student trying to access Admin Menu Configuration -> 403 Forbidden
    resp = client.get('/admin/menu')
    assert resp.status_code == 403

    # 5. Staff trying to access Admin Dashboard -> 403 Forbidden
    auth.logout()
    auth.login('staff', 'staff123')
    resp = client.get('/admin/dashboard')
    assert resp.status_code == 403

    # 6. Admin can access everything
    auth.logout()
    auth.login('admin', 'admin123')
    assert client.get('/admin/dashboard').status_code == 200
    assert client.get('/admin/menu').status_code == 200
    assert client.get('/staff/queue').status_code == 200


def test_reports_totals_and_csv_export(client, auth, app):
    """Test 5: Verify sales aggregation, top dishes ranking, and CSV export file generation."""
    # Create test orders as student
    auth.login('student', 'student123')
    with app.app_context():
        items = query_db("SELECT id, name FROM menu_items LIMIT 3")
        id1, id2, id3 = items[0]['id'], items[1]['id'], items[2]['id']

    # Place Order 1
    client.post('/cart/add', data={'item_id': id1, 'quantity': 3})
    client.post('/order/checkout', data={})

    # Place Order 2
    client.post('/cart/add', data={'item_id': id2, 'quantity': 2})
    client.post('/cart/add', data={'item_id': id3, 'quantity': 1})
    client.post('/order/checkout', data={})

    auth.logout()
    auth.login('admin', 'admin123')

    # 1. Admin Dashboard View
    dash_resp = client.get('/admin/dashboard')
    assert dash_resp.status_code == 200
    assert b"Today's Total Orders" in dash_resp.data

    # 2. Chart Data JSON API
    chart_resp = client.get('/api/reports/chart-data')
    assert chart_resp.status_code == 200
    data = chart_resp.get_json()
    assert 'hourly' in data
    assert 'top_dishes' in data
    assert len(data['top_dishes']['labels']) > 0

    # 3. CSV Export
    csv_resp = client.get('/admin/reports/export-csv')
    assert csv_resp.status_code == 200
    assert csv_resp.headers['Content-Type'].startswith('text/csv')
    assert 'attachment; filename=' in csv_resp.headers['Content-Disposition']

    # Parse and validate CSV content
    csv_text = csv_resp.data.decode('utf-8')
    csv_reader = csv.reader(io.StringIO(csv_text))
    rows = list(csv_reader)
    
    # Check headers
    assert rows[0] == [
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
    ]
    # Check that orders are present
    assert len(rows) >= 3
    # Check that summary row is present
    assert any('SUMMARY' in r[0] for r in rows if r)


def test_menu_filtering_and_admin_crud(client, auth, app):
    """Test 6: Verify menu filters (search, category, diet) and Admin CRUD actions."""
    # 1. Menu browse category filter
    resp = client.get('/menu?category=Breakfast')
    assert resp.status_code == 200
    assert b'Masala Dosa' in resp.data

    # 2. Veg only filter
    resp = client.get('/menu?diet=veg')
    assert resp.status_code == 200
    assert b'Hyderabadi Chicken Biryani' not in resp.data

    # 3. Non-veg only filter
    resp = client.get('/menu?diet=non-veg')
    assert resp.status_code == 200
    assert b'Hyderabadi Chicken Biryani' in resp.data
    assert b'Masala Dosa' not in resp.data

    # 4. Search query
    resp = client.get('/menu?q=Biryani')
    assert resp.status_code == 200
    assert b'Hyderabadi Chicken Biryani' in resp.data

    # 5. Admin CRUD: Add new menu item
    auth.login('admin', 'admin123')
    add_resp = client.post('/admin/menu/add', data={
        'name': 'Gobi Manchurian',
        'category': 'Snacks',
        'price': '85.0',
        'is_veg': '1',
        'description': 'Crispy cauliflower tossed in spicy Indo-Chinese sauce',
        'image_emoji': '🥦'
    }, follow_redirects=True)
    assert add_resp.status_code == 200
    assert b'Gobi Manchurian' in add_resp.data

    with app.app_context():
        new_item = query_db("SELECT * FROM menu_items WHERE name = 'Gobi Manchurian'", one=True)
        assert new_item is not None
        assert new_item['price'] == 85.0
        item_id = new_item['id']

    # 6. Admin CRUD: Edit item
    edit_resp = client.post(f'/admin/menu/{item_id}/edit', data={
        'name': 'Special Gobi Manchurian',
        'category': 'Snacks',
        'price': '95.0',
        'is_veg': '1',
        'description': 'Upgraded crispy cauliflower',
        'image_emoji': '🥦',
        'is_available': '1'
    }, follow_redirects=True)
    assert edit_resp.status_code == 200
    assert b'Special Gobi Manchurian' in edit_resp.data

    # 7. Admin CRUD: Delete item
    del_resp = client.post(f'/admin/menu/{item_id}/delete', follow_redirects=True)
    assert del_resp.status_code == 200
    assert b'deleted successfully' in del_resp.data
