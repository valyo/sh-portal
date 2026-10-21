"""Tests for choosing the VAT rate (6 or 12) when sending invoices."""
import datetime
import os

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


@pytest.fixture(autouse=True)
def _no_real_pdf(fake_invoice_pdf):
    """These tests are about VAT, not PDF rendering (see tests/test_pdf_generation.py)."""


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
            assert inv.vat_net == round(total / (1 + rate / 100), 2)
            assert inv.vat_net + inv.vat_amount == pytest.approx(total, abs=1e-9)
            other = 6 if rate == 12 else 12
            for html in (_render_pdf_html(app, inv), _render_email_html(app, inv)):
                assert f"{rate}%" in html
                assert f"{other}%" not in html
                assert f"{inv.vat_amount:.2f} kr" in html
                assert f"{inv.vat_net:.2f} kr" in html

    def test_pdf_is_saved_under_configured_invoices_dir(self, request, logged_in_client, season, app, monkeypatch,
                                                         fake_invoice_pdf, url, module, model_name,
                                                         booking_fixture, total):
        booking = request.getfixturevalue(booking_fixture)
        rv = self._send(logged_in_client, monkeypatch, module, url, booking, season, vat_rate=12)
        assert rv.status_code == 200
        kind = module.rsplit(".", 1)[-1]
        with app.app_context():
            invoice_number = self._invoice(app, model_name, booking).invoice_id
        expected = os.path.join(app.config["INVOICES_DIR"], kind, str(season.year), f"{invoice_number}.pdf")
        assert fake_invoice_pdf == [expected]
        assert os.path.isfile(expected)

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

    def test_pdf_failure_does_not_send_or_keep_invoice(self, request, logged_in_client, season, app,
                                                       monkeypatch, url, module, model_name,
                                                       booking_fixture, total):
        booking = request.getfixturevalue(booking_fixture)
        sent = []
        monkeypatch.setattr(f"{module}.generate_invoice_pdf", lambda *a, **k: False)
        monkeypatch.setattr(f"{module}.send_mail_using_current_config", lambda *a, **k: sent.append(1))
        rv = logged_in_client.post(
            url,
            json={"booking_ids": [booking.id], "season_id": season.id, "vat_rate": 12},
        )
        assert rv.status_code == 200
        assert sent == []
        data = rv.get_json()
        assert data.get("errors")
        assert any("PDF" in err for err in data["errors"])
        with app.app_context():
            from sh_portal import models
            assert getattr(models, model_name).query.filter_by(booking_id=booking.id).count() == 0


class TestVatRounding:
    """Net + VAT must add up to the total exactly as printed (to the öre)."""

    @pytest.mark.parametrize("rate", [6, 12])
    @pytest.mark.parametrize("total", [100.0, 250.0, 333.33, 1350.0, 4200.0, 0.01, 19999.99])
    def test_net_plus_vat_equals_total(self, rate, total):
        from sh_portal.models import Invoice
        inv = Invoice(tot_sum=total, vat_rate=rate)
        assert round(inv.vat_net + inv.vat_amount, 2) == total
        assert inv.vat_net == round(inv.vat_net, 2)
        assert inv.vat_amount == round(inv.vat_amount, 2)

    def test_example_that_used_to_be_off_by_an_ore(self):
        from sh_portal.models import Invoice
        inv = Invoice(tot_sum=250.0, vat_rate=6)
        assert (inv.vat_net, inv.vat_amount) == (235.85, 14.15)


class TestVatRateIsAlwaysExplicit:
    def test_invoice_without_vat_rate_is_rejected_by_the_database(self, app, season, booking):
        import sqlalchemy
        from sh_portal import db
        from sh_portal.models import Invoice
        with app.app_context():
            db.session.add(Invoice(season_id=season.id, booking_id=booking.id, invoice_id="NO-VAT", quantity=1, tot_sum=1.0))
            with pytest.raises(sqlalchemy.exc.IntegrityError):
                db.session.commit()
            db.session.rollback()

    @pytest.mark.parametrize("payload,expected", [
        ({"vat_rate": 6}, 6), ({"vat_rate": "12"}, 12), ({"vat_rate": 12.0}, 12),
    ])
    def test_parse_vat_rate_accepts_the_allowed_rates(self, payload, expected):
        from sh_portal.utils import parse_vat_rate
        assert parse_vat_rate(payload) == (expected, None)

    @pytest.mark.parametrize("payload", [{}, None, {"vat_rate": None}, {"vat_rate": ""}, {"vat_rate": "x"}, {"vat_rate": 25}, {"vat_rate": 0}])
    def test_parse_vat_rate_rejects_everything_else(self, payload):
        from sh_portal.utils import parse_vat_rate
        rate, error = parse_vat_rate(payload)
        assert rate is None and "select a VAT rate" in error

