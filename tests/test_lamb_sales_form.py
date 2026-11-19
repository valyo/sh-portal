"""Selling lammkött (weight and price per kg) and lammskinn (quantity and price) by hand: no honey fields."""
import pytest

from sh_portal import db


@pytest.fixture
def lamb(app):
    from sh_portal.models import Product
    with app.app_context():
        p = Product(name="lammkött")
        db.session.add(p)
        db.session.commit()
        db.session.refresh(p)
        yield p


def _sales(app):
    from sh_portal.models import Sale
    with app.app_context():
        return Sale.query.order_by(Sale.id).all()


def _lamb_form(lamb, category, **kw):
    data = {"timestamp": "2026-10-20", "product_id": lamb.id, "category_id": category.id, "kg": "2.4", "price_per_kg": "250"}
    data.update(kw)
    return {k: v for k, v in data.items() if v is not None}


@pytest.fixture
def skin(app):
    from sh_portal.models import Product
    with app.app_context():
        p = Product(name="lammskinn")
        db.session.add(p)
        db.session.commit()
        db.session.refresh(p)
        yield p


def _skin_form(skin, category, **kw):
    data = {"timestamp": "2026-10-20", "product_id": skin.id, "category_id": category.id, "quantity": "3", "unit_price": "400"}
    data.update(kw)
    return {k: v for k, v in data.items() if v is not None}


class TestCreate:
    def test_kg_and_price_per_kg_make_one_sale_with_the_total(self, logged_in_client, app, lamb, sale_category, customer):
        rv = logged_in_client.post("/sales/create", data=_lamb_form(lamb, sale_category, customer_id=customer.id), follow_redirects=True)
        assert rv.status_code == 200
        [s] = _sales(app)
        assert (s.quantity, s.burk_kg, s.unit_price, s.skord) == (1, 2.4, 600.0, "2026")  # 2.4 kg x 250 kr
        assert (s.consistency, s.apiary) == (None, None)
        assert s.customer_id == customer.id and s.invoice_id is None and s.lamm_invoice_id is None
        assert s.total_price == 600.0 and s.timestamp.strftime("%Y-%m-%d") == "2026-10-20"

    def test_a_typed_customer_name_creates_the_customer_as_for_honey(self, logged_in_client, app, lamb, sale_category):
        from sh_portal.models import Customer
        logged_in_client.post("/sales/create", data=_lamb_form(lamb, sale_category, customer_name="new buyer"))
        with app.app_context():
            assert [c.name for c in Customer.query.all()] == ["New Buyer"]
            assert _sales(app)[0].customer_id == Customer.query.one().id

    def test_no_customer_is_allowed(self, logged_in_client, app, lamb, sale_category):
        logged_in_client.post("/sales/create", data=_lamb_form(lamb, sale_category))
        assert len(_sales(app)) == 1 and _sales(app)[0].customer_id is None

    def test_the_honey_fields_are_not_needed(self, logged_in_client, app, lamb, sale_category):
        data = _lamb_form(lamb, sale_category)
        assert not ({"skord", "quantity", "unit_price", "consistency", "apiary", "burk_kg"} & set(data))
        logged_in_client.post("/sales/create", data=data)
        assert len(_sales(app)) == 1

    def test_the_price_is_rounded_to_whole_ore(self, logged_in_client, app, lamb, sale_category):
        logged_in_client.post("/sales/create", data=_lamb_form(lamb, sale_category, kg="1.333", price_per_kg="99.99"))
        assert _sales(app)[0].unit_price == 133.29

    @pytest.mark.parametrize("override", [
        {"kg": None}, {"kg": "0"}, {"kg": "-1"}, {"price_per_kg": None}, {"price_per_kg": "-5"},
        {"timestamp": ""}, {"timestamp": "not a date"}, {"category_id": None},
    ])
    def test_bad_input_creates_nothing(self, logged_in_client, app, lamb, sale_category, override):
        rv = logged_in_client.post("/sales/create", data=_lamb_form(lamb, sale_category, **override), follow_redirects=True)
        assert rv.status_code == 200 and _sales(app) == []

    def test_a_free_lamb_price_of_zero_is_allowed(self, logged_in_client, app, lamb, sale_category):
        logged_in_client.post("/sales/create", data=_lamb_form(lamb, sale_category, price_per_kg="0"))
        assert _sales(app)[0].unit_price == 0.0

    def test_honey_still_needs_its_fields(self, logged_in_client, app, product, sale_category):
        logged_in_client.post("/sales/create", data={"timestamp": "2026-10-20", "product_id": product.id,
                                                     "category_id": sale_category.id, "kg": "2", "price_per_kg": "100"})
        assert _sales(app) == []


