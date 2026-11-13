"""A paid lammandel invoice can be turned into a sale (lammkött, category lammandel) by hand."""
import html as html_module
import re
from datetime import datetime

import pytest

from sh_portal import db


@pytest.fixture
def lamb_setup(app):
    """The product and category that the real DB gets from the migration."""
    from sh_portal.models import Product, SaleCategory
    with app.app_context():
        db.session.add_all([Product(name="lammkött"), SaleCategory(name="lammandel")])
        db.session.commit()


def _pay(app, invoice_id, day=datetime(2025, 3, 14)):
    """Mark paid through the session the fixtures keep open (the test client reuses that app context)."""
    from sh_portal.models import InvoiceLamm
    db.session.get(InvoiceLamm, invoice_id).date_payed = day
    db.session.commit()


def _post_sale(client, invoice_id, **kw):
    return client.post(f"/lammandel/api/invoice/{invoice_id}/sale", **kw)


def _sales(app):
    from sh_portal.models import Sale
    with app.app_context():
        return [(s.id, s.product.name, s.category.name, s.skord, s.quantity, s.unit_price, s.timestamp, s.customer_id,
                 s.burk_kg, s.consistency, s.apiary, s.lamm_invoice_id, s.invoice_id) for s in Sale.query.all()]


class TestCreateSale:
    def test_a_paid_invoice_becomes_a_lammkott_sale(self, logged_in_client, app, customer, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        rv = _post_sale(logged_in_client, lamm_invoice.id)
        assert rv.status_code == 200 and rv.get_json()["success"] is True
        [(_, product, category, skord, qty, unit_price, ts, customer_id, burk, consistency, apiary, lamm_inv, andel_inv)] = _sales(app)
        assert (product, category, skord, qty) == ("lammkött", "lammandel", "2025", 2)
        assert unit_price == 200.0  # 400 kr / 2 shares
        assert ts == datetime(2025, 3, 14) and customer_id == customer.id
        assert (burk, consistency, apiary) == (None, None, None)
        assert lamm_inv == lamm_invoice.id and andel_inv is None

    def test_an_unpaid_invoice_is_refused(self, logged_in_client, app, lamm_invoice, lamb_setup):
        rv = _post_sale(logged_in_client, lamm_invoice.id)
        assert rv.status_code == 400
        assert _sales(app) == []

    def test_a_second_sale_for_the_same_invoice_is_refused(self, logged_in_client, app, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        assert _post_sale(logged_in_client, lamm_invoice.id).status_code == 200
        assert _post_sale(logged_in_client, lamm_invoice.id).status_code == 409
        assert len(_sales(app)) == 1

    def test_unknown_invoice_is_404(self, logged_in_client, lamb_setup):
        assert _post_sale(logged_in_client, 9999).status_code == 404

    def test_missing_product_or_category_is_reported(self, logged_in_client, app, lamm_invoice):
        _pay(app, lamm_invoice.id)
        rv = _post_sale(logged_in_client, lamm_invoice.id)
        assert rv.status_code == 500 and "missing" in rv.get_json()["error"]
        assert _sales(app) == []

    def test_requires_login(self, client, app, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        assert _post_sale(client, lamm_invoice.id).status_code == 401
        assert _sales(app) == []

    def test_cross_origin_is_blocked(self, logged_in_client, app, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        assert _post_sale(logged_in_client, lamm_invoice.id, headers={"Origin": "https://evil.example"}).status_code == 403
        assert _sales(app) == []

    def test_a_price_with_decimals_is_the_invoice_total_per_share(self, logged_in_client, app, lamm_invoice, lamb_setup):
        from sh_portal.models import InvoiceLamm
        inv = db.session.get(InvoiceLamm, lamm_invoice.id)
        inv.quantity, inv.tot_sum = 3, 11700.0
        db.session.commit()
        _pay(app, lamm_invoice.id)
        _post_sale(logged_in_client, lamm_invoice.id)
        assert _sales(app)[0][4:6] == (3, 3900.0)


class TestFollowsTheInvoice:
    def _paid_with_sale(self, client, app, invoice):
        _pay(app, invoice.id)
        assert _post_sale(client, invoice.id).status_code == 200

    def test_changing_the_payment_date_moves_the_sale(self, logged_in_client, app, lamm_invoice, lamb_setup):
        self._paid_with_sale(logged_in_client, app, lamm_invoice)
        rv = logged_in_client.post(f"/lammandel/api/invoice/{lamm_invoice.id}/payment", json={"date_paid": "2025-05-01"})
        assert rv.get_json()["success"] is True
        assert _sales(app)[0][6] == datetime(2025, 5, 1)

    def test_clearing_the_payment_removes_the_sale(self, logged_in_client, app, lamm_invoice, lamb_setup):
        self._paid_with_sale(logged_in_client, app, lamm_invoice)
        logged_in_client.post(f"/lammandel/api/invoice/{lamm_invoice.id}/payment", json={"date_paid": None})
        assert _sales(app) == []

    def test_paying_does_not_create_a_sale_by_itself(self, logged_in_client, app, lamm_invoice, lamb_setup):
        logged_in_client.post(f"/lammandel/api/invoice/{lamm_invoice.id}/payment", json={"date_paid": "2025-05-01"})
        assert _sales(app) == []

    def test_deleting_the_invoice_removes_its_sale(self, logged_in_client, app, lamm_invoice, lamb_setup):
        self._paid_with_sale(logged_in_client, app, lamm_invoice)
        rv = logged_in_client.post(f"/lammandel/api/invoice/{lamm_invoice.id}/delete")
        assert rv.get_json()["success"] is True
        assert _sales(app) == []


class TestInvoicesTable:
    def _html(self, client, season):
        return client.get(f"/lammandel?season_id={season.id}").get_data(as_text=True)

    def test_unpaid_invoice_has_a_disabled_button(self, logged_in_client, season, lamm_invoice, lamb_setup):
        button = re.search(r'<button[^>]*create-sale-btn[^>]*>', self._html(logged_in_client, season), re.S).group(0)
        assert "disabled" in button and f'data-invoice-id="{lamm_invoice.id}"' in button

    def test_paid_invoice_has_an_enabled_button(self, logged_in_client, app, season, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        button = re.search(r'<button[^>]*create-sale-btn[^>]*>', self._html(logged_in_client, season), re.S).group(0)
        assert "disabled" not in button

    def test_an_invoice_with_a_sale_shows_a_badge_instead_of_the_button(self, logged_in_client, app, season, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        _post_sale(logged_in_client, lamm_invoice.id)
        html = self._html(logged_in_client, season)
        assert "Sale created" in html and "create-sale-btn" not in html.split("<script")[0]

    def test_andelsbiodling_has_no_create_sale_button(self, logged_in_client, season, customer, booking, invoice):
        html = logged_in_client.get(f"/andelsbiodling?season_id={season.id}").get_data(as_text=True)
        assert 'class="btn btn-sm btn-outline-success ms-1 create-sale-btn"' not in html


class TestBookingsColumns:
    def test_lammandel_has_no_welcome_sent_column(self, logged_in_client, season, customer, lamm_invoice):
        html = logged_in_client.get(f"/lammandel?season_id={season.id}").get_data(as_text=True)
        assert "<th>Welcome sent</th>" not in html and "<th>Cert. sent</th>" not in html
        header = re.search(r"<thead[^>]*>.*?</thead>", html, re.S).group(0)
        assert header.count("<th") == 8  # checkbox, name, quantity, status, payment, delivered, actions + select-all cell

    def test_andelsbiodling_keeps_cert_sent(self, logged_in_client, season, customer, booking):
        html = logged_in_client.get(f"/andelsbiodling?season_id={season.id}").get_data(as_text=True)
        assert "<th>Cert. sent</th>" in html


class TestCustomerCounts:
    def _counts(self, app, customer_id):
        from sh_portal.customers import _activity_counts
        with app.app_context():
            return _activity_counts().get(customer_id, {})

    def test_a_booking_alone_counts_as_one_lammandel(self, app, customer, lamm_invoice):
        c = self._counts(app, customer.id)
        assert (c["lamb"], c["sales"], c["honey"]) == (1, 0, 0)

    def test_a_lammandel_sale_is_counted_once_with_its_booking(self, logged_in_client, app, customer, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        _post_sale(logged_in_client, lamm_invoice.id)
        c = self._counts(app, customer.id)
        assert (c["lamb"], c["sales"], c["honey"]) == (1, 0, 0)

    def test_an_older_lammandel_sale_without_a_booking_counts(self, app, customer, lamb_setup, lamm_invoice):
        from sh_portal.models import Product, Sale, SaleCategory
        with app.app_context():
            db.session.add(Sale(timestamp=datetime(2023, 5, 1), product_id=Product.query.filter_by(name="lammkött").one().id,
                                skord="2023", unit_price=100.0, quantity=1, consistency=None, apiary=None,
                                category_id=SaleCategory.query.filter_by(name="lammandel").one().id, customer_id=customer.id))
            db.session.commit()
        assert self._counts(app, customer.id)["lamb"] == 2  # the 2025 booking and the 2023 sale

    def test_the_table_shows_lammandel_and_not_sales(self, logged_in_client, app, customer, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        _post_sale(logged_in_client, lamm_invoice.id)
        html = logged_in_client.get("/customers").get_data(as_text=True)
        row = re.search(rf"<tr>\s*<td>{customer.id}</td>.*?</tr>", html, re.S).group(0)
        text = re.sub(r"\s+", " ", html_module.unescape(re.sub(r"<[^>]+>", " ", row))).strip()
        assert "Lammandel: 1" in text and "Sales:" not in text

    def test_the_card_lists_the_share_once(self, logged_in_client, app, customer, lamm_invoice, lamb_setup):
        _pay(app, lamm_invoice.id)
        _post_sale(logged_in_client, lamm_invoice.id)
        data = logged_in_client.get(f"/api/customer/{customer.id}").get_json()
        assert data["seasons"] == [{"year": "2025", "type": "lammandel"}]
