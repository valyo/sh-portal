"""Tests for Andelsbiodling API endpoints."""


class TestGetBooking:
    """GET /api/booking/<id> (andelsbiodling context)."""

    def test_unauthorized_returns_401(self, client, booking):
        rv = client.get(f"/api/booking/{booking.id}")
        assert rv.status_code == 401
        assert rv.get_json() == {"error": "Unauthorized"}

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.get("/api/booking/99999")
        assert rv.status_code == 404

    def test_returns_booking_data(self, logged_in_client, booking):
        rv = logged_in_client.get(f"/api/booking/{booking.id}")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["id"] == booking.id
        assert data["name"] == booking.name
        assert data["email"] == booking.email
        assert data["quantity"] == booking.quantity
        assert "is_paid" in data
        assert "certificate_sent_at" in data


class TestUpdateBooking:
    """POST /api/booking/<id>."""

    def test_unauthorized_returns_401(self, client, booking):
        rv = client.post(
            f"/api/booking/{booking.id}",
            data={"name": "Updated", "email": booking.email, "telephone": booking.telephone,
                  "address": booking.address, "postnummer": booking.postnummer, "ort": booking.ort,
                  "quantity": "3"},
            follow_redirects=False,
        )
        assert rv.status_code == 401

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.post(
            "/api/booking/99999",
            data={"name": "Updated", "email": "a@b.com", "telephone": "0", "address": "a", "postnummer": "1", "ort": "b", "quantity": "1"},
            follow_redirects=False,
        )
        assert rv.status_code == 404

    def test_success_updates_booking(self, logged_in_client, booking, app):
        rv = logged_in_client.post(
            f"/api/booking/{booking.id}",
            data={
                "name": "Updated Name",
                "email": booking.email,
                "telephone": booking.telephone,
                "address": booking.address,
                "postnummer": booking.postnummer,
                "ort": booking.ort,
                "message": "",
                "quantity": "5",
                "certificate_name": "",
                "certificate_quantity": "",
            },
        )
        assert rv.status_code == 200
        assert rv.get_json() == {"success": True}
        with app.app_context():
            from sh_portal.models import Bookings
            from sh_portal import db
            b = db.session.get(Bookings, booking.id)
            assert b.name == "Updated Name"
            assert b.quantity == 5

    def test_update_booking_certificate_sent_checkbox(self, logged_in_client, booking, app):
        """certificate_sent=1 sets timestamp when was unset; certificate_sent=0 clears."""
        base = {
            "name": booking.name,
            "email": booking.email,
            "telephone": booking.telephone,
            "address": booking.address,
            "postnummer": booking.postnummer,
            "ort": booking.ort,
            "message": "",
            "quantity": str(booking.quantity),
            "certificate_name": "",
            "certificate_quantity": "",
        }
        rv = logged_in_client.post(
            f"/api/booking/{booking.id}",
            data={**base, "certificate_sent": "1"},
        )
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Bookings
            from sh_portal import db
            b = db.session.get(Bookings, booking.id)
            assert b.certificate_sent_at is not None
        rv2 = logged_in_client.post(
            f"/api/booking/{booking.id}",
            data={**base, "certificate_sent": "0"},
        )
        assert rv2.status_code == 200
        with app.app_context():
            b = db.session.get(Bookings, booking.id)
            assert b.certificate_sent_at is None


class TestSendInvoices:
    """POST /api/send-invoices."""

    def test_unauthorized_returns_401(self, client, season, booking):
        rv = client.post(
            "/api/send-invoices",
            json={"booking_ids": [booking.id], "season_id": season.id},
            content_type="application/json",
        )
        assert rv.status_code == 401

    def test_no_booking_ids_returns_400(self, logged_in_client, season):
        rv = logged_in_client.post(
            "/api/send-invoices",
            json={"booking_ids": [], "season_id": season.id},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "booking" in rv.get_json().get("error", "").lower()

    def test_no_season_id_returns_400(self, logged_in_client, booking):
        rv = logged_in_client.post(
            "/api/send-invoices",
            json={"booking_ids": [booking.id]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "season" in rv.get_json().get("error", "").lower()

    def test_invalid_season_returns_400(self, logged_in_client, booking):
        rv = logged_in_client.post(
            "/api/send-invoices",
            json={"booking_ids": [booking.id], "season_id": 99999},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "not found" in rv.get_json().get("error", "").lower()


class TestInvoicePayment:
    """POST /api/invoice/<id>/payment"""

    def test_unauthorized_returns_401(self, client, invoice):
        rv = client.post(
            f"/api/invoice/{invoice.id}/payment",
            json={"date_paid": "2025-03-15"},
            content_type="application/json",
        )
        assert rv.status_code == 401

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.post(
            "/api/invoice/99999/payment",
            json={"date_paid": "2025-03-15"},
            content_type="application/json",
        )
        assert rv.status_code == 404

    def test_mark_paid_creates_sale(self, logged_in_client, app, invoice, product, sale_category):
        """First time marking invoice as paid creates a Sale (product and category must exist)."""
        assert product.name == "solberg honung"
        assert sale_category.name == "andel"
        rv = logged_in_client.post(
            f"/api/invoice/{invoice.id}/payment",
            json={"date_paid": "2025-03-15"},
            content_type="application/json",
        )
        assert rv.status_code == 200
        assert rv.get_json().get("success") is True
        with app.app_context():
            from sh_portal.models import Sale, Invoice
            from sh_portal import db
            inv = db.session.get(Invoice, invoice.id)
            assert inv.date_payed is not None
            sales = Sale.query.filter_by(invoice_id=invoice.id).all()
            assert len(sales) == 1
            assert sales[0].quantity == invoice.quantity

    def test_mark_paid_again_does_not_duplicate_sale(self, logged_in_client, app, invoice, product, sale_category):
        """Marking already-paid invoice again (e.g. change date) does not create a second Sale."""
        # First payment
        logged_in_client.post(
            f"/api/invoice/{invoice.id}/payment",
            json={"date_paid": "2025-03-15"},
            content_type="application/json",
        )
        with app.app_context():
            from sh_portal.models import Sale
            from sh_portal import db
            count_after_first = Sale.query.filter_by(invoice_id=invoice.id).count()
            assert count_after_first == 1
        # Second request (e.g. user changes payment date)
        rv = logged_in_client.post(
            f"/api/invoice/{invoice.id}/payment",
            json={"date_paid": "2025-03-20"},
            content_type="application/json",
        )
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Sale
            from sh_portal import db
            sales = Sale.query.filter_by(invoice_id=invoice.id).all()
            assert len(sales) == 1