class TestEdit:
    def _lamb_sale(self, client, app, lamb, category):
        client.post("/sales/create", data=_lamb_form(lamb, category))
        return _sales(app)[0].id

    def test_editing_the_weight_and_price_recomputes_the_total(self, logged_in_client, app, lamb, sale_category):
        sale_id = self._lamb_sale(logged_in_client, app, lamb, sale_category)
        logged_in_client.post(f"/sales/{sale_id}/edit", data=_lamb_form(lamb, sale_category, kg="3", price_per_kg="200", timestamp="2027-01-05"))
        [s] = _sales(app)
        assert (s.burk_kg, s.unit_price, s.quantity, s.skord, s.consistency, s.apiary) == (3.0, 600.0, 1, "2027", None, None)

    def test_switching_a_honey_sale_to_lamb(self, logged_in_client, app, lamb, product, sale_category):
        logged_in_client.post("/sales/create", data={"timestamp": "2025-03-15", "product_id": product.id, "skord": "2025",
                                                     "unit_price": "100", "quantity": "2", "consistency": "fast",
                                                     "apiary": "Solberg", "category_id": sale_category.id})
        sale_id = _sales(app)[0].id
        logged_in_client.post(f"/sales/{sale_id}/edit", data=_lamb_form(lamb, sale_category))
        [s] = _sales(app)
        assert (s.product_id, s.unit_price, s.consistency, s.apiary) == (lamb.id, 600.0, None, None)

    def test_switching_a_lamb_sale_back_to_honey_needs_the_honey_fields(self, logged_in_client, app, lamb, product, sale_category):
        sale_id = self._lamb_sale(logged_in_client, app, lamb, sale_category)
        logged_in_client.post(f"/sales/{sale_id}/edit", data={"timestamp": "2026-10-20", "product_id": product.id,
                                                              "category_id": sale_category.id})
        assert _sales(app)[0].product_id == lamb.id  # refused, unchanged

    def test_a_sale_made_from_a_lammandel_invoice_cannot_be_edited(self, logged_in_client, app, lamb, sale_category, lamm_invoice):
        from sh_portal.models import Sale
        db.session.add(Sale(timestamp=lamm_invoice.date_created, product_id=lamb.id, skord="2025", unit_price=200.0, quantity=2,
                            category_id=sale_category.id, lamm_invoice_id=lamm_invoice.id, consistency=None, apiary=None))
        db.session.commit()
        sale_id = Sale.query.one().id
        logged_in_client.post(f"/sales/{sale_id}/edit", data=_lamb_form(lamb, sale_category, kg="9", price_per_kg="9"))
        assert Sale.query.one().unit_price == 200.0


class TestForm:
    def test_the_lamb_product_is_marked_and_the_kg_fields_exist(self, logged_in_client, lamb, product):
        html = logged_in_client.get("/sales").get_data(as_text=True)
        assert f'<option value="{lamb.id}" data-kind="meat">lammkött</option>' in html
        assert f'<option value="{product.id}">solberg honung</option>' in html
        for field in ('name="kg"', 'name="price_per_kg"'):
            assert html.count(field) == 2  # new and edit form

    def test_the_skin_product_is_marked(self, logged_in_client, skin):
        html = logged_in_client.get("/sales").get_data(as_text=True)
        assert f'<option value="{skin.id}" data-kind="skin">lammskinn</option>' in html

    def test_fields_say_which_products_they_are_for(self, logged_in_client):
        html = logged_in_client.get("/sales").get_data(as_text=True)
        assert html.count('data-kinds="honey"') == 8  # skörd, jar, consistency, apiary in the new and edit forms
        assert html.count('data-kinds="honey skin"') == 4  # unit price and quantity
        assert html.count('data-kinds="meat"') == 6  # weight, price per kg, total

    def test_lammandel_invoice_sales_have_no_edit_button(self, logged_in_client, app, lamb, sale_category, lamm_invoice):
        from sh_portal.models import Sale
        db.session.add(Sale(timestamp=lamm_invoice.date_created, product_id=lamb.id, skord="2025", unit_price=200.0, quantity=2,
                            category_id=sale_category.id, lamm_invoice_id=lamm_invoice.id, consistency=None, apiary=None))
        db.session.commit()
        html = logged_in_client.get("/sales?list=1").get_data(as_text=True)
        assert "sale-edit-btn" not in html.split("<script")[0].split("<tbody>")[-1]


class TestSkin:
    def test_quantity_and_price_make_one_sale(self, logged_in_client, app, skin, sale_category, customer):
        rv = logged_in_client.post("/sales/create", data=_skin_form(skin, sale_category, customer_id=customer.id), follow_redirects=True)
        assert rv.status_code == 200
        [s] = _sales(app)
        assert (s.quantity, s.unit_price, s.skord, s.burk_kg) == (3, 400.0, "2026", None)
        assert (s.consistency, s.apiary) == (None, None)
        assert s.total_price == 1200.0 and s.customer_id == customer.id

    def test_a_typed_customer_name_creates_the_customer(self, logged_in_client, app, skin, sale_category):
        from sh_portal.models import Customer
        logged_in_client.post("/sales/create", data=_skin_form(skin, sale_category, customer_name="skin buyer"))
        with app.app_context():
            assert [c.name for c in Customer.query.all()] == ["Skin Buyer"]

    @pytest.mark.parametrize("override", [
        {"quantity": None}, {"quantity": "0"}, {"unit_price": None}, {"unit_price": "-1"},
        {"timestamp": ""}, {"timestamp": "x"}, {"category_id": None},
    ])
    def test_bad_input_creates_nothing(self, logged_in_client, app, skin, sale_category, override):
        rv = logged_in_client.post("/sales/create", data=_skin_form(skin, sale_category, **override), follow_redirects=True)
        assert rv.status_code == 200 and _sales(app) == []

    def test_editing(self, logged_in_client, app, skin, sale_category):
        logged_in_client.post("/sales/create", data=_skin_form(skin, sale_category))
        sale_id = _sales(app)[0].id
        logged_in_client.post(f"/sales/{sale_id}/edit", data=_skin_form(skin, sale_category, quantity="5", unit_price="350", timestamp="2027-02-01"))
        [s] = _sales(app)
        assert (s.quantity, s.unit_price, s.skord, s.consistency, s.apiary) == (5, 350.0, "2027", None, None)
