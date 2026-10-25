"""Tests for the customer picker in the New booking form (GET /api/customers)."""
import pytest


def _add_customer(app, **overrides):
    from sh_portal import db
    from sh_portal.models import Customer
    data = dict(email="x@example.com", name="X", telephone="1", address="a", postnummer="1", ort="o")
    data.update(overrides)
    with app.app_context():
        c = Customer(**data)
        db.session.add(c)
        db.session.commit()
        return c.id


class TestCustomersJson:
    def test_unauthorized_returns_401(self, client):
        assert client.get("/api/customers").status_code == 401

    def test_lists_all_customers_with_contact_fields_sorted_by_name(self, logged_in_client, app):
        _add_customer(app, email="b@example.com", name="bertil", telephone="2", address="Gata 2", postnummer="22222", ort="Lund")
        _add_customer(app, email="a@example.com", name="Åsa", ort="Malmö")
        _add_customer(app, email="c@example.com", name="Carl")
        data = logged_in_client.get("/api/customers").get_json()
        assert [c["name"] for c in data] == ["bertil", "Carl", "Åsa"]  # case-insensitive order
        bertil = data[0]
        assert bertil == {
            "id": bertil["id"], "name": "bertil", "email": "b@example.com", "telephone": "2",
            "address": "Gata 2", "postnummer": "22222", "ort": "Lund", "booked": False,
        }

    def test_empty_database_gives_empty_list(self, logged_in_client):
        assert logged_in_client.get("/api/customers").get_json() == []

    def test_booked_flag_is_per_kind_and_season(self, logged_in_client, app, season):
        from sh_portal import db
        from sh_portal.models import Bookings, BookingsLamm, Season
        honey = _add_customer(app, email="honey@example.com", name="Honey Person")
        lamb = _add_customer(app, email="lamb@example.com", name="Lamb Person")
        other = _add_customer(app, email="none@example.com", name="No Booking")
        with app.app_context():
            other_season = Season(year="2024", price=1.0, price_lamm=1.0)
            db.session.add(other_season)
            db.session.commit()
            db.session.add_all([
                Bookings(season_id=season.id, customer_id=honey, quantity=1),
                BookingsLamm(season_id=season.id, customer_id=lamb, quantity=1),
                Bookings(season_id=other_season.id, customer_id=other, quantity=1),
            ])
            db.session.commit()

        def booked(kind, season_id):
            rows = logged_in_client.get(f"/api/customers?kind={kind}&season_id={season_id}").get_json()
            return sorted(c["name"] for c in rows if c["booked"])

        assert booked("andelsbiodling", season.id) == ["Honey Person"]
        assert booked("lammandel", season.id) == ["Lamb Person"]
        assert booked("andelsbiodling", 99999) == []

    def test_booked_flag_also_covers_duplicate_rows_with_the_same_email(self, logged_in_client, app, season):
        from sh_portal import db
        from sh_portal.models import Bookings
        first = _add_customer(app, email="dup@example.com", name="Dup One")
        _add_customer(app, email="DUP@example.com", name="Dup Two")
        with app.app_context():
            db.session.add(Bookings(season_id=season.id, customer_id=first, quantity=1))
            db.session.commit()
        rows = logged_in_client.get(f"/api/customers?kind=andelsbiodling&season_id={season.id}").get_json()
        assert {c["name"]: c["booked"] for c in rows} == {"Dup One": True, "Dup Two": True}

    def test_without_kind_nobody_is_flagged(self, logged_in_client, app, season):
        _add_customer(app, email="a@example.com", name="A")
        assert logged_in_client.get(f"/api/customers?season_id={season.id}").get_json()[0]["booked"] is False

    def test_unknown_kind_is_rejected(self, logged_in_client):
        rv = logged_in_client.get("/api/customers?kind=pigs&season_id=1")
        assert rv.status_code == 400


class TestPickerOnThePages:
    @pytest.mark.parametrize("url", ["/andelsbiodling", "/lammandel"])
    def test_new_booking_form_has_the_picker(self, logged_in_client, season, url):
        html = logged_in_client.get(f"{url}?season_id={season.id}").get_data(as_text=True)
        assert 'id="customerPicker"' in html
        assert 'list="customerOptions"' in html
        assert 'id="customerOptions"' in html

    def test_picker_field_is_not_submitted_with_the_form(self, logged_in_client, season):
        html = logged_in_client.get(f"/lammandel?season_id={season.id}").get_data(as_text=True)
        picker = html[html.index('id="customerPicker"') - 60: html.index('id="customerPicker"') + 250]
        assert 'name="customerPicker"' not in picker and ' name=' not in picker
