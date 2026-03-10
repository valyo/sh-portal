"""Tests for Customers page and API endpoints."""


class TestListCustomers:
    """GET /customers"""

    def test_unauthorized_redirects_to_home(self, client):
        rv = client.get("/customers", follow_redirects=False)
        assert rv.status_code in (302, 303)
        assert "/" in rv.location or rv.location.endswith("/")

    def test_logged_in_returns_200(self, logged_in_client, customer):
        rv = logged_in_client.get("/customers")
        assert rv.status_code == 200
        assert b"Customers" in rv.data
        assert customer.name.encode() in rv.data
        assert customer.email.encode() in rv.data


class TestGetCustomer:
    """GET /api/customer/<id>"""

    def test_unauthorized_returns_401(self, client, customer):
        rv = client.get(f"/api/customer/{customer.id}")
        assert rv.status_code == 401
        assert rv.get_json() == {"error": "Unauthorized"}

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.get("/api/customer/99999")
        assert rv.status_code == 404

    def test_returns_customer_data(self, logged_in_client, customer):
        rv = logged_in_client.get(f"/api/customer/{customer.id}")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["id"] == customer.id
        assert data["name"] == customer.name
        assert data["email"] == customer.email
        assert data["telephone"] == customer.telephone
        assert data["address"] == customer.address
        assert data["postnummer"] == customer.postnummer
        assert data["ort"] == customer.ort
        assert "bookings" in data
        assert isinstance(data["bookings"], list)

    def test_returns_bookings_for_customer_with_booking(self, logged_in_client, customer, season, booking):
        rv = logged_in_client.get(f"/api/customer/{customer.id}")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["id"] == customer.id
        assert len(data["bookings"]) == 1
        b = data["bookings"][0]
        assert b["season_id"] == season.id
        assert b["year"] == season.year
        assert b["type"] == "andelsbiodling"
        assert b["booking_id"] == booking.id


class TestUpdateCustomer:
    """POST /api/customer/<id>"""

    def test_unauthorized_returns_401(self, client, customer):
        rv = client.post(
            f"/api/customer/{customer.id}",
            data={"name": "Updated", "email": customer.email},
            follow_redirects=False,
        )
        assert rv.status_code == 401

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.post(
            "/api/customer/99999",
            data={"name": "Updated", "email": "a@b.com"},
            follow_redirects=False,
        )
        assert rv.status_code == 404

    def test_success_updates_customer(self, logged_in_client, customer, app):
        rv = logged_in_client.post(
            f"/api/customer/{customer.id}",
            data={
                "name": "Updated Name",
                "email": "updated@example.com",
                "telephone": "0711111111",
                "address": "New Street 2",
                "postnummer": "11111",
                "ort": "Göteborg",
            },
        )
        assert rv.status_code == 200
        assert rv.get_json() == {"success": True}
        with app.app_context():
            from sh_portal.models import Customer
            from sh_portal import db
            c = db.session.get(Customer, customer.id)
            assert c.name == "Updated Name"
            assert c.email == "updated@example.com"
            assert c.telephone == "0711111111"
            assert c.address == "New Street 2"
            assert c.postnummer == "11111"
            assert c.ort == "Göteborg"
