"""Tests for home and auth-related endpoints."""


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
