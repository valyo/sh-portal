"""Every customer is recorded, not only andel ones: only the name is required."""
import pytest

from sh_portal import db


def _customers(app):
    from sh_portal.models import Customer
    with app.app_context():
        return [(c.id, c.name, c.email, c.telephone, c.address, c.postnummer, c.ort)
                for c in Customer.query.order_by(Customer.id).all()]


def _add(app, **kw):
    from sh_portal.models import Customer
    data = dict(name="X", email=None, telephone=None, address=None, postnummer=None, ort=None)
    data.update(kw)
    with app.app_context():
        c = Customer(**data)
        db.session.add(c)
        db.session.commit()
        return c.id


def _sale_form(product, sale_category, **extra):
    data = {"timestamp": "2025-03-15", "product_id": product.id, "skord": "2025", "unit_price": "100",
            "quantity": "2", "consistency": "fast", "apiary": "Solberg", "category_id": sale_category.id}
    data.update(extra)
    return data


def _sales(app):
    from sh_portal.models import Sale
    with app.app_context():
        return [(s.id, s.customer_id, s.customer_name) for s in Sale.query.order_by(Sale.id).all()]


class TestModel:
    def test_a_customer_needs_only_a_name(self, app):
        from sh_portal.models import Customer
        with app.app_context():
            db.session.add(Customer(name="Just A Name"))
            db.session.commit()
            c = Customer.query.one()
            assert (c.email, c.telephone, c.address, c.postnummer, c.ort) == (None, None, None, None, None)

    def test_a_customer_without_a_name_is_rejected(self, app):
        import sqlalchemy
        from sh_portal.models import Customer
        with app.app_context():
            db.session.add(Customer(email="a@b.c"))
            with pytest.raises(sqlalchemy.exc.IntegrityError):
                db.session.commit()
            db.session.rollback()


class TestCreateSaleCustomer:
    def test_a_new_name_becomes_a_name_only_customer(self, logged_in_client, app, product, sale_category):
        rv = logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_name="  maria   svensson "),
                                   follow_redirects=True)
        assert b"Sale created successfully" in rv.data and b"Created the new customer Maria Svensson" in rv.data
        assert _customers(app) == [(1, "Maria Svensson", None, None, None, None, None)]
        assert _sales(app) == [(1, 1, None)]            # linked to the customer, no free-text name

    def test_a_picked_customer_is_used(self, logged_in_client, app, product, sale_category, customer):
        logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_id=customer.id, customer_name="ignored"))
        assert _sales(app) == [(1, customer.id, None)]
        assert len(_customers(app)) == 1

    def test_an_unknown_picked_customer_is_an_error(self, logged_in_client, app, product, sale_category):
        rv = logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_id=999), follow_redirects=True)
        assert b"no longer exists" in rv.data
        assert _sales(app) == []

    def test_an_exact_name_match_reuses_the_existing_customer(self, logged_in_client, app, product, sale_category):
        existing = _add(app, name="Anna Andersson", email="anna@example.com")
        rv = logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_name="ANNA andersson"),
                                   follow_redirects=True)
        assert b"Used the existing customer Anna Andersson" in rv.data
        assert len(_customers(app)) == 1
        assert _sales(app) == [(1, existing, None)]

    def test_several_customers_with_that_name_must_be_picked_by_hand(self, logged_in_client, app, product, sale_category):
        _add(app, name="Anna Andersson", email="a1@example.com")
        _add(app, name="Anna Andersson", email="a2@example.com")
        rv = logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_name="Anna Andersson"),
                                   follow_redirects=True)
        assert b"several customers named Anna Andersson" in rv.data
        assert _sales(app) == [] and len(_customers(app)) == 2

    def test_no_name_and_no_customer_means_a_sale_without_customer(self, logged_in_client, app, product, sale_category):
        logged_in_client.post("/sales/create", data=_sale_form(product, sale_category))
        assert _sales(app) == [(1, None, None)]
        assert _customers(app) == []

    def test_a_too_long_name_creates_neither_sale_nor_customer(self, logged_in_client, app, product, sale_category):
        rv = logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_name="N" * 151),
                                   follow_redirects=True)
        assert b"too long" in rv.data
        assert _sales(app) == [] and _customers(app) == []

    def test_contact_fields_sent_with_a_sale_are_ignored(self, logged_in_client, app, product, sale_category):
        """The sale form only carries the name; contact details are edited on the Customers page."""
        logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_name="Name Only",
                                                               customer_email="x@example.com", customer_address="Gatan 1"))
        assert _customers(app) == [(1, "Name Only", None, None, None, None, None)]

    def test_no_customer_is_created_when_the_sale_itself_is_invalid(self, logged_in_client, app, sale_category, product):
        rv = logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_name="Ghost Buyer", unit_price=""),
                                   follow_redirects=True)
        assert b"Unit price is required" in rv.data
        assert _customers(app) == []


