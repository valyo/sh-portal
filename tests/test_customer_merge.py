"""Merging a duplicate customer into another: bookings and sales move, the duplicate is deleted."""
import pytest

from sh_portal import db


def _add(app, name, **kw):
    from sh_portal.models import Customer
    with app.app_context():
        c = Customer(name=name, **kw)
        db.session.add(c)
        db.session.commit()
        return c.id


def _person(app, name, email):
    return _add(app, name, email=email, telephone="070", address="Street 1", postnummer="12345", ort="Stad")


def _season(app, year):
    from sh_portal.models import Season
    with app.app_context():
        s = Season(year=year, price=100.0, price_lamm=200.0, google_sheets_link_honey='', sheet_range_honey='',
                   google_sheets_link_lamm='', sheet_range_lamm='')
        db.session.add(s)
        db.session.commit()
        return s.id


def _booking(app, model_name, season_id, customer_id, quantity=1):
    from sh_portal import models
    with app.app_context():
        b = getattr(models, model_name)(season_id=season_id, customer_id=customer_id, quantity=quantity)
        db.session.add(b)
        db.session.commit()
        return b.id


def _sale(app, customer_id, product, sale_category):
    from datetime import datetime
    from sh_portal.models import Sale
    with app.app_context():
        s = Sale(timestamp=datetime(2025, 3, 1), product_id=product.id, skord="2025", unit_price=100.0, quantity=1,
                 consistency="fast", apiary="Solberg", category_id=sale_category.id, customer_id=customer_id)
        db.session.add(s)
        db.session.commit()
        return s.id


def _ids(app):
    from sh_portal.models import Customer
    with app.app_context():
        return [c.id for c in Customer.query.order_by(Customer.id).all()]


def _merge(client, keep, duplicate, **kw):
    return client.post(f"/api/customer/{keep}/merge", data={"duplicate_id": duplicate}, **kw)


class TestAccess:
    def test_requires_login(self, client, app):
        keep, dup = _person(app, "A", "a@example.com"), _person(app, "B", "b@example.com")
        assert _merge(client, keep, dup).status_code == 401
        assert client.get(f"/api/customer/{keep}/merge-preview?duplicate_id={dup}").status_code == 401
        assert _ids(app) == [keep, dup]

    def test_cross_origin_is_blocked(self, logged_in_client, app):
        keep, dup = _person(app, "A", "a@example.com"), _person(app, "B", "b@example.com")
        assert _merge(logged_in_client, keep, dup, headers={"Origin": "https://evil.example"}).status_code == 403
        assert _ids(app) == [keep, dup]

    def test_unknown_customer_is_404(self, logged_in_client, app):
        dup = _person(app, "B", "b@example.com")
        assert _merge(logged_in_client, 9999, dup).status_code == 404


class TestValidation:
    def test_needs_a_duplicate(self, logged_in_client, app):
        keep = _person(app, "A", "a@example.com")
        rv = logged_in_client.post(f"/api/customer/{keep}/merge", data={})
        assert rv.status_code == 400 and rv.get_json()["success"] is False

    def test_cannot_merge_into_itself(self, logged_in_client, app):
        keep = _person(app, "A", "a@example.com")
        rv = _merge(logged_in_client, keep, keep)
        assert rv.status_code == 400
        assert _ids(app) == [keep]

    def test_unknown_duplicate_is_refused(self, logged_in_client, app):
        keep = _person(app, "A", "a@example.com")
        assert _merge(logged_in_client, keep, 9999).status_code == 400


