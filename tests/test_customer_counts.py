"""The Bookings and Sales columns of the customers table: andel-category sales are Andelsbiodling."""
import html as html_module
import re
from datetime import datetime

from sh_portal import db


def _sale(app, customer_id, product, category_id, invoice_id=None, year="2024"):
    from sh_portal.models import Sale
    with app.app_context():
        s = Sale(timestamp=datetime(int(year), 3, 1), product_id=product.id, skord=year, unit_price=100.0, quantity=1,
                 consistency="fast", apiary="Solberg", category_id=category_id, customer_id=customer_id,
                 invoice_id=invoice_id)
        db.session.add(s)
        db.session.commit()
        return s.id


def _category(app, name):
    from sh_portal.models import SaleCategory
    with app.app_context():
        c = SaleCategory(name=name)
        db.session.add(c)
        db.session.commit()
        return c.id


def _counts(app, customer_id):
    from sh_portal.customers import _activity_counts
    with app.app_context():
        return _activity_counts().get(customer_id, {})


def _row(html, name):
    """The table cells of one customer's row, as plain text."""
    row = re.search(rf"<tr>\s*<td>\d+</td>\s*<td>{name}</td>.*?</tr>", html, re.S).group(0)
    text = html_module.unescape(re.sub(r"<[^>]+>", " ", row))
    return re.sub(r"\s+", " ", text).strip()


class TestActivityCounts:
    def test_imported_andel_sales_count_as_andelsbiodling_not_as_sales(self, app, customer, product, sale_category):
        for year in range(2018, 2024):
            _sale(app, customer.id, product, sale_category.id, year=str(year))
        assert _counts(app, customer.id) == {"honey": 6, "lamb": 0, "sales": 0}

    def test_a_paid_booking_is_counted_once_through_its_sale(self, app, customer, product, sale_category, invoice, sale_from_invoice):
        for year in range(2019, 2025):
            _sale(app, customer.id, product, sale_category.id, year=str(year))
        # 6 imported + 1 created from the paid invoice = 7; the booking itself is not added again
        assert _counts(app, customer.id) == {"honey": 7, "lamb": 0, "sales": 0}

    def test_a_booking_without_a_sale_counts_as_one(self, app, customer, product, sale_category, booking):
        _sale(app, customer.id, product, sale_category.id)
        assert _counts(app, customer.id)["honey"] == 2

    def test_an_invoiced_but_unpaid_booking_counts_as_one(self, app, customer, invoice):
        assert _counts(app, customer.id)["honey"] == 1

    def test_other_categories_are_sales(self, app, customer, product, sale_category):
        kollega = _category(app, "kollega")
        _sale(app, customer.id, product, kollega)
        _sale(app, customer.id, product, kollega)
        _sale(app, customer.id, product, sale_category.id)
        assert _counts(app, customer.id) == {"honey": 1, "lamb": 0, "sales": 2}

    def test_lammandel_bookings_are_counted(self, app, customer, lamm_invoice):
        assert _counts(app, customer.id) == {"honey": 0, "lamb": 1, "sales": 0}

    def test_sales_without_a_customer_are_ignored(self, app, product, sale_category):
        from sh_portal.models import Sale
        with app.app_context():
            db.session.add(Sale(timestamp=datetime(2024, 3, 1), product_id=product.id, skord="2024", unit_price=1.0,
                                quantity=1, consistency="fast", apiary="Solberg", category_id=sale_category.id,
                                customer_name="Free Text"))
            db.session.commit()
        from sh_portal.customers import _activity_counts
        with app.app_context():
            assert _activity_counts() == {}


class TestCustomersPage:
    def test_the_table_shows_the_corrected_counts(self, logged_in_client, app, product, sale_category):
        from sh_portal.models import Customer
        with app.app_context():
            sarah = Customer(name="Sarah Lindstrom", email="s@example.com")
            buyer = Customer(name="Plain Buyer")
            nobody = Customer(name="No Activity")
            db.session.add_all([sarah, buyer, nobody])
            db.session.commit()
            sarah_id, buyer_id = sarah.id, buyer.id
        kollega = _category(app, "kollega")
        for year in range(2018, 2025):
            _sale(app, sarah_id, product, sale_category.id, year=str(year))
        _sale(app, buyer_id, product, kollega)
        html = logged_in_client.get("/customers").get_data(as_text=True)
        assert _row(html, "Sarah Lindstrom").endswith("Andelsbiodling: 7 — Manage")
        assert _row(html, "Plain Buyer").endswith("— Sales: 1 Manage")
        assert _row(html, "No Activity").endswith("— — Manage")
