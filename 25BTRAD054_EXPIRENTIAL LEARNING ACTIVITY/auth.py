import functools
import re
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, g
from werkzeug.security import generate_password_hash, check_password_hash
from database import query_db, execute_db

auth_bp = Blueprint('auth', __name__)


def login_required(view):
    """Decorator to require user login before accessing a view."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return view(**kwargs)
    return wrapped_view


def role_required(*allowed_roles):
    """Decorator to enforce role-based access control."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            
            user_role = session.get('role')
            if user_role not in allowed_roles:
                flash(f'Access denied. Role "{user_role}" does not have permission to access this page.', 'danger')
                return abort(403)
            return view(**kwargs)
        return wrapped_view
    return decorator


def student_required(view):
    """Decorator allowing only student users."""
    return role_required('student')(view)


def staff_required(view):
    """Decorator allowing staff and admin users."""
    return role_required('staff', 'admin')(view)


def admin_required(view):
    """Decorator allowing strictly admin users."""
    return role_required('admin')(view)


@auth_bp.before_app_request
def load_logged_in_user():
    """Populate g.user with current user details if logged in."""
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = query_db('SELECT id, username, name, email, role FROM users WHERE id = ?', (user_id,), one=True)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle new user registration."""
    if 'user_id' in session:
        return redirect(url_for('menu.browse_menu'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'student').strip().lower()

        # Input Validations
        errors = []
        if not username or len(username) < 3 or len(username) > 30:
            errors.append('Username must be between 3 and 30 characters.')
        elif not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append('Username can only contain alphanumeric characters and underscores.')

        if not name:
            errors.append('Full name is required.')

        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors.append('A valid email address is required.')

        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters long.')

        if password != confirm_password:
            errors.append('Passwords do not match.')

        if role not in ['student', 'staff']:
            errors.append('Invalid role specified. Only Student or Staff registration is allowed.')

        # Check existing username/email
        if not errors:
            existing_user = query_db('SELECT id FROM users WHERE username = ? OR email = ?', (username, email), one=True)
            if existing_user:
                errors.append('Username or email is already registered.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html', username=username, name=name, email=email, role=role)

        # Hash password and insert
        password_hash = generate_password_hash(password)
        execute_db(
            'INSERT INTO users (username, password_hash, name, email, role) VALUES (?, ?, ?, ?, ?)',
            (username, password_hash, name, email, role)
        )
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login and redirect according to role."""
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('reports.dashboard'))
        elif role == 'staff':
            return redirect(url_for('queue.staff_queue'))
        return redirect(url_for('menu.browse_menu'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Both username and password are required.', 'danger')
            return render_template('auth/login.html', username=username)

        user = query_db('SELECT * FROM users WHERE username = ?', (username,), one=True)

        if user is None or not check_password_hash(user['password_hash'], password):
            flash('Invalid username or password.', 'danger')
            return render_template('auth/login.html', username=username)

        # Set session
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['name'] = user['name']
        session['role'] = user['role']
        session['cart'] = {}  # Initialize empty cart

        flash(f"Welcome back, {user['name']}!", 'success')

        # Check next redirect or route to role home
        next_url = request.args.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)

        if user['role'] == 'admin':
            return redirect(url_for('reports.dashboard'))
        elif user['role'] == 'staff':
            return redirect(url_for('queue.staff_queue'))
        else:
            return redirect(url_for('menu.browse_menu'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """Log out the current user and clear the session."""
    session.clear()
    flash('You have been logged out safely.', 'info')
    return redirect(url_for('auth.login'))
