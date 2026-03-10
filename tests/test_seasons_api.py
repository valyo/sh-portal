"""Tests for seasons API endpoints."""


class TestGetSeason:
    """GET /api/season/<id>"""

    def test_unauthorized_returns_401(self, client, season):
        rv = client.get(f"/api/season/{season.id}")
        assert rv.status_code == 401
        assert rv.get_json() == {"error": "Unauthorized"}

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.get("/api/season/99999")
        assert rv.status_code == 404

    def test_returns_season_data(self, logged_in_client, season):
        rv = logged_in_client.get(f"/api/season/{season.id}")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["id"] == season.id
        assert data["year"] == season.year
        assert data["price"] == season.price
        assert data["price_lamm"] == season.price_lamm
        assert "google_sheets_link_honey" in data
        assert "sheet_range_honey" in data


class TestUpdateSeason:
    """POST /api/season/<id>"""

    def test_unauthorized_returns_401(self, client, season):
        rv = client.post(
            f"/api/season/{season.id}",
            data={"year": "2025", "price": "150", "price_lamm": "250"},
            follow_redirects=False,
        )
        assert rv.status_code == 401

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.post(
            "/api/season/99999",
            data={"year": "2025", "price": "150", "price_lamm": "250"},
            follow_redirects=False,
        )
        assert rv.status_code == 404

    def test_success_updates_season(self, logged_in_client, season, app):
        rv = logged_in_client.post(
            f"/api/season/{season.id}",
            data={
                "year": "2025",
                "price": "150.0",
                "price_lamm": "250.0",
                "google_sheets_link_honey": "",
                "sheet_range_honey": "",
                "google_sheets_link_lamm": "",
                "sheet_range_lamm": "",
            },
        )
        assert rv.status_code == 200
        assert rv.get_json() == {"success": True}
        with app.app_context():
            from sh_portal.models import Season
            s = Season.query.get(season.id)
            assert s.price == 150.0
            assert s.price_lamm == 250.0


class TestDeleteSeason:
    """POST /api/season/<id>/delete"""

    def test_unauthorized_returns_401(self, client, season):
        rv = client.post(f"/api/season/{season.id}/delete", follow_redirects=False)
        assert rv.status_code == 401

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.post("/api/season/99999/delete", follow_redirects=False)
        assert rv.status_code == 404

    def test_success_deletes_season(self, logged_in_client, season, app):
        sid = season.id
        rv = logged_in_client.post(f"/api/season/{sid}/delete")
        assert rv.status_code == 200
        assert rv.get_json() == {"success": True}
        with app.app_context():
            from sh_portal.models import Season
            assert Season.query.get(sid) is None


class TestListSeasons:
    """GET /seasons"""

    def test_unauthorized_redirects_to_home(self, client):
        rv = client.get("/seasons", follow_redirects=False)
        assert rv.status_code in (302, 303)
        assert "/" in rv.location or rv.location.endswith("/")

    def test_logged_in_returns_200(self, logged_in_client):
        rv = logged_in_client.get("/seasons")
        assert rv.status_code == 200


class TestCreateSeason:
    """POST /seasons/create"""

    def test_unauthorized_redirects_to_home(self, client):
        rv = client.post(
            "/seasons/create",
            data={"year": "2030", "price": "100", "price_lamm": "200",
                  "google_sheets_link_honey": "", "sheet_range_honey": "",
                  "google_sheets_link_lamm": "", "sheet_range_lamm": ""},
            follow_redirects=False,
        )
        assert rv.status_code in (302, 303)
        assert "/" in rv.location or rv.location.endswith("/")

    def test_logged_in_creates_season_and_redirects(self, logged_in_client, app):
        rv = logged_in_client.post(
            "/seasons/create",
            data={
                "year": "2030",
                "price": "100",
                "price_lamm": "200",
                "google_sheets_link_honey": "",
                "sheet_range_honey": "",
                "google_sheets_link_lamm": "",
                "sheet_range_lamm": "",
            },
            follow_redirects=False,
        )
        assert rv.status_code in (302, 303)
        assert "seasons" in rv.location
        with app.app_context():
            from sh_portal.models import Season
            s = Season.query.filter_by(year="2030").first()
            assert s is not None
            assert s.price == 100.0

    def test_duplicate_year_redirects_with_flash(self, logged_in_client, app):
        """Creating a season for a year that already exists must not create a second one and must flash error."""
        with app.app_context():
            from sh_portal.models import Season
            from sh_portal import db
            existing = Season(year="2029", price=50.0, price_lamm=100.0)
            db.session.add(existing)
            db.session.commit()
        # First create 2029 would work; we already have 2029 in DB, so try to create again
        rv = logged_in_client.post(
            "/seasons/create",
            data={
                "year": "2029",
                "price": "99",
                "price_lamm": "199",
                "google_sheets_link_honey": "",
                "sheet_range_honey": "",
                "google_sheets_link_lamm": "",
                "sheet_range_lamm": "",
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        # Flash "A season for this year already exists." should appear on the page
        assert b"A season for this year already exists" in rv.data or b"already exists" in rv.data
        with app.app_context():
            from sh_portal.models import Season
            seasons_2029 = Season.query.filter_by(year="2029").all()
            assert len(seasons_2029) == 1  # still only one, no duplicate
