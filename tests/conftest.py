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


@pytest.fixture
def season(app):
    """Create one season in the DB for endpoint tests."""
    from sh_portal.models import Season
    from sh_portal import db
    with app.app_context():
        s = Season(
            year='2025',
            price=100.0,
            price_lamm=200.0,
            google_sheets_link_honey='',
            sheet_range_honey='',
            google_sheets_link_lamm='',
            sheet_range_lamm='',
        )
        db.session.add(s)
        db.session.commit()
        db.session.refresh(s)
        yield s
        # In-memory DB is discarded after test; no teardown needed


@pytest.fixture
def booking(app, season):
    """Create one booking (andelsbiodling) for endpoint tests."""
    from sh_portal.models import Bookings
    from sh_portal import db
    with app.app_context():
        b = Bookings(
            season_id=season.id,
            email="test@example.com",
            name="Test User",
            telephone="0700000000",
            address="Street 1",
            postnummer="12345",
            ort="Stockholm",
            quantity=2,
        )
        db.session.add(b)
        db.session.commit()
        db.session.refresh(b)
        yield b
