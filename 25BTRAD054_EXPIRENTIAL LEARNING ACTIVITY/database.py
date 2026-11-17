import sqlite3
from flask import g, current_app
from werkzeug.security import generate_password_hash


def get_db():
    """Retrieve or create the SQLite database connection for the current request."""
    if 'db' not in g:
        db_path = current_app.config['DATABASE']
        # If in-memory database is requested, reuse the connection on app object in testing
        if db_path == ':memory:':
            if not hasattr(current_app, '_in_memory_db'):
                current_app._in_memory_db = sqlite3.connect(':memory:')
                current_app._in_memory_db.row_factory = sqlite3.Row
                current_app._in_memory_db.execute("PRAGMA foreign_keys = ON;")
            return current_app._in_memory_db

        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def close_db(e=None):
    """Close the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None and current_app.config.get('DATABASE') != ':memory:':
        db.close()


def query_db(query, args=(), one=False):
    """Execute a parameterized SELECT query and return rows as dictionaries."""
    db = get_db()
    cur = db.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=(), commit=True):
    """Execute a parameterized INSERT, UPDATE, or DELETE query and return the last row ID."""
    db = get_db()
    cur = db.execute(query, args)
    if commit:
        db.commit()
    last_id = cur.lastrowid
    rowcount = cur.rowcount
    cur.close()
    return last_id, rowcount


def init_db(app):
    """Create database tables and seed initial data if not already present."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'staff', 'admin')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Menu items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('Breakfast', 'Lunch', 'Snacks', 'Drinks')),
                price REAL NOT NULL CHECK(price >= 0),
                is_veg INTEGER NOT NULL DEFAULT 1 CHECK(is_veg IN (0, 1)),
                description TEXT,
                is_available INTEGER NOT NULL DEFAULT 1 CHECK(is_available IN (0, 1)),
                image_emoji TEXT DEFAULT '🍲',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token TEXT UNIQUE NOT NULL,
                subtotal REAL NOT NULL CHECK(subtotal >= 0),
                tax REAL NOT NULL CHECK(tax >= 0),
                total REAL NOT NULL CHECK(total >= 0),
                status TEXT NOT NULL DEFAULT 'Received' CHECK(status IN ('Received', 'Preparing', 'Ready', 'Collected', 'Cancelled')),
                estimated_wait_minutes INTEGER NOT NULL DEFAULT 15,
                special_instructions TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Order items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
                item_name TEXT NOT NULL,
                price REAL NOT NULL CHECK(price >= 0),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                subtotal REAL NOT NULL CHECK(subtotal >= 0)
            );
        ''')

        db.commit()

        # Seed default users if they don't exist
        seed_users(db)

        # Seed 12 sample menu items if table is empty
        seed_menu_items(db)


def seed_users(db):
    """Seed default admin, staff, and student accounts."""
    users_to_seed = [
        ('admin', 'admin123', 'Campus Admin', 'admin@canteen.edu', 'admin'),
        ('staff', 'staff123', 'Kitchen Staff 1', 'staff@canteen.edu', 'staff'),
        ('student', 'student123', 'Alex Student', 'student@canteen.edu', 'student')
    ]

    for username, password, name, email, role in users_to_seed:
        existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if not existing:
            hashed_pwd = generate_password_hash(password)
            db.execute(
                'INSERT INTO users (username, password_hash, name, email, role) VALUES (?, ?, ?, ?, ?)',
                (username, hashed_pwd, name, email, role)
            )
    db.commit()


def seed_menu_items(db):
    """Seed 12 diverse sample menu items spanning all four categories."""
    count = db.execute('SELECT COUNT(*) as count FROM menu_items').fetchone()['count']
    if count == 0:
        sample_items = [
            # Breakfast items
            ('Masala Dosa', 'Breakfast', 70.0, 1, 'Crispy fermented rice-lentil crepe filled with spiced potato mash, served with coconut chutney & sambar', 1, '🥞'),
            ('Idli Vada Combo', 'Breakfast', 60.0, 1, 'Two steamed fluffy rice cakes and one crispy lentil fritter with piping hot sambar & chutney', 1, '🍘'),
            ('Poha & Masala Chai Combo', 'Breakfast', 50.0, 1, 'Tempered flattened rice with roasted peanuts, mustard seeds, fresh coriander, and ginger chai', 1, '🥣'),
            
            # Lunch items
            ('Paneer Butter Masala Thali', 'Lunch', 130.0, 1, 'Tender cottage cheese in rich tomato-cashew gravy with 3 butter rotis, jeera rice & fresh salad', 1, '🍛'),
            ('Hyderabadi Chicken Biryani', 'Lunch', 160.0, 0, 'Fragrant basmati rice layered with tender spiced chicken, saffron, mint, and cooling onion raita', 1, '🍗'),
            ('South Indian Veg Thali', 'Lunch', 110.0, 1, 'Homestyle feast with steamed rice, sambar, rasam, vegetable poriyal, curd, pickle, and appalam', 1, '🍱'),
            
            # Snacks items
            ('Samosa Chaat', 'Snacks', 50.0, 1, 'Two crushed golden samosas layered with spicy chana masala, sweet tamarind & zesty mint chutney', 1, '🥟'),
            ('Crispy Veg Burger', 'Snacks', 85.0, 1, 'Golden vegetable patty layered with crisp iceberg lettuce, tomato slice, and house burger sauce', 1, '🍔'),
            ('Chicken Kathi Roll', 'Snacks', 95.0, 0, 'Flaky layered paratha roll stuffed with juicy tandoori chicken chunks, sliced onions & mint dip', 1, '🌯'),
            
            # Drinks items
            ('Assam Masala Chai', 'Drinks', 20.0, 1, 'Freshly boiled strong Assam black tea infused with crushed ginger, cardamom, and whole milk', 1, '☕'),
            ('Cold Coffee with Ice Cream', 'Drinks', 60.0, 1, 'Thick chilled blended coffee topped with a generous scoop of artisanal vanilla bean ice cream', 1, '🥤'),
            ('Alphonso Mango Lassi', 'Drinks', 55.0, 1, 'Thick creamy yogurt drink sweetened and blended with rich Alphonso mango pulp and cardamom', 1, '🥭')
        ]

        db.executemany(
            '''INSERT INTO menu_items (name, category, price, is_veg, description, is_available, image_emoji)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            sample_items
        )
        db.commit()


def init_app(app):
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db)
    init_db(app)
