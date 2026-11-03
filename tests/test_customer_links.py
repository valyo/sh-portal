"""Customer names in the bookings, invoices and sales lists link to /customers?manage=<id>."""
from datetime import datetime

from sh_portal import db


def _manage_link(customer):
    return f'href="/customers?manage={customer.id}"'


class TestNameLinks:
    def test_booking_and_invoice_rows_link_to_the_customer(self, logged_in_client, season, customer, booking, invoice):
        html = logged_in_client.get(f"/andelsbiodling?season_id={season.id}").get_data(as_text=True)
        assert html.count(_manage_link(customer)) == 2  # bookings table + invoices table

    def test_a_sale_with_a_customer_links_to_them(self, logged_in_client, customer, product, sale_category, sale_from_invoice):
        html = logged_in_client.get("/sales?list=1").get_data(as_text=True)
        assert _manage_link(customer) in html

    def test_a_sale_with_a_free_text_name_is_not_a_link(self, logged_in_client, app, product, sale_category):
        from sh_portal.models import Sale
        with app.app_context():
            db.session.add(Sale(timestamp=datetime(2024, 3, 1), product_id=product.id, skord="2024", unit_price=1.0,
                                quantity=1, consistency="fast", apiary="Solberg", category_id=sale_category.id,
                                customer_name="Free Text"))
            db.session.commit()
        html = logged_in_client.get("/sales?list=1").get_data(as_text=True)
        assert "Free Text" in html and "/customers?manage=" not in html


class TestOpeningTheForm:
    def test_the_customers_page_opens_the_form_named_in_the_url(self, logged_in_client, customer):
        html = logged_in_client.get(f"/customers?manage={customer.id}").get_data(as_text=True)
        assert "get('manage')" in html
        assert f'class="btn btn-sm btn-outline-secondary manage-customer"\n                                                data-customer-id="{customer.id}"' in html
