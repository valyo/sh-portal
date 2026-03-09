"""Tests for /api/mail-backend GET and POST."""
import pytest


class TestMailBackendGET:
    """GET /api/mail-backend."""

    def test_unauthorized_returns_401(self, client):
        rv = client.get('/api/mail-backend')
        assert rv.status_code == 401
        assert rv.get_json() == {'error': 'Unauthorized'}

    def test_returns_backend_and_source_when_logged_in(self, logged_in_client):
        rv = logged_in_client.get('/api/mail-backend')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['mail_backend'] in ('mailcatcher', 'google')
        assert data['mail_backend_source'] in ('cookie', 'config')

    def test_returns_cookie_value_when_set(self, logged_in_client):
        logged_in_client.set_cookie('mail_backend', 'google')
        rv = logged_in_client.get('/api/mail-backend')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['mail_backend'] == 'google'
        assert data['mail_backend_source'] == 'cookie'


class TestMailBackendPOST:
    """POST /api/mail-backend."""

    def test_unauthorized_returns_401(self, client):
        rv = client.post(
            '/api/mail-backend',
            json={'backend': 'google'},
            content_type='application/json',
        )
        assert rv.status_code == 401

    def test_valid_google_returns_200_and_sets_cookie(self, logged_in_client):
        rv = logged_in_client.post(
            '/api/mail-backend',
            json={'backend': 'google'},
            content_type='application/json',
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert data == {'success': True, 'mail_backend': 'google'}
        assert 'mail_backend=google' in rv.headers.get('Set-Cookie', '')

    def test_valid_mailcatcher_returns_200_and_sets_cookie(self, logged_in_client):
        rv = logged_in_client.post(
            '/api/mail-backend',
            json={'backend': 'mailcatcher'},
            content_type='application/json',
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert data == {'success': True, 'mail_backend': 'mailcatcher'}
        assert 'mail_backend=mailcatcher' in rv.headers.get('Set-Cookie', '')

    def test_invalid_backend_returns_400(self, logged_in_client):
        rv = logged_in_client.post(
            '/api/mail-backend',
            json={'backend': 'smtp.example.com'},
            content_type='application/json',
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert 'error' in data
        assert 'mailcatcher' in data['error'] and 'google' in data['error']

    def test_empty_backend_returns_400(self, logged_in_client):
        rv = logged_in_client.post(
            '/api/mail-backend',
            json={'backend': ''},
            content_type='application/json',
        )
        assert rv.status_code == 400

    def test_post_then_get_reflects_cookie(self, logged_in_client):
        logged_in_client.post(
            '/api/mail-backend',
            json={'backend': 'google'},
            content_type='application/json',
        )
        rv = logged_in_client.get('/api/mail-backend')
        assert rv.status_code == 200
        assert rv.get_json()['mail_backend'] == 'google'
        assert rv.get_json()['mail_backend_source'] == 'cookie'
