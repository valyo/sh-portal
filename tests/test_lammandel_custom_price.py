"""Custom (hand-entered) price for an individual Lammandel andel."""
import json

import pytest

from sh_portal import db


@pytest.fixture
def prices(app, season):
    """Season with price 1 = 200 and price 2 = 300 (set through the fixture's own session)."""
    from sh_portal.models import Season
    s = db.session.get(Season, season.id)
    s.price_lamm, s.price_lamm_2 = 200.0, 300.0
    db.session.commit()
    return s


def _form(season, **extra):
    data = {
        "season_id": str(season.id), "name": "Nina New", "email": "nina@example.com", "telephone": "0701234567",
        "address": "Storgatan 1", "postnummer": "11122", "ort": "Uppsala", "quantity": "3", "message": "",
    }
    data.update(extra)
    return data


def _create(client, season, **extra):
    return client.post("/lammandel/api/booking", data=_form(season, **extra))


def _booking(booking_id):
    """Load a booking; call inside `with app.app_context():` so lazy relationships keep working."""
    from sh_portal.models import BookingsLamm
    return db.session.get(BookingsLamm, booking_id)


class TestCreateWithCustomPrices:
    def test_custom_price_is_stored_and_used_in_the_total(self, logged_in_client, season, prices, app):
        rv = _create(logged_in_client, season, andel_tiers=json.dumps([1, 2, 1]),
                     andel_custom_prices=json.dumps([None, None, 450.5]))
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import BookingsLamm
            b = db.session.get(BookingsLamm, rv.get_json()["booking_id"])
            assert b.get_andel_custom_prices() == [None, None, 450.5]
            assert b.andel_prices() == [200.0, 300.0, 450.5]
            assert b.total_price() == 950.5

    def test_custom_price_wins_over_the_tier_for_that_andel(self, logged_in_client, season, prices, app):
        rv = _create(logged_in_client, season, andel_tiers=json.dumps([2, 2, 2]),
                     andel_custom_prices=json.dumps([100, None, None]))
        with app.app_context():
            b = _booking(rv.get_json()["booking_id"])
            assert b.andel_prices() == [100.0, 300.0, 300.0]

    def test_zero_is_a_valid_custom_price(self, logged_in_client, season, prices, app):
        rv = _create(logged_in_client, season, quantity="1", andel_custom_prices=json.dumps([0]))
        assert rv.status_code == 200
        with app.app_context():
            assert _booking(rv.get_json()["booking_id"]).total_price() == 0.0

    def test_prices_are_rounded_to_ore_and_totals_have_no_float_noise(self, logged_in_client, season, prices, app):
        rv = _create(logged_in_client, season, quantity="3",
                     andel_custom_prices=json.dumps([0.1, 0.2, 123.456]))
        with app.app_context():
            b = _booking(rv.get_json()["booking_id"])
            assert b.get_andel_custom_prices() == [0.1, 0.2, 123.46]
            assert b.total_price() == 123.76

    def test_get_booking_returns_the_custom_prices(self, logged_in_client, season, prices):
        booking_id = _create(logged_in_client, season, andel_custom_prices=json.dumps([None, 99.5, None])).get_json()["booking_id"]
        data = logged_in_client.get(f"/lammandel/api/booking/{booking_id}").get_json()
        assert data["andel_custom_prices"] == [None, 99.5, None]

    def test_without_custom_prices_everything_works_as_before(self, logged_in_client, season, prices, app):
        rv = _create(logged_in_client, season, andel_tiers=json.dumps([1, 2, 2]))
        with app.app_context():
            b = _booking(rv.get_json()["booking_id"])
            assert b.get_andel_custom_prices() == [None, None, None]
            assert b.total_price() == 800.0

    @pytest.mark.parametrize("bad", [
        json.dumps([-1, None, None]), json.dumps([None, 100001, None]), json.dumps(["100", None, None]),
        json.dumps([True, None, None]), json.dumps({"a": 1}), json.dumps(5), "NaN", "[Infinity]", "[1e999]",
        "not json", json.dumps([None] * 201),
    ])
    def test_invalid_custom_prices_are_rejected_and_nothing_is_created(self, logged_in_client, season, prices, app, bad):
        rv = _create(logged_in_client, season, andel_custom_prices=bad)
        assert rv.status_code == 400
        assert rv.get_json()["success"] is False
        with app.app_context():
            from sh_portal.models import BookingsLamm, Customer
            assert BookingsLamm.query.count() == 0
            assert Customer.query.filter_by(email="nina@example.com").count() == 0