class TestEditSaleCustomer:
    def test_editing_a_legacy_free_text_sale_turns_the_name_into_a_customer(self, logged_in_client, app, sale):
        from sh_portal.models import Sale
        # the sale fixture's app context is active, so this is the same session the request uses
        s = db.session.get(Sale, sale.id)
        s.customer_id, s.customer_name = None, "Gammal Kund"
        db.session.commit()
        data = _sale_form(sale.product, sale.category, customer_name="Gammal Kund")
        logged_in_client.post(f"/sales/{sale.id}/edit", data=data)
        names = [c[1] for c in _customers(app)]
        assert "Gammal Kund" in names
        with app.app_context():
            s = db.session.get(Sale, sale.id)
            assert s.customer_id is not None and s.customer_name is None and s.display_customer == "Gammal Kund"

    def test_editing_to_another_picked_customer(self, logged_in_client, app, sale):
        other = _add(app, name="Other Buyer")
        logged_in_client.post(f"/sales/{sale.id}/edit", data=_sale_form(sale.product, sale.category, customer_id=other))
        assert _sales(app)[0][1] == other

    def test_ambiguous_name_on_edit_changes_nothing(self, logged_in_client, app, sale):
        _add(app, name="Twin", email="t1@example.com")
        _add(app, name="Twin", email="t2@example.com")
        before = _sales(app)
        rv = logged_in_client.post(f"/sales/{sale.id}/edit", data=_sale_form(sale.product, sale.category, customer_name="Twin"),
                                   follow_redirects=True)
        assert b"several customers named Twin" in rv.data
        assert _sales(app) == before


