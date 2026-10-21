"""Tests for manual booking creation (andelsbiodling and lammandel)."""
import json

import pytest


def _form(season, **overrides):
    data = {
        "season_id": str(season.id),
        "name": "Nina Newcustomer", "email": "nina@example.com", "telephone": "0701234567",
        "address": "Storgatan 1", "postnummer": "11122", "ort": "Uppsala",
        "quantity": "3", "message": "Hello", "certificate_name": "Nina & Co",
        "certificate_quantity": "2", "booking_date": "2025-03-04T10:30",
        "certificate_sent": "1", "delivered": "1",
    }
    data.update(overrides)
    return data


APPS = [
    pytest.param("/api/booking", "Bookings", id="andelsbiodling"),
    pytest.param("/lammandel/api/booking", "BookingsLamm", id="lammandel"),
]


@pytest.mark.parametrize("url,model_name", APPS)
class TestCreateBooking:
    def _model(self, name):
        from sh_portal import models
        return getattr(models, name)

    def test_unauthorized_returns_401(self, client, season, url, model_name):
        assert client.post(url, data=_form(season)).status_code == 401

    def test_creates_booking_with_all_attributes(self, logged_in_client, season, app, url, model_name):
        rv = logged_in_client.post(url, data=_form(season))
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        with app.app_context():
            from sh_portal import db
            b = db.session.get(self._model(model_name), body["booking_id"])
            assert b.season_id == season.id
            assert (b.name, b.email, b.telephone) == ("Nina Newcustomer", "nina@example.com", "0701234567")
            assert (b.address, b.postnummer, b.ort) == ("Storgatan 1", "11122", "Uppsala")
            assert b.quantity == 3
            assert b.message == "Hello"
            assert b.certificate_name == "Nina & Co"
            assert b.certificate_quantity == 2
            assert b.timestamp.strftime("%Y-%m-%d %H:%M") == "2025-03-04 10:30"
            assert b.certificate_sent_at is not None
            assert b.delivered_at is not None

    def test_optional_fields_can_be_left_out(self, logged_in_client, season, app, url, model_name):
        form = _form(season)
        for key in ("message", "certificate_name", "certificate_quantity", "booking_date",
                    "certificate_sent", "delivered"):
            form.pop(key)
        rv = logged_in_client.post(url, data=form)
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal import db
            b = db.session.get(self._model(model_name), rv.get_json()["booking_id"])
            assert b.certificate_name is None and b.certificate_quantity is None
            assert b.certificate_sent_at is None and b.delivered_at is None
            assert b.timestamp is not None

    def test_existing_customer_is_reused_by_email(self, logged_in_client, season, customer, app, url, model_name):
        rv = logged_in_client.post(url, data=_form(season, email=customer.email, name="Renamed"))
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Customer
            assert Customer.query.filter_by(email=customer.email).count() == 1
            assert Customer.query.filter_by(email=customer.email).one().name == "Renamed"

    def test_duplicate_booking_for_customer_and_season_rejected(self, logged_in_client, season, app, url, model_name):
        assert logged_in_client.post(url, data=_form(season)).status_code == 200
        rv = logged_in_client.post(url, data=_form(season, quantity="1"))
        assert rv.status_code == 400
        assert "already exists" in rv.get_json()["message"]
        with app.app_context():
            assert self._model(model_name).query.count() == 1

    @pytest.mark.parametrize("field", ["name", "email", "telephone", "address", "postnummer", "ort"])
    def test_required_fields(self, logged_in_client, season, app, url, model_name, field):
        rv = logged_in_client.post(url, data=_form(season, **{field: "  "}))
        assert rv.status_code == 400
        assert field in rv.get_json()["message"]
        with app.app_context():
            assert self._model(model_name).query.count() == 0

    @pytest.mark.parametrize("override", [
        {"quantity": "0"}, {"quantity": "abc"}, {"quantity": ""},
        {"certificate_quantity": "0"}, {"certificate_quantity": "x"},
        {"booking_date": "yesterday"}, {"season_id": "99999"}, {"season_id": ""},
    ])
    def test_invalid_values_rejected(self, logged_in_client, season, app, url, model_name, override):
        rv = logged_in_client.post(url, data=_form(season, **override))
        assert rv.status_code == 400
        assert rv.get_json()["success"] is False
        with app.app_context():
            from sh_portal.models import Customer
            assert self._model(model_name).query.count() == 0
            assert Customer.query.filter_by(email="nina@example.com").count() == 0


class TestCreateLammandelPrices:
    def test_andel_tiers_are_stored(self, logged_in_client, season, app):
        from sh_portal.models import Season
        from sh_portal import db
        # The season fixture's app context is active, so this uses the same session as the request.
        s = db.session.get(Season, season.id)
        s.price_lamm, s.price_lamm_2 = 200.0, 300.0
        db.session.commit()
        rv = logged_in_client.post("/lammandel/api/booking",
                                   data=_form(season, quantity="3", andel_tiers=json.dumps([1, 2, 2])))
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import BookingsLamm
            b = db.session.get(BookingsLamm, rv.get_json()["booking_id"])
            assert b.get_andel_tiers() == [1, 2, 2]
            assert b.total_price() == 800.0

    def test_tier_2_ignored_without_second_price(self, logged_in_client, season, app):
        rv = logged_in_client.post("/lammandel/api/booking",
                                   data=_form(season, quantity="2", andel_tiers=json.dumps([2, 2])))
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal import db
            from sh_portal.models import BookingsLamm
            assert db.session.get(BookingsLamm, rv.get_json()["booking_id"]).get_andel_tiers() == [1, 1]
