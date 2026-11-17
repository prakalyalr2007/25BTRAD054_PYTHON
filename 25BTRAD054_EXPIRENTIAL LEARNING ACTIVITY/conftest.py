import os
import tempfile
import pytest
from app import create_app
from database import init_db


class TestConfig:
    TESTING = True
    SECRET_KEY = 'test-secret-key-123'
    TAX_RATE = 0.05
    CATEGORIES = ['Breakfast', 'Lunch', 'Snacks', 'Drinks']
    ORDER_STATUSES = ['Received', 'Preparing', 'Ready', 'Collected', 'Cancelled']
    BASE_PREP_MINUTES = 10
    MINS_PER_ACTIVE_ORDER = 3
    WTF_CSRF_ENABLED = False


@pytest.fixture
def app():
    """Create and configure a fresh Flask app instance with a temporary SQLite database for tests."""
    db_fd, db_path = tempfile.mkstemp()
    
    class RuntimeTestConfig(TestConfig):
        DATABASE = db_path

    app = create_app(RuntimeTestConfig)

    with app.app_context():
        init_db(app)

    yield app

    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()


class AuthActions:
    """Helper class to encapsulate login/logout actions in test cases."""
    def __init__(self, client):
        self._client = client

    def login(self, username='student', password='student123'):
        return self._client.post('/login', data={
            'username': username,
            'password': password
        }, follow_redirects=True)

    def logout(self):
        return self._client.get('/logout', follow_redirects=True)


@pytest.fixture
def auth(client):
    """Fixture providing authentication helpers."""
    return AuthActions(client)