class TestCustomerEndpoints:
    def test_create_with_only_a_name(self, logged_in_client, app):
        rv = logged_in_client.post("/api/customer", data={"name": "  Lone Name  ", "email": "", "telephone": " "})
        assert rv.status_code == 200 and rv.get_json()["success"] is True
        assert _customers(app) == [(rv.get_json()["customer_id"], "Lone Name", None, None, None, None, None)]

    @pytest.mark.parametrize("data,message", [
        ({"name": ""}, "Name is required"),
        ({"name": "N" * 151}, "too long"),
        ({"name": "A", "email": "nope"}, "does not look valid"),
    ])
    def test_create_validation(self, logged_in_client, app, data, message):
        rv = logged_in_client.post("/api/customer", data=data)
        assert rv.status_code == 400 and message in rv.get_json()["message"]
        assert _customers(app) == []

    def test_create_refuses_an_email_that_exists_ignoring_case(self, logged_in_client, app):
        _add(app, name="Owner", email="owner@example.com")
        rv = logged_in_client.post("/api/customer", data={"name": "Other", "email": "OWNER@example.com"})
        assert rv.status_code == 400 and "Owner already has this email" in rv.get_json()["message"]

    def test_create_requires_login(self, client):
        assert client.post("/api/customer", data={"name": "A"}).status_code == 401

    def test_update_can_clear_optional_fields_of_a_sales_customer(self, logged_in_client, app):
        cid = _add(app, name="Sales Pal", email="pal@example.com", telephone="1", address="a", postnummer="2", ort="o")
        rv = logged_in_client.post(f"/api/customer/{cid}", data={"name": "Sales Pal", "email": "", "telephone": "", "address": "", "postnummer": "", "ort": ""})
        assert rv.get_json()["success"] is True
        assert _customers(app) == [(cid, "Sales Pal", None, None, None, None, None)]

    def test_update_still_requires_the_name(self, logged_in_client, app):
        cid = _add(app, name="Keep Me")
        rv = logged_in_client.post(f"/api/customer/{cid}", data={"name": " "})
        assert rv.status_code == 400
        assert _customers(app)[0][1] == "Keep Me"

    def test_a_customer_with_bookings_keeps_the_details_invoices_need(self, logged_in_client, app, customer, booking):
        rv = logged_in_client.post(f"/api/customer/{customer.id}", data={"name": customer.name, "email": customer.email,
                                   "telephone": "", "address": "", "postnummer": "", "ort": ""})
        assert rv.status_code == 400 and "has bookings" in rv.get_json()["message"]
        assert _customers(app)[0][4] == customer.address        # untouched

    def test_changing_to_an_email_of_another_customer_is_refused_but_keeping_your_own_is_fine(self, logged_in_client, app):
        _add(app, name="First", email="first@example.com")
        second = _add(app, name="Second", email="second@example.com")
        assert logged_in_client.post(f"/api/customer/{second}", data={"name": "Second", "email": "FIRST@example.com"}).status_code == 400
        assert logged_in_client.post(f"/api/customer/{second}", data={"name": "Second Renamed", "email": "second@example.com"}).status_code == 200

    def test_detail_json_has_the_sales_count(self, logged_in_client, app, product, sale_category):
        logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_name="Counted"))
        logged_in_client.post("/sales/create", data=_sale_form(product, sale_category, customer_name="Counted"))
        assert logged_in_client.get("/api/customer/1").get_json()["sales_count"] == 2

    def test_customers_page_shows_customers_without_details_cleanly(self, logged_in_client, app):
        _add(app, name="Name Only")
        html = logged_in_client.get("/customers").get_data(as_text=True)
        assert "Name Only" in html and ">None<" not in html and "mailto:None" not in html


class TestPickerListIncludesSalesCustomers:
    def test_customers_json_copes_with_missing_details_and_flags_bookings(self, logged_in_client, app, season, customer, booking):
        _add(app, name="Sales Only")
        rows = {c["name"]: c for c in logged_in_client.get(f"/api/customers?kind=andelsbiodling&season_id={season.id}").get_json()}
        assert rows["Sales Only"]["email"] is None and rows["Sales Only"]["booked"] is False
        assert rows[customer.name]["booked"] is True


APPS = [pytest.param("/api/booking", "Bookings", id="andelsbiodling"),
        pytest.param("/lammandel/api/booking", "BookingsLamm", id="lammandel")]


def _booking_form(season, **extra):
    data = {"season_id": str(season.id), "name": "Pelle Plomb", "email": "pelle@example.com", "telephone": "0701234567",
            "address": "Gatan 1", "postnummer": "11122", "ort": "Lund", "quantity": "2", "message": ""}
    data.update(extra)
    return data


