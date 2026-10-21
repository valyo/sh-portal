"""Tests for home and auth-related endpoints."""
from unittest.mock import MagicMock, patch

from sh_portal.home import build_authorization_response


class TestHome:
    """GET /"""

    def test_home_returns_200(self, client):
        rv = client.get("/")
        assert rv.status_code == 200

    def test_home_logged_in_returns_200(self, logged_in_client):
        rv = logged_in_client.get("/")
        assert rv.status_code == 200

    def test_home_season_stats_includes_invoiced_and_paid(self, logged_in_client, season, booking, invoice):
        """Current season stats include num_invoiced and num_paid when invoices exist."""
        rv = logged_in_client.get("/")
        assert rv.status_code == 200
        # One invoice in this season
        assert b"Invoiced" in rv.data or b"invoiced" in rv.data
        assert b"Paid" in rv.data or b"paid" in rv.data


class TestLogout:
    """GET /logout"""

    def test_logout_redirects_to_home(self, client):
        rv = client.get("/logout", follow_redirects=False)
        assert rv.status_code in (302, 303)
        assert "/" in rv.location or rv.location.endswith("/")

    def test_logout_clears_session(self, logged_in_client):
        with logged_in_client.session_transaction() as sess:
            assert sess.get("user") is not None
        logged_in_client.get("/logout")
        # After logout, next request has no user (session cookie may still be sent but session cleared)
        rv = logged_in_client.get("/api/mail-backend")
        assert rv.status_code == 401


class TestLogin:
    """GET /login"""

    def test_login_redirects_to_github(self, client):
        rv = client.get("/login", follow_redirects=False)
        assert rv.status_code in (302, 303)
        assert "github" in rv.location.lower()


class TestRequestHost:
    """Werkzeug 3.1.7+ host validation vs the hosts this app actually uses."""

    def test_localhost_keeps_full_request_url(self, app):
        with app.test_request_context("/callback?code=abc", headers={"Host": "localhost:8087"}):
            from flask import request
            assert request.host == "localhost:8087"
            assert request.url == "http://localhost:8087/callback?code=abc"

    def test_public_host_keeps_full_request_url(self, app):
        with app.test_request_context("/callback?code=abc", headers={"Host": "example.com"}):
            from flask import request
            assert request.host == "example.com"
            assert request.url == "http://example.com/callback?code=abc"

    def test_underscore_host_empties_request_host(self, app):
        with app.test_request_context("/callback?code=abc", headers={"Host": "sh_portal:5000"}):
            from flask import request
            assert request.host == ""
            assert request.url.startswith("http:///")


class TestBuildAuthorizationResponse:
    """OAuth callback URL must not depend on request.host."""

    def test_appends_query_string(self):
        assert build_authorization_response(
            "http://localhost:8087/callback",
            b"code=abc&state=xyz",
        ) == "http://localhost:8087/callback?code=abc&state=xyz"

    def test_empty_query_returns_redirect_uri(self):
        assert build_authorization_response("http://localhost:8087/callback", b"") == (
            "http://localhost:8087/callback"
        )


class TestCallback:
    """GET /callback"""

    def test_uses_configured_redirect_uri_when_host_has_underscore(self, client, app):
        mock_oauth = MagicMock()
        mock_oauth.fetch_token.return_value = {"access_token": "t"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 999, "login": "nobody"}
        mock_oauth.get.return_value = mock_resp

        with patch("sh_portal.home.get_oauth", return_value=mock_oauth):
            rv = client.get(
                "/callback?code=abc&state=xyz",
                headers={"Host": "sh_portal:5000"},
            )

        assert rv.status_code == 200
        assert mock_oauth.fetch_token.call_args.kwargs["authorization_response"] == (
            f"{app.config['OAUTH_REDIRECT_URI']}?code=abc&state=xyz"
        )


class TestMaxContentLength:
    """Request body cap restores a limit after Werkzeug 3.1.9."""

    def test_limit_is_configured(self, app):
        assert app.config["MAX_CONTENT_LENGTH"] == 1024 * 1024

    def test_rejects_oversized_post(self, logged_in_client, app):
        app.config["MAX_CONTENT_LENGTH"] = 100
        rv = logged_in_client.post(
            "/api/mail-backend",
            data=b'{"backend":"' + b"g" * 200 + b'"}',
            content_type="application/json",
        )
        assert rv.status_code == 413
