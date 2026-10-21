"""Tests for choosing the VAT rate (6 or 12) when sending invoices."""
import datetime

import pytest


@pytest.fixture
def lamm_booking(app, season, customer):
    from sh_portal.models import BookingsLamm
    from sh_portal import db
    with app.app_context():
        b = BookingsLamm(season_id=season.id, customer_id=customer.id, quantity=2)
        db.session.add(b)
        db.session.commit()
        db.session.refresh(b)
        yield b


def _render_pdf_html(app, invoice):
    from flask import render_template
    with app.test_request_context():
        return render_template(
            "invoice_pdf_template.html", invoice=invoice, booking=invoice.booking,
            timedelta=datetime.timedelta, logo_cid="logo", swish_qr_cid="swish_qr",
        )


def _render_email_html(app, invoice):
    from flask import render_template
    with app.test_request_context():
        return render_template(
            "invoice_template.html", invoice=invoice, booking=invoice.booking,
            timedelta=datetime.timedelta, logo_cid="logo", swish_qr_cid="swish_qr",
        )


CASES = [
    # (url, module to stub mail in, invoice model name, booking fixture, expected total)
    ("/api/send-invoices", "sh_portal.andelsbiodling", "Invoice", "booking", 200.0),
    ("/lammandel/api/send-invoices", "sh_portal.lammandel", "InvoiceLamm", "lamm_booking", 400.0),
]


@pytest.mark.parametrize("url,module,model_name,booking_fixture,total", CASES)
class TestInvoiceVat:
    def _send(self, client, monkeypatch, module, url, booking, season, **extra):
        monkeypatch.setattr(f"{module}.send_mail_using_current_config", lambda *a, **k: None)
        return client.post(url, json={"booking_ids": [booking.id], "season_id": season.id, **extra})

    def _invoice(self, app, model_name, booking):
        from sh_portal import models
        model = getattr(models, model_name)
        return model.query.filter_by(booking_id=booking.id).one()

    @pytest.mark.parametrize("rate", [6, 12])
    def test_chosen_rate_is_stored_and_used(self, request, logged_in_client, season, app, monkeypatch,
                                            url, module, model_name, booking_fixture, total, rate):
        booking = request.getfixturevalue(booking_fixture)
        rv = self._send(logged_in_client, monkeypatch, module, url, booking, season, vat_rate=rate)
        assert rv.status_code == 200
        with app.app_context():
            inv = self._invoice(app, model_name, booking)
            assert inv.vat_rate == rate
            assert inv.tot_sum == total  # prices are VAT-inclusive: total is unchanged
            assert inv.vat_net == pytest.approx(total / (1 + rate / 100))
            assert inv.vat_amount == pytest.approx(total - total / (1 + rate / 100))
            other = 6 if rate == 12 else 12
            for html in (_render_pdf_html(app, inv), _render_email_html(app, inv)):
                assert f"{rate}%" in html
                assert f"{other}%" not in html
                assert f"{inv.vat_amount:.2f} kr" in html
                assert f"{inv.vat_net:.3f} kr" in html

    def test_missing_rate_rejected(self, request, logged_in_client, season, app, monkeypatch,
                                   url, module, model_name, booking_fixture, total):
        booking = request.getfixturevalue(booking_fixture)
        rv = self._send(logged_in_client, monkeypatch, module, url, booking, season)
        assert rv.status_code == 400
        assert "select a VAT rate" in rv.get_json()["error"]
        with app.app_context():
            from sh_portal import models
            assert getattr(models, model_name).query.count() == 0

    @pytest.mark.parametrize("bad", [25, 0, "abc", None])
    def test_invalid_rate_rejected(self, request, logged_in_client, season, app, monkeypatch,
                                   url, module, model_name, booking_fixture, total, bad):
        booking = request.getfixturevalue(booking_fixture)
        rv = self._send(logged_in_client, monkeypatch, module, url, booking, season, vat_rate=bad)
        assert rv.status_code == 400
        with app.app_context():
            from sh_portal import models
            assert getattr(models, model_name).query.count() == 0