@pytest.mark.parametrize("url,model_name", APPS)
class TestBookingForPickedSalesCustomer:
    def test_completing_a_sales_customer_updates_them_instead_of_creating_a_duplicate(self, logged_in_client, app, season, url, model_name):
        sales_customer = _add(app, name="Pelle Plomb")                      # name only
        rv = logged_in_client.post(url, data=_booking_form(season, customer_id=str(sales_customer)))
        assert rv.status_code == 200
        assert any("updated" in n for n in rv.get_json()["notes"])
        assert _customers(app) == [(sales_customer, "Pelle Plomb", "pelle@example.com", "0701234567", "Gatan 1", "11122", "Lund")]

    def test_the_picked_customer_is_the_one_booked(self, logged_in_client, app, season, url, model_name):
        from sh_portal import models
        cid = _add(app, name="Pelle Plomb")
        booking_id = logged_in_client.post(url, data=_booking_form(season, customer_id=str(cid))).get_json()["booking_id"]
        with app.app_context():
            assert db.session.get(getattr(models, model_name), booking_id).customer_id == cid

    def test_a_picked_customer_with_a_booking_in_the_season_is_refused(self, logged_in_client, app, season, url, model_name):
        cid = _add(app, name="Pelle Plomb")
        assert logged_in_client.post(url, data=_booking_form(season, customer_id=str(cid))).status_code == 200
        rv = logged_in_client.post(url, data=_booking_form(season, customer_id=str(cid), email="other@example.com"))
        assert rv.status_code == 400 and "already exists" in rv.get_json()["message"]

    def test_an_email_used_by_another_customer_is_refused(self, logged_in_client, app, season, url, model_name):
        _add(app, name="Owner", email="pelle@example.com")
        cid = _add(app, name="Pelle Plomb")
        rv = logged_in_client.post(url, data=_booking_form(season, customer_id=str(cid)))
        assert rv.status_code == 400 and "Owner already uses the email" in rv.get_json()["message"]

    @pytest.mark.parametrize("bad", ["9999", "abc"])
    def test_an_unknown_picked_customer_is_refused(self, logged_in_client, app, season, url, model_name, bad):
        rv = logged_in_client.post(url, data=_booking_form(season, customer_id=bad))
        assert rv.status_code == 400 and "no longer exists" in rv.get_json()["message"]

    def test_a_booking_still_needs_all_the_details(self, logged_in_client, app, season, url, model_name):
        cid = _add(app, name="Pelle Plomb")
        rv = logged_in_client.post(url, data=_booking_form(season, customer_id=str(cid), address=""))
        assert rv.status_code == 400 and "address is required" in rv.get_json()["message"]
        assert _customers(app)[0][4] is None                              # customer untouched


class TestLinkSalesCustomersCommand:
    def _legacy_sales(self, app, product, sale_category, names):
        from sh_portal.models import Sale
        from datetime import datetime
        with app.app_context():
            for name in names:
                db.session.add(Sale(timestamp=datetime(2025, 3, 1), product_id=product.id, skord="2025", unit_price=100.0,
                                    quantity=1, consistency="fast", apiary="Solberg", category_id=sale_category.id,
                                    customer_id=None, customer_name=name))
            db.session.commit()

    def _run(self, app, *args):
        from sh_portal.commands import link_sales_customers
        return app.test_cli_runner().invoke(link_sales_customers, list(args))

    def test_dry_run_reports_but_changes_nothing(self, app, product, sale_category):
        self._legacy_sales(app, product, sale_category, ["Kund A", "Kund A", "Kund B"])
        result = self._run(app, "--dry-run")
        assert "DRY RUN: would link 3 sales: 2 new customers" in result.output
        assert _customers(app) == [] and all(s[1] is None for s in _sales(app))

    def test_creates_reuses_and_skips_ambiguous_names(self, app, product, sale_category):
        _add(app, name="Kund A", email="a@example.com")                     # exactly one -> reused
        _add(app, name="Kund Dubbel", email="d1@example.com")
        _add(app, name="Kund Dubbel", email="d2@example.com")               # two -> skipped
        self._legacy_sales(app, product, sale_category, ["kund a", "Kund A", "Kund Ny", "Kund Dubbel"])
        result = self._run(app)
        assert "Linked 3 sales: 1 new customers, 1 existing customers reused." in result.output
        assert "Skipped, several customers with this name: Kund Dubbel (1 sales, 2 customers)" in result.output
        by_name = {c[1]: c for c in _customers(app) if c[1] in ("Kund A", "Kund Ny")}
        sales = _sales(app)
        assert sales[0][1] == sales[1][1] == by_name["Kund A"][0] and sales[0][2] is None
        assert sales[2][1] == by_name["Kund Ny"][0]
        assert sales[3][1] is None and sales[3][2] == "Kund Dubbel"          # left for manual fixing

    def test_running_it_twice_changes_nothing_the_second_time(self, app, product, sale_category):
        self._legacy_sales(app, product, sale_category, ["Kund A"])
        self._run(app)
        before = (_customers(app), _sales(app))
        assert "Linked 0 sales" in self._run(app).output
        assert (_customers(app), _sales(app)) == before


