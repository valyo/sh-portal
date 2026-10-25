"""Deleting a customer: allowed without bookings; their sales keep the name as text."""
import pytest

from sh_portal import db


def _names(app):
    from sh_portal.models import Customer
    with app.app_context():
        return [c.name for c in Customer.query.order_by(Customer.id).all()]


def _add(app, name="Sales Pal", **kw):
    from sh_portal.models import Customer
    with app.app_context():
        c = Customer(name=name, **kw)
        db.session.add(c)
        db.session.commit()
        return c.id


def _sale_for(app, customer_id, product, sale_category, quantity=1):
    from datetime import datetime
    from sh_portal.models import Sale
    with app.app_context():
        s = Sale(timestamp=datetime(2025, 3, 1), product_id=product.id, skord="2025", unit_price=100.0, quantity=quantity,
                 consistency="fast", apiary="Solberg", category_id=sale_category.id, customer_id=customer_id)
        db.session.add(s)
        db.session.commit()
        return s.id


class TestDeleteCustomer:
    def test_requires_login(self, client, app):
        cid = _add(app)
        assert client.post(f"/api/customer/{cid}/delete").status_code == 401
        assert _names(app) == ["Sales Pal"]

    def test_unknown_customer_is_404(self, logged_in_client):
        assert logged_in_client.post("/api/customer/9999/delete").status_code == 404

    def test_a_customer_with_nothing_attached_is_deleted(self, logged_in_client, app):
        keep = _add(app, "Keep Me")
        gone = _add(app, "Delete Me", email="d@example.com")
        rv = logged_in_client.post(f"/api/customer/{gone}/delete")
        assert rv.status_code == 200
        assert rv.get_json() == {"success": True, "message": "Customer Delete Me deleted", "sales_kept": 0}
        assert _names(app) == ["Keep Me"]

    def test_their_sales_stay_with_the_name_as_plain_text(self, logged_in_client, app, product, sale_category):
        from sh_portal.models import Sale
        cid = _add(app, "Maria Svensson")
        s1 = _sale_for(app, cid, product, sale_category, quantity=2)
        s2 = _sale_for(app, cid, product, sale_category, quantity=3)
        rv = logged_in_client.post(f"/api/customer/{cid}/delete")
        assert rv.get_json()["sales_kept"] == 2
        assert _names(app) == []
        with app.app_context():
            sales = [db.session.get(Sale, i) for i in (s1, s2)]
            assert [(s.customer_id, s.customer_name, s.display_customer, s.quantity) for s in sales] == [
                (None, "Maria Svensson", "Maria Svensson", 2), (None, "Maria Svensson", "Maria Svensson", 3)]

    def test_other_customers_sales_are_untouched(self, logged_in_client, app, product, sale_category):
        from sh_portal.models import Sale
        other = _add(app, "Other Buyer")
        mine = _add(app, "To Delete")
        other_sale = _sale_for(app, other, product, sale_category)
        logged_in_client.post(f"/api/customer/{mine}/delete")
        with app.app_context():
            s = db.session.get(Sale, other_sale)
            assert s.customer_id == other and s.customer_name is None

    @pytest.mark.parametrize("make_booking,expected", [
        ("honey", "2025 Andelsbiodling"),
        ("lamm", "2025 Lammandel"),
    ])
    def test_a_customer_with_bookings_cannot_be_deleted(self, logged_in_client, app, season, customer, make_booking, expected):
        from sh_portal.models import Bookings, BookingsLamm
        with app.app_context():
            model = Bookings if make_booking == "honey" else BookingsLamm
            db.session.add(model(season_id=season.id, customer_id=customer.id, quantity=1))
            db.session.commit()
        rv = logged_in_client.post(f"/api/customer/{customer.id}/delete")
        assert rv.status_code == 400
        assert rv.get_json()["success"] is False
        assert expected in rv.get_json()["message"] and customer.name in rv.get_json()["message"]
        assert customer.name in _names(app)

    def test_a_customer_with_bookings_and_sales_keeps_everything(self, logged_in_client, app, season, customer, booking, product, sale_category):
        from sh_portal.models import Sale
        sale_id = _sale_for(app, customer.id, product, sale_category)
        assert logged_in_client.post(f"/api/customer/{customer.id}/delete").status_code == 400
        with app.app_context():
            assert db.session.get(Sale, sale_id).customer_id == customer.id

    def test_cross_site_requests_cannot_delete(self, logged_in_client, app):
        cid = _add(app)
        rv = logged_in_client.post(f"/api/customer/{cid}/delete", headers={"Origin": "https://evil.example"})
        assert rv.status_code == 403
        assert _names(app) == ["Sales Pal"]


class TestDeleteButtonOnThePage:
    def test_customers_page_has_the_button_and_the_endpoint_call(self, logged_in_client, app):
        _add(app)
        html = logged_in_client.get("/customers").get_data(as_text=True)
        assert 'id="deleteCustomerBtn"' in html
        assert "/delete'" in html and "confirm(" in html
