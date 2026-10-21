"""Tests for Lammandel per-andel pricing."""
import json

import pytest


@pytest.fixture
def lamm_booking(app, season, customer):
    from sh_portal.models import BookingsLamm, Season
    from sh_portal import db
    with app.app_context():
        s = db.session.get(Season, season.id)
        s.price_lamm = 200.0
        s.price_lamm_2 = 300.0
        b = BookingsLamm(season_id=season.id, customer_id=customer.id, quantity=3)
        db.session.add(b)
        db.session.commit()
        db.session.refresh(b)
        yield b


def _form(booking, **extra):
    return {
        "name": booking.name, "email": booking.email, "telephone": booking.telephone,
        "address": booking.address, "postnummer": booking.postnummer, "ort": booking.ort,
        "message": "", "quantity": str(booking.quantity),
        "certificate_name": "", "certificate_quantity": "", **extra,
    }


class TestSeasonSecondPrice:
    def test_season_price_lamm_2_set_and_cleared(self, logged_in_client, season, app):
        data = {"year": "2025", "price": "100", "price_lamm": "200", "price_lamm_2": "350"}
        assert logged_in_client.post(f"/api/season/{season.id}", data=data).status_code == 200
        assert logged_in_client.get(f"/api/season/{season.id}").get_json()["price_lamm_2"] == 350.0
        data["price_lamm_2"] = ""
        assert logged_in_client.post(f"/api/season/{season.id}", data=data).status_code == 200
        assert logged_in_client.get(f"/api/season/{season.id}").get_json()["price_lamm_2"] is None


class TestBookingPrices:
    def test_get_booking_defaults_to_price_1(self, logged_in_client, lamm_booking):
        data = logged_in_client.get(f"/lammandel/api/booking/{lamm_booking.id}").get_json()
        assert data["andel_tiers"] == [1, 1, 1]
        assert data["price_options"] == {"1": 200.0, "2": 300.0}

    def test_update_stores_tiers(self, logged_in_client, lamm_booking):
        rv = logged_in_client.post(
            f"/lammandel/api/booking/{lamm_booking.id}",
            data=_form(lamm_booking, andel_tiers=json.dumps([1, 2, 2])),
        )
        assert rv.get_json() == {"success": True}
        data = logged_in_client.get(f"/lammandel/api/booking/{lamm_booking.id}").get_json()
        assert data["andel_tiers"] == [1, 2, 2]

    def test_tier_2_ignored_without_price_2(self, logged_in_client, lamm_booking, app):
        from sh_portal.models import Season
        from sh_portal import db
        with app.app_context():
            db.session.get(Season, lamm_booking.season_id).price_lamm_2 = None
            db.session.commit()
        logged_in_client.post(
            f"/lammandel/api/booking/{lamm_booking.id}",
            data=_form(lamm_booking, andel_tiers=json.dumps([2, 2, 2])),
        )
        data = logged_in_client.get(f"/lammandel/api/booking/{lamm_booking.id}").get_json()
        assert data["andel_tiers"] == [1, 1, 1]

    def test_tiers_follow_quantity(self, app, lamm_booking):
        from sh_portal.models import BookingsLamm
        from sh_portal import db
        with app.app_context():
            b = db.session.get(BookingsLamm, lamm_booking.id)
            b.andel_tiers = json.dumps([2])
            b.quantity = 3
            assert b.get_andel_tiers() == [2, 1, 1]
            b.quantity = 1
            assert b.get_andel_tiers() == [2]


class TestInvoiceTotal:
    def test_invoice_is_sum_of_andel_prices(self, logged_in_client, lamm_booking, season, app, monkeypatch):
        monkeypatch.setattr("sh_portal.lammandel.send_mail_using_current_config", lambda *a, **k: None)
        logged_in_client.post(
            f"/lammandel/api/booking/{lamm_booking.id}",
            data=_form(lamm_booking, andel_tiers=json.dumps([1, 2, 2])),
        )
        rv = logged_in_client.post(
            "/lammandel/api/send-invoices",
            json={"booking_ids": [lamm_booking.id], "season_id": season.id},
        )
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import InvoiceLamm
            inv = InvoiceLamm.query.filter_by(booking_id=lamm_booking.id).one()
            assert inv.tot_sum == 200.0 + 300.0 + 300.0
            assert inv.line_items == [
                {"quantity": 1, "unit_price": 200.0, "total": 200.0},
                {"quantity": 2, "unit_price": 300.0, "total": 600.0},
            ]
            from flask import render_template
            with app.test_request_context():
                html = render_template("invoice_pdf_template.html", invoice=inv, booking=inv.booking,
                                       timedelta=__import__("datetime").timedelta,
                                       logo_cid="logo", swish_qr_cid="swish_qr")
            assert "200.00 kr" in html and "300.00 kr" in html and "600.00 kr" in html
