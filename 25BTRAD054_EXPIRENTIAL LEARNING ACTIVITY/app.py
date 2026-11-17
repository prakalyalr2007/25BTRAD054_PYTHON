from datetime import datetime
from flask import Flask, render_template, session, g
from config import Config
from database import init_app


def create_app(test_config=None):
    """Application factory for the Campus Canteen Ordering System."""
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_object(test_config)

    # Initialize SQLite database and tables
    init_app(app)

    # Register Blueprints
    from auth import auth_bp
    from menu import menu_bp
    from orders import orders_bp
    from queue_mgmt import queue_bp
    from reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(queue_bp)
    app.register_blueprint(reports_bp)

    # Template context processor for global variables
    @app.context_processor
    def inject_global_data():
        cart = session.get('cart', {})
        total_items = 0
        if isinstance(cart, dict):
            for qty in cart.values():
                try:
                    total_items += int(qty)
                except (ValueError, TypeError):
                    pass

        return {
            'current_user': getattr(g, 'user', None),
            'cart_count': total_items,
            'categories': app.config.get('CATEGORIES', ['Breakfast', 'Lunch', 'Snacks', 'Drinks']),
            'current_year': datetime.now().year,
            'app_name': 'Campus Canteen'
        }

    # Custom Jinja filters
    @app.template_filter('currency')
    def currency_filter(value):
        try:
            return f"₹{float(value):.2f}"
        except (ValueError, TypeError):
            return f"₹0.00"

    # Custom error pages
    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template('errors/500.html'), 500

    return app


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    application = create_app()
    print("=" * 60)
    print(f" Campus Canteen Ordering System is starting on port {port}")
    print(" Default accounts:")
    print("   Admin:   admin / admin123")
    print("   Staff:   staff / staff123")
    print("   Student: student / student123")
    print("=" * 60)
    try:
        application.run(debug=True, host='0.0.0.0', port=port)
    except OSError:
        fallback_port = 5001
        print(f"Port {port} in use (e.g. macOS AirPlay). Falling back to http://127.0.0.1:{fallback_port}")
        application.run(debug=True, host='0.0.0.0', port=fallback_port)