class TestEditCustomPrices:
    def _existing(self, client, season):
        return _create(client, season, andel_tiers=json.dumps([1, 2, 1]),
                       andel_custom_prices=json.dumps([None, 111, None])).get_json()["booking_id"]

    def _edit_form(self, **extra):
        data = {"name": "Nina New", "email": "nina@example.com", "telephone": "0701234567", "address": "Storgatan 1",
                "postnummer": "11122", "ort": "Uppsala", "message": "", "certificate_name": "",
                "certificate_quantity": "", "quantity": "3"}
        data.update(extra)
        return data

    def test_custom_price_can_be_changed_and_cleared(self, logged_in_client, season, prices, app):
        booking_id = self._existing(logged_in_client, season)
        rv = logged_in_client.post(f"/lammandel/api/booking/{booking_id}",
                                   data=self._edit_form(andel_custom_prices=json.dumps([None, 222.25, 50])))
        assert rv.get_json()["success"] is True
        with app.app_context():
            assert _booking(booking_id).andel_prices() == [200.0, 222.25, 50.0]
        logged_in_client.post(f"/lammandel/api/booking/{booking_id}",
                              data=self._edit_form(andel_custom_prices=json.dumps([None, None, None])))
        with app.app_context():
            assert _booking(booking_id).andel_prices() == [200.0, 300.0, 200.0]  # back to the season tiers

    def test_invalid_custom_price_on_edit_changes_nothing(self, logged_in_client, season, prices, app):
        booking_id = self._existing(logged_in_client, season)
        rv = logged_in_client.post(f"/lammandel/api/booking/{booking_id}",
                                   data=self._edit_form(andel_custom_prices=json.dumps([-5, None, None]), message="changed"))
        assert rv.get_json()["success"] is False
        with app.app_context():
            b = _booking(booking_id)
            assert b.get_andel_custom_prices() == [None, 111.0, None]
            assert b.message == ""

    def test_custom_prices_follow_quantity(self, logged_in_client, season, prices, app):
        booking_id = self._existing(logged_in_client, season)
        logged_in_client.post(f"/lammandel/api/booking/{booking_id}",
                              data=self._edit_form(quantity="2", andel_custom_prices=json.dumps([None, 111, 999])))
        with app.app_context():
            b = _booking(booking_id)
            assert b.get_andel_custom_prices() == [None, 111.0]      # truncated with the quantity
            b.quantity = 4
            assert b.get_andel_custom_prices() == [None, 111.0, None, None]  # padded, no price invented

    def test_lowering_the_quantity_does_not_leave_a_price_that_can_come_back(self, logged_in_client, season, prices, app):
        booking_id = self._existing(logged_in_client, season)   # quantity 3: tiers [1,2,1], custom [None,111,None]
        # a second custom price on andel 3, then shrink to 2 without resending any price list
        logged_in_client.post(f"/lammandel/api/booking/{booking_id}",
                              data=self._edit_form(andel_custom_prices=json.dumps([None, 111, 999])))
        logged_in_client.post(f"/lammandel/api/booking/{booking_id}", data=self._edit_form(quantity="2"))
        with app.app_context():
            b = _booking(booking_id)
            assert json.loads(b.andel_custom_prices) == [None, 111.0]
            assert json.loads(b.andel_tiers) == [1, 2]
        logged_in_client.post(f"/lammandel/api/booking/{booking_id}", data=self._edit_form(quantity="3"))
        with app.app_context():
            b = _booking(booking_id)
            assert b.get_andel_custom_prices() == [None, 111.0, None]   # the 999 is gone for good
            assert b.andel_prices() == [200.0, 111.0, 200.0]


class TestInvoiceWithCustomPrices:
    def test_invoice_is_the_sum_and_has_a_row_per_distinct_price(self, logged_in_client, season, prices, app,
                                                                  fake_invoice_pdf, monkeypatch):
        monkeypatch.setattr("sh_portal.lammandel.send_mail_using_current_config", lambda *a, **k: None)
        booking_id = _create(logged_in_client, season, quantity="4", andel_tiers=json.dumps([1, 2, 1, 1]),
                             andel_custom_prices=json.dumps([None, None, 450.5, 450.5])).get_json()["booking_id"]
        rv = logged_in_client.post("/lammandel/api/send-invoices",
                                   json={"booking_ids": [booking_id], "season_id": season.id, "vat_rate": 12})
        assert rv.status_code == 200
        with app.app_context():
            from flask import render_template
            from datetime import timedelta
            from sh_portal.models import InvoiceLamm
            inv = InvoiceLamm.query.filter_by(booking_id=booking_id).one()
            assert inv.tot_sum == 200.0 + 300.0 + 2 * 450.5
            assert inv.line_items == [
                {"quantity": 1, "unit_price": 200.0, "total": 200.0},
                {"quantity": 1, "unit_price": 300.0, "total": 300.0},
                {"quantity": 2, "unit_price": 450.5, "total": 901.0},
            ]
            with app.test_request_context():
                html = render_template("invoice_pdf_template.html", invoice=inv, booking=inv.booking,
                                       timedelta=timedelta, logo_cid="logo", swish_qr_cid="swish_qr")
            assert "450.50 kr" in html and "901.00 kr" in html and "1401.00 kr" in html


class TestAndelsbiodlingIgnoresCustomPrices:
    def test_honey_booking_is_unaffected(self, logged_in_client, season, app):
        rv = logged_in_client.post("/api/booking", data=_form(season, andel_custom_prices=json.dumps([1, 2, 3])))
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Bookings
            assert not hasattr(db.session.get(Bookings, rv.get_json()["booking_id"]), "andel_custom_prices")


class TestFormMarkup:
    def test_lammandel_page_offers_custom_prices_and_renders_the_limit(self, logged_in_client, season):
        html = logged_in_client.get(f"/lammandel?season_id={season.id}").get_data(as_text=True)
        assert "custom price" in html
        assert "const MAX_CUSTOM_PRICE = 100000;" in html
        assert "{{" not in html and "{%" not in html   # no unrendered template code

