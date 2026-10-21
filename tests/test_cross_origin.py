"""Cross-site POSTs must not be able to use an admin's login cookie."""
import pytest


class TestCrossOriginGuard:
    def test_cross_origin_delete_is_blocked_and_does_nothing(self, logged_in_client, invoice, app):
        rv = logged_in_client.post(f"/api/invoice/{invoice.id}/delete", headers={"Origin": "https://evil.example"})
        assert rv.status_code == 403
        assert rv.get_json() == {"error": "Cross-origin request blocked"}
        with app.app_context():
            from sh_portal import db
            from sh_portal.models import Invoice
            assert db.session.get(Invoice, invoice.id) is not None

    @pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost.evil.example", "http://localhost:9999"])
    def test_foreign_origins_are_blocked(self, logged_in_client, season, origin):
        rv = logged_in_client.post("/api/booking", data={"season_id": season.id}, headers={"Origin": origin})
        assert rv.status_code == 403

    def test_same_origin_is_allowed(self, logged_in_client, invoice):
        rv = logged_in_client.post(f"/api/invoice/{invoice.id}/delete", headers={"Origin": "http://localhost"})
        assert rv.status_code == 200

    def test_origin_matching_the_configured_redirect_uri_host_is_allowed(self, logged_in_client, invoice, app):
        app.config["OAUTH_REDIRECT_URI"] = "https://portal.example.org/callback"
        rv = logged_in_client.post(f"/api/invoice/{invoice.id}/delete", headers={"Origin": "https://portal.example.org"})
        assert rv.status_code == 200

    def test_extra_allowed_hosts_can_be_configured(self, logged_in_client, invoice, app):
        app.config["ALLOWED_ORIGIN_HOSTS"] = {"admin.example.org"}
        rv = logged_in_client.post(f"/api/invoice/{invoice.id}/delete", headers={"Origin": "https://admin.example.org"})
        assert rv.status_code == 200

    def test_requests_without_origin_still_work(self, logged_in_client, invoice):
        assert logged_in_client.post(f"/api/invoice/{invoice.id}/delete").status_code == 200

    def test_get_requests_are_never_blocked(self, logged_in_client):
        assert logged_in_client.get("/seasons", headers={"Origin": "https://evil.example"}).status_code == 200


class TestSessionCookie:
    def test_login_cookie_is_samesite_lax(self, client):
        rv = client.get("/login")
        cookie = rv.headers.get("Set-Cookie", "")
        assert "SameSite=Lax" in cookie
        assert "HttpOnly" in cookie
