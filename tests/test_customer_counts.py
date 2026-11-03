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
        assert _counts(app, customer.id) == {"honey": 6, "unpaid": 0, "lamb": 0, "sales": 0}

    def test_a_paid_booking_is_counted_once_through_its_sale(self, app, customer, product, sale_category, invoice, sale_from_invoice):
        for year in range(2019, 2025):
            _sale(app, customer.id, product, sale_category.id, year=str(year))
        # 6 imported + 1 created from the paid invoice = 7; the booking itself is not added again
        assert _counts(app, customer.id) == {"honey": 7, "unpaid": 0, "lamb": 0, "sales": 0}

    def test_a_booking_without_a_sale_counts_as_one(self, app, customer, product, sale_category, booking):
        _sale(app, customer.id, product, sale_category.id)
        assert _counts(app, customer.id)["honey"] == 2

    def test_a_booking_whose_season_already_has_an_andel_sale_is_not_counted_again(self, app, customer, product, sale_category, booking, season):
        # booking is for season 2025; an imported andel sale for harvest year 2025 is the same share
        _sale(app, customer.id, product, sale_category.id, year="2025")
        _sale(app, customer.id, product, sale_category.id, year="2024")
        assert _counts(app, customer.id) == {"honey": 2, "unpaid": 0, "lamb": 0, "sales": 0}

    def test_only_an_andel_sale_hides_a_booking(self, app, customer, product, booking, season):
        kollega = _category(app, "kollega")
        _sale(app, customer.id, product, kollega, year="2025")
        assert _counts(app, customer.id) == {"honey": 1, "unpaid": 1, "lamb": 0, "sales": 1}

    def test_another_customers_sale_does_not_hide_a_booking(self, app, customer, product, sale_category, booking, season):
        from sh_portal.models import Customer
        with app.app_context():
            other = Customer(name="Other")
            db.session.add(other)
            db.session.commit()
            other_id = other.id
        _sale(app, other_id, product, sale_category.id, year="2025")
        assert _counts(app, customer.id)["honey"] == 1

    def test_sarah_lindstrom_case(self, app, season, product, sale_category):
        """Bookings for 2024-2026 and sales for 2020-2026 (only 2026 linked to an invoice) are 7 shares."""
        from sh_portal.models import Customer, Season, Bookings, Invoice
        with app.app_context():
            c = Customer(name="Sarah")
            db.session.add(c)
            seasons = {season.year: db.session.get(Season, season.id)}
            for y in ("2024", "2026"):
                seasons[y] = Season(year=y, price=100.0, price_lamm=200.0, google_sheets_link_honey="", sheet_range_honey="",
                                    google_sheets_link_lamm="", sheet_range_lamm="")
                db.session.add(seasons[y])
            db.session.commit()
            bookings = {y: Bookings(season_id=seasons[y].id, customer_id=c.id, quantity=3) for y in ("2024", "2025", "2026")}
            db.session.add_all(bookings.values())
            db.session.commit()
            inv = Invoice(season_id=seasons["2026"].id, booking_id=bookings["2026"].id, invoice_id="F-2026-0001",
                          quantity=3, tot_sum=300.0, vat_rate=12, date_payed=datetime(2026, 3, 17))
            db.session.add(inv)
            db.session.commit()
            customer_id, invoice_pk = c.id, inv.id
        for year in range(2020, 2026):
            _sale(app, customer_id, product, sale_category.id, year=str(year))
        _sale(app, customer_id, product, sale_category.id, invoice_id=invoice_pk, year="2026")
        assert _counts(app, customer_id) == {"honey": 7, "unpaid": 0, "lamb": 0, "sales": 0}

    def test_an_invoiced_but_unpaid_booking_counts_as_one(self, app, customer, invoice):
        assert _counts(app, customer.id)["honey"] == 1

    def test_an_unpaid_booking_is_counted_as_unpaid_but_paid_shares_are_not(self, app, customer, product, sale_category, booking):
        _sale(app, customer.id, product, sale_category.id, year="2020")
        counts = _counts(app, customer.id)
        assert (counts["honey"], counts["unpaid"]) == (2, 1)

    def test_a_paid_booking_is_not_unpaid(self, app, customer, invoice, sale_from_invoice):
        assert _counts(app, customer.id)["unpaid"] == 0

    def test_other_categories_are_sales(self, app, customer, product, sale_category):
        kollega = _category(app, "kollega")
        _sale(app, customer.id, product, kollega)
        _sale(app, customer.id, product, kollega)
        _sale(app, customer.id, product, sale_category.id)
        assert _counts(app, customer.id) == {"honey": 1, "unpaid": 0, "lamb": 0, "sales": 2}

    def test_lammandel_bookings_are_counted(self, app, customer, lamm_invoice):
        assert _counts(app, customer.id) == {"honey": 0, "unpaid": 0, "lamb": 1, "sales": 0}

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

    def test_the_table_header_is_sticky(self, logged_in_client, app, customer):
        html = logged_in_client.get("/customers").get_data(as_text=True)
        assert 'class="table-responsive customers-table-wrapper"' in html
        assert ".customers-table-wrapper thead th" in html and "position: sticky" in html

    def test_andelsbiodling_is_red_only_when_a_share_is_not_paid(self, logged_in_client, app, customer, product, sale_category, booking):
        # `customer` has an unpaid 2025 booking; the other customer only has an imported (paid) sale
        from sh_portal.models import Customer
        with app.app_context():
            payer = Customer(name="Paid Person")
            db.session.add(payer)
            db.session.commit()
            payer_id = payer.id
        _sale(app, payer_id, product, sale_category.id, year="2020")
        html = logged_in_client.get("/customers").get_data(as_text=True)
        unpaid_row = re.search(rf"<tr>\s*<td>{customer.id}</td>.*?</tr>", html, re.S).group(0)
        paid_row = re.search(rf"<tr>\s*<td>{payer_id}</td>.*?</tr>", html, re.S).group(0)
        assert 'badge bg-danger" title="1 not paid">Andelsbiodling: 1' in unpaid_row
        assert "bg-danger" not in paid_row and "bg-warning" in paid_row


