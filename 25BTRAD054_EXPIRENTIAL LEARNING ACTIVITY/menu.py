from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from database import query_db, execute_db
from auth import login_required, admin_required

menu_bp = Blueprint('menu', __name__)


@menu_bp.route('/')
def home():
    """Default entry point redirects users based on auth status."""
    return redirect(url_for('menu.browse_menu'))


@menu_bp.route('/menu')
def browse_menu():
    """Browse menu items with category filtering, keyword search, and veg/non-veg filter."""
    category = request.args.get('category', '').strip()
    search_query = request.args.get('q', '').strip()
    diet = request.args.get('diet', 'all').strip().lower()

    # Build dynamic query
    sql = 'SELECT * FROM menu_items WHERE 1=1'
    params = []

    if category and category in current_app.config['CATEGORIES']:
        sql += ' AND category = ?'
        params.append(category)

    if search_query:
        sql += ' AND (name LIKE ? OR description LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%'])

    if diet == 'veg':
        sql += ' AND is_veg = 1'
    elif diet == 'non-veg':
        sql += ' AND is_veg = 0'

    sql += ' ORDER BY category ASC, is_available DESC, name ASC'
    items = query_db(sql, params)

    categories = current_app.config['CATEGORIES']

    return render_template(
        'student/menu.html',
        items=items,
        categories=categories,
        selected_category=category,
        search_query=search_query,
        selected_diet=diet
    )


@menu_bp.route('/api/menu')
def api_menu():
    """JSON API for searching and filtering menu items."""
    category = request.args.get('category', '').strip()
    search_query = request.args.get('q', '').strip()
    diet = request.args.get('diet', 'all').strip().lower()

    sql = 'SELECT * FROM menu_items WHERE 1=1'
    params = []

    if category and category in current_app.config['CATEGORIES']:
        sql += ' AND category = ?'
        params.append(category)

    if search_query:
        sql += ' AND (name LIKE ? OR description LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%'])

    if diet == 'veg':
        sql += ' AND is_veg = 1'
    elif diet == 'non-veg':
        sql += ' AND is_veg = 0'

    sql += ' ORDER BY category, name'
    items = query_db(sql, params)
    
    return jsonify([{
        'id': item['id'],
        'name': item['name'],
        'category': item['category'],
        'price': item['price'],
        'is_veg': bool(item['is_veg']),
        'description': item['description'],
        'is_available': bool(item['is_available']),
        'image_emoji': item['image_emoji']
    } for item in items])


@menu_bp.route('/admin/menu')
@login_required
@admin_required
def admin_menu():
    """Admin view for managing all menu items."""
    items = query_db('SELECT * FROM menu_items ORDER BY category ASC, name ASC')
    categories = current_app.config['CATEGORIES']
    return render_template('admin/menu_management.html', items=items, categories=categories)


@menu_bp.route('/admin/menu/add', methods=['POST'])
@login_required
@admin_required
def add_item():
    """Create a new menu item with server-side validation."""
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    price_raw = request.form.get('price', '').strip()
    is_veg_raw = request.form.get('is_veg', '1')
    description = request.form.get('description', '').strip()
    image_emoji = request.form.get('image_emoji', '🍲').strip() or '🍲'

    # Validation
    errors = []
    if not name:
        errors.append('Item name is required.')

    if category not in current_app.config['CATEGORIES']:
        errors.append('Invalid category selected.')

    try:
        price = float(price_raw)
        if price <= 0:
            errors.append('Price must be greater than zero.')
    except ValueError:
        errors.append('Price must be a valid numeric value.')

    is_veg = 1 if is_veg_raw in ['1', 'true', 'on', 'yes'] else 0

    if errors:
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for('menu.admin_menu'))

    execute_db(
        '''INSERT INTO menu_items (name, category, price, is_veg, description, is_available, image_emoji)
           VALUES (?, ?, ?, ?, ?, 1, ?)''',
        (name, category, price, is_veg, description, image_emoji)
    )
    flash(f'Menu item "{name}" added successfully.', 'success')
    return redirect(url_for('menu.admin_menu'))


@menu_bp.route('/admin/menu/<int:item_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_item(item_id):
    """Update an existing menu item with validation."""
    item = query_db('SELECT id FROM menu_items WHERE id = ?', (item_id,), one=True)
    if not item:
        flash('Menu item not found.', 'danger')
        return redirect(url_for('menu.admin_menu'))

    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    price_raw = request.form.get('price', '').strip()
    is_veg_raw = request.form.get('is_veg', '1')
    description = request.form.get('description', '').strip()
    image_emoji = request.form.get('image_emoji', '🍲').strip() or '🍲'
    is_available = 1 if request.form.get('is_available') in ['1', 'true', 'on'] else 0

    errors = []
    if not name:
        errors.append('Item name is required.')

    if category not in current_app.config['CATEGORIES']:
        errors.append('Invalid category selected.')

    try:
        price = float(price_raw)
        if price <= 0:
            errors.append('Price must be greater than zero.')
    except ValueError:
        errors.append('Price must be a valid numeric value.')

    is_veg = 1 if is_veg_raw in ['1', 'true', 'on', 'yes'] else 0

    if errors:
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for('menu.admin_menu'))

    execute_db(
        '''UPDATE menu_items
           SET name = ?, category = ?, price = ?, is_veg = ?, description = ?, is_available = ?, image_emoji = ?
           WHERE id = ?''',
        (name, category, price, is_veg, description, is_available, image_emoji, item_id)
    )
    flash(f'Menu item "{name}" updated successfully.', 'success')
    return redirect(url_for('menu.admin_menu'))


@menu_bp.route('/admin/menu/<int:item_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_item(item_id):
    """Delete a menu item or mark it unavailable if previously ordered."""
    item = query_db('SELECT name FROM menu_items WHERE id = ?', (item_id,), one=True)
    if not item:
        flash('Item not found.', 'danger')
        return redirect(url_for('menu.admin_menu'))

    # Check if item is referenced in previous orders
    order_ref = query_db('SELECT id FROM order_items WHERE menu_item_id = ? LIMIT 1', (item_id,), one=True)
    if order_ref:
        # To maintain historical integrity of previous orders, mark unavailable instead of deleting
        execute_db('UPDATE menu_items SET is_available = 0 WHERE id = ?', (item_id,))
        flash(f'Item "{item["name"]}" is in historical orders; it has been marked as discontinued instead of deleted.', 'info')
    else:
        execute_db('DELETE FROM menu_items WHERE id = ?', (item_id,))
        flash(f'Item "{item["name"]}" deleted successfully.', 'success')

    return redirect(url_for('menu.admin_menu'))