class TestMerge:
    def test_bookings_and_sales_move_and_the_duplicate_is_deleted(self, logged_in_client, app, product, sale_category):
        from sh_portal.models import Bookings, BookingsLamm, Sale
        keep = _person(app, "Erik Trygg", "erik@work.example")
        dup = _person(app, "Erik Trygg", "erik@home.example")
        s2024, s2025 = _season(app, "2024"), _season(app, "2025")
        honey = _booking(app, "Bookings", s2024, dup, quantity=2)
        lamb = _booking(app, "BookingsLamm", s2025, dup, quantity=1)
        kept_honey = _booking(app, "Bookings", s2025, keep, quantity=3)
        sales = [_sale(app, dup, product, sale_category), _sale(app, dup, product, sale_category)]
        own_sale = _sale(app, keep, product, sale_category)

        rv = _merge(logged_in_client, keep, dup)
        assert rv.status_code == 200
        assert rv.get_json() == {"success": True, "message": "Erik Trygg merged into Erik Trygg",
                                 "bookings_moved": 2, "sales_moved": 2}
        assert _ids(app) == [keep]
        with app.app_context():
            assert db.session.get(Bookings, honey).customer_id == keep
            assert db.session.get(BookingsLamm, lamb).customer_id == keep
            assert db.session.get(Bookings, kept_honey).customer_id == keep
            assert db.session.get(Bookings, honey).quantity == 2
            assert [db.session.get(Sale, i).customer_id for i in sales + [own_sale]] == [keep] * 3

    def test_the_kept_customer_keeps_its_own_details(self, logged_in_client, app):
        from sh_portal.models import Customer
        keep = _person(app, "Said Aspen", "said@work.example")
        dup = _add(app, "Said", email="said@home.example", telephone="999", address="Other 9", postnummer="99999", ort="Annan")
        assert _merge(logged_in_client, keep, dup).status_code == 200
        with app.app_context():
            c = db.session.get(Customer, keep)
            assert (c.name, c.email, c.telephone, c.address, c.postnummer, c.ort) == (
                "Said Aspen", "said@work.example", "070", "Street 1", "12345", "Stad")

    def test_details_the_kept_customer_lacks_come_from_the_duplicate(self, logged_in_client, app):
        from sh_portal.models import Customer
        keep = _add(app, "Sales Only")
        dup = _person(app, "Sales Only", "dup@example.com")
        _booking(app, "Bookings", _season(app, "2025"), dup)
        assert _merge(logged_in_client, keep, dup).status_code == 200
        with app.app_context():
            c = db.session.get(Customer, keep)
            assert (c.email, c.telephone, c.address, c.postnummer, c.ort) == ("dup@example.com", "070", "Street 1", "12345", "Stad")
            assert len(c.bookings) == 1

    def test_the_invoice_stays_with_its_moved_booking(self, logged_in_client, app, season, customer, invoice, booking):
        from sh_portal.models import Invoice
        other = _person(app, "Test User", "other@example.com")
        # `customer` has the booking and invoice; merge it as the duplicate into the other one
        assert _merge(logged_in_client, other, customer.id).status_code == 200
        with app.app_context():
            inv = db.session.get(Invoice, invoice.id)
            assert inv.booking.customer_id == other
            assert inv.booking.season_id == season.id

    def test_other_customers_are_untouched(self, logged_in_client, app, product, sale_category):
        keep, dup, bystander = (_person(app, n, f"{n}@example.com") for n in ("K", "D", "Z"))
        z = _season(app, "2025")
        _booking(app, "Bookings", z, bystander)
        sale = _sale(app, bystander, product, sale_category)
        assert _merge(logged_in_client, keep, dup).status_code == 200
        assert _ids(app) == [keep, bystander]
        from sh_portal.models import Bookings, Sale
        with app.app_context():
            assert Bookings.query.filter_by(customer_id=bystander).count() == 1
            assert db.session.get(Sale, sale).customer_id == bystander

    def test_merging_customers_without_anything_attached(self, logged_in_client, app):
        keep, dup = _add(app, "A"), _add(app, "B")
        rv = _merge(logged_in_client, keep, dup)
        assert rv.get_json()["bookings_moved"] == 0 and rv.get_json()["sales_moved"] == 0
        assert _ids(app) == [keep]


class TestSameSeasonConflict:
    @pytest.mark.parametrize("model_name,label", [("Bookings", "Andelsbiodling"), ("BookingsLamm", "Lammandel")])
    def test_both_booked_in_the_same_season_is_refused_and_nothing_changes(self, logged_in_client, app, model_name, label):
        keep = _person(app, "Said Aspen", "said@work.example")
        dup = _person(app, "Said Aspen", "said@home.example")
        season_id = _season(app, "2025")
        other_year = _season(app, "2024")
        _booking(app, model_name, season_id, keep)
        clash = _booking(app, model_name, season_id, dup)
        movable = _booking(app, model_name, other_year, dup)

        rv = _merge(logged_in_client, keep, dup)
        assert rv.status_code == 400
        assert f"2025 {label}" in rv.get_json()["message"]
        assert _ids(app) == [keep, dup]
        from sh_portal import models
        with app.app_context():
            model = getattr(models, model_name)
            assert db.session.get(model, clash).customer_id == dup
            assert db.session.get(model, movable).customer_id == dup

    def test_different_kinds_in_the_same_season_do_not_conflict(self, logged_in_client, app):
        keep = _person(app, "A", "a@example.com")
        dup = _person(app, "B", "b@example.com")
        season_id = _season(app, "2025")
        _booking(app, "Bookings", season_id, keep)
        _booking(app, "BookingsLamm", season_id, dup)
        assert _merge(logged_in_client, keep, dup).status_code == 200


class TestPreview:
    def test_describes_the_merge_and_changes_nothing(self, logged_in_client, app, product, sale_category):
        keep = _add(app, "Sales Only")
        dup = _person(app, "Erik", "erik@example.com")
        s = _season(app, "2025")
        _booking(app, "Bookings", s, dup)
        _sale(app, dup, product, sale_category)

        rv = logged_in_client.get(f"/api/customer/{keep}/merge-preview?duplicate_id={dup}")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True and data["message"] is None
        plan = data["plan"]
        assert plan["keep"]["id"] == keep and plan["duplicate"]["id"] == dup
        assert [(b["year"], b["label"]) for b in plan["bookings"]] == [("2025", "Andelsbiodling")]
        assert plan["sales_count"] == 1
        assert plan["filled_fields"] == ["email", "telephone", "address", "postnummer", "ort"]
        assert _ids(app) == [keep, dup]

    def test_reports_a_conflict(self, logged_in_client, app):
        keep, dup = _person(app, "A", "a@example.com"), _person(app, "B", "b@example.com")
        s = _season(app, "2025")
        _booking(app, "Bookings", s, keep)
        _booking(app, "Bookings", s, dup)
        data = logged_in_client.get(f"/api/customer/{keep}/merge-preview?duplicate_id={dup}").get_json()
        assert data["success"] is False
        assert "2025 Andelsbiodling" in data["message"]
        assert data["plan"]["bookings"] == []

    def test_without_a_duplicate_it_is_a_400(self, logged_in_client, app):
        keep = _person(app, "A", "a@example.com")
        assert logged_in_client.get(f"/api/customer/{keep}/merge-preview").status_code == 400