class TestCustomerCard:
    """GET /api/customer/<id>: the 'seasons' list agrees with the table's count."""

    def _card(self, client, customer_id):
        return client.get(f"/api/customer/{customer_id}").get_json()

    def test_lists_andel_sales_and_uncovered_bookings_by_year(self, logged_in_client, app, customer, product, sale_category, booking, lamm_invoice):
        # booking is for 2025; the 2025 andel sale covers it, 2020 exists only as a sale
        _sale(app, customer.id, product, sale_category.id, year="2020")
        _sale(app, customer.id, product, sale_category.id, year="2025")
        data = self._card(logged_in_client, customer.id)
        assert data["seasons"] == [
            {"year": "2025", "type": "andelsbiodling", "paid": True},
            {"year": "2025", "type": "lammandel"},
            {"year": "2020", "type": "andelsbiodling", "paid": True},
        ]
        assert _counts(app, customer.id)["honey"] == sum(1 for x in data["seasons"] if x["type"] == "andelsbiodling")

    def test_a_paid_booking_is_listed_once(self, logged_in_client, app, customer, invoice, sale_from_invoice):
        data = self._card(logged_in_client, customer.id)
        assert data["seasons"] == [{"year": "2025", "type": "andelsbiodling", "paid": True}]

    def test_an_unsold_booking_is_listed_as_not_paid(self, logged_in_client, app, customer, booking):
        assert self._card(logged_in_client, customer.id)["seasons"] == [
            {"year": "2025", "type": "andelsbiodling", "paid": False}]

    def test_other_categories_are_not_shares(self, logged_in_client, app, customer, product, sale_category):
        _sale(app, customer.id, product, _category(app, "kollega"))
        assert self._card(logged_in_client, customer.id)["seasons"] == []

    def test_bookings_field_still_lists_real_bookings_only(self, logged_in_client, app, customer, product, sale_category):
        _sale(app, customer.id, product, sale_category.id, year="2020")
        data = self._card(logged_in_client, customer.id)
        assert data["bookings"] == []  # drives the delete button: sales alone do not block deleting
        assert data["seasons"] == [{"year": "2020", "type": "andelsbiodling", "paid": True}]
