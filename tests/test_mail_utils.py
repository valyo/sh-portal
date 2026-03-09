"""Tests for mail backend utils (get_mail_connection_params, get_effective_mail_backend_with_source)."""
import os
import pytest


class TestGetMailConnectionParams:
    """Tests for get_mail_connection_params."""

    def test_mailcatcher_returns_no_auth(self, monkeypatch):
        monkeypatch.delenv('MAIL_SERVER', raising=False)
        monkeypatch.delenv('MAIL_PORT', raising=False)
        from sh_portal.utils import get_mail_connection_params
        params = get_mail_connection_params('mailcatcher')
        assert params['server'] == 'mailcatcher'
        assert params['port'] == 1025
        assert params['use_tls'] is False
        assert params['use_ssl'] is False
        assert params['username'] == ''
        assert params['password'] == ''

    def test_mailcatcher_none_normalized_to_mailcatcher(self, monkeypatch):
        monkeypatch.delenv('MAIL_SERVER', raising=False)
        monkeypatch.delenv('MAIL_PORT', raising=False)
        from sh_portal.utils import get_mail_connection_params
        params = get_mail_connection_params(None)
        assert params['server'] == 'mailcatcher'
        assert params['port'] == 1025

    def test_google_returns_tls_and_env_credentials(self, monkeypatch):
        monkeypatch.setenv('MAIL_SERVER', 'smtp.gmail.com')
        monkeypatch.setenv('MAIL_PORT', '587')
        monkeypatch.setenv('MAIL_USERNAME', 'user@gmail.com')
        monkeypatch.setenv('MAIL_PASSWORD', 'secret')
        from sh_portal.utils import get_mail_connection_params
        params = get_mail_connection_params('google')
        assert params['server'] == 'smtp.gmail.com'
        assert params['port'] == 587
        assert params['use_tls'] is True
        assert params['use_ssl'] is False
        assert params['username'] == 'user@gmail.com'
        assert params['password'] == 'secret'

    def test_google_defaults_when_env_empty(self, monkeypatch):
        monkeypatch.delenv('MAIL_SERVER', raising=False)
        monkeypatch.delenv('MAIL_PORT', raising=False)
        monkeypatch.delenv('MAIL_USERNAME', raising=False)
        monkeypatch.delenv('MAIL_PASSWORD', raising=False)
        from sh_portal.utils import get_mail_connection_params
        params = get_mail_connection_params('google')
        assert params['server'] == 'smtp.gmail.com'
        assert params['port'] == 587
        assert params['use_tls'] is True
        assert params['username'] == ''
        assert params['password'] == ''


class TestGetEffectiveMailBackendWithSource:
    """Tests for get_effective_mail_backend_with_source (cookie > config)."""

    def test_no_cookie_uses_config(self, app):
        app.config['MAIL_BACKEND'] = 'google'
        with app.test_request_context():
            from sh_portal.utils import get_effective_mail_backend_with_source
            backend, source = get_effective_mail_backend_with_source(app)
            assert backend == 'google'
            assert source == 'config'

    def test_cookie_overrides_config(self, app):
        app.config['MAIL_BACKEND'] = 'google'
        with app.test_request_context(headers=[('Cookie', 'mail_backend=mailcatcher')]):
            from sh_portal.utils import get_effective_mail_backend_with_source
            backend, source = get_effective_mail_backend_with_source(app)
            assert backend == 'mailcatcher'
            assert source == 'cookie'

    def test_cookie_google(self, app):
        app.config['MAIL_BACKEND'] = 'mailcatcher'
        with app.test_request_context(headers=[('Cookie', 'mail_backend=google')]):
            from sh_portal.utils import get_effective_mail_backend_with_source
            backend, source = get_effective_mail_backend_with_source(app)
            assert backend == 'google'
            assert source == 'cookie'

    def test_invalid_cookie_falls_back_to_config(self, app):
        app.config['MAIL_BACKEND'] = 'google'
        with app.test_request_context(headers=[('Cookie', 'mail_backend=invalid')]):
            from sh_portal.utils import get_effective_mail_backend_with_source
            backend, source = get_effective_mail_backend_with_source(app)
            assert backend == 'google'
            assert source == 'config'
