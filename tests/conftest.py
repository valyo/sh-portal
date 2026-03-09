"""Pytest fixtures for SH Portal tests."""
import os
import pytest


@pytest.fixture
def app():
    """Create application for testing."""
    from sh_portal import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///:memory:')
    app.config['MAIL_BACKEND'] = os.getenv('MAIL_BACKEND', 'mailcatcher')
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def logged_in_client(client):
    """Client with session user set (logged in)."""
    with client.session_transaction() as sess:
        sess['user'] = {'username': 'testuser', 'id': 1}
    return client
