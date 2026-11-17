import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'campus-canteen-dev-key-change-in-production')
    DATABASE = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'canteen.db'))
    
    # Financial settings
    TAX_RATE = 0.05  # 5% GST
    
    # Menu categories
    CATEGORIES = ['Breakfast', 'Lunch', 'Snacks', 'Drinks']
    
    # Order workflow stages
    ORDER_STATUSES = ['Received', 'Preparing', 'Ready', 'Collected', 'Cancelled']
    
    # Wait time estimation parameters (in minutes)
    BASE_PREP_MINUTES = 10
    MINS_PER_ACTIVE_ORDER = 3
    
    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class TestingConfig(Config):
    """Configuration for automated test runs."""
    TESTING = True
    DATABASE = ':memory:'
    SECRET_KEY = 'test-secret-key-do-not-use-in-prod'