class TestImportSalesCommand:
    def _csv(self, tmp_path, rows):
        path = tmp_path / "sales.csv"
        header = "Timestamp,sort,skörd,burk,unit_price,antal,konsistens,bigård,kategori,kund"
        path.write_text("\n".join([header] + rows) + "\n", encoding="utf-8")
        return str(path)

    def test_buyers_become_customers_and_repeat_buyers_are_reused(self, app, tmp_path, product, sale_category):
        from sh_portal.commands import import_sales
        csv_path = self._csv(tmp_path, [
            "2025-03-01,solberg honung,2025,2.5 kg,100.00 kr,2,fast,Solberg,andel,maria svensson",
            "2025-03-02,solberg honung,2025,2.5 kg,100.00 kr,1,fast,Solberg,andel,Maria Svensson",
            "2025-03-03,solberg honung,2025,2.5 kg,100.00 kr,1,fast,Solberg,andel,",
        ])
        result = app.test_cli_runner().invoke(import_sales, [csv_path])
        assert result.exit_code == 0
        assert [c[1] for c in _customers(app)] == ["Maria Svensson"]
        sales = _sales(app)
        assert sales[0][1] == sales[1][1] == 1 and sales[0][2] is None
        assert sales[2][1] is None and sales[2][2] is None               # no buyer named

    def test_dry_run_creates_no_customers(self, app, tmp_path, product, sale_category):
        from sh_portal.commands import import_sales
        csv_path = self._csv(tmp_path, ["2025-03-01,solberg honung,2025,2.5 kg,100.00 kr,2,fast,Solberg,andel,Maria Svensson"])
        app.test_cli_runner().invoke(import_sales, [csv_path, "--dry-run"])
        assert _customers(app) == [] and _sales(app) == []


class TestSaleFormMarkup:
    """The new-sale form stays compact and scrolls inside its dialog in short windows."""

    def _html(self, logged_in_client):
        return logged_in_client.get("/sales").get_data(as_text=True)

    def test_the_form_only_asks_for_the_customer_name(self, logged_in_client):
        html = self._html(logged_in_client)
        for removed in ("customer_email", "customer_telephone", "customer_address", "customer_postnummer", "customer_ort",
                        "sale_new_customer_details"):
            assert removed not in html

    def test_contact_details_are_pointed_to_the_customers_page(self, logged_in_client):
        assert "add contact details later on the Customers page" in self._html(logged_in_client)

    def test_the_customer_hint_reserves_its_space_so_the_form_does_not_resize(self, logged_in_client):
        html = self._html(logged_in_client)
        hint = html[html.index('id="sale_customer_normalized_hint"') - 5: html.index('id="sale_customer_normalized_hint"') + 160]
        assert "invisible" in hint and "min-height" in hint and "d-none" not in hint

    @pytest.mark.parametrize("form_marker", ["action=\"/sales/create\"", 'id="saleEditForm"'])
    def test_forms_inside_scrollable_dialogs_take_part_in_the_flex_layout(self, logged_in_client, form_marker):
        """Without this a tall form is clipped in a short window and its buttons cannot be reached."""
        html = self._html(logged_in_client)
        start = html.index("<form", html.index(form_marker) - 80)
        assert "d-flex flex-column flex-grow-1" in html[start: html.index(">", start)]
        assert "min-height: 0" in html[start: html.index(">", start)]

