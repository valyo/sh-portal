"""Tests for deleting an invoice (row, linked sale and saved PDF)."""
import os
from pathlib import Path

import pytest


@pytest.fixture
def invoices_dir(app):
    """The app's (temporary) invoices folder, from app.config['INVOICES_DIR']."""
    return Path(app.config["INVOICES_DIR"])


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 test")
    return path


class TestDeleteInvoiceAndelsbiodling:
    def test_unauthorized_returns_401(self, client, invoice):
        assert client.post(f"/api/invoice/{invoice.id}/delete").status_code == 401

    def test_not_found_returns_404(self, logged_in_client):
        assert logged_in_client.post("/api/invoice/99999/delete").status_code == 404

    def test_removes_invoice_and_pdf_but_not_others(self, logged_in_client, invoice, app, invoices_dir):
        pdf = _touch(invoices_dir / "andelsbiodling" / "2025" / "INV-TEST-001.pdf")
        other_year_copy = _touch(invoices_dir / "andelsbiodling" / "2024" / "INV-TEST-001.pdf")
        other_invoice = _touch(invoices_dir / "andelsbiodling" / "2025" / "INV-TEST-002.pdf")
        lamm_same_name = _touch(invoices_dir / "lammandel" / "2025" / "INV-TEST-001.pdf")

        rv = logged_in_client.post(f"/api/invoice/{invoice.id}/delete")
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

        with app.app_context():
            from sh_portal.models import Invoice
            from sh_portal import db
            assert db.session.get(Invoice, invoice.id) is None
        assert not pdf.exists()
        assert not other_year_copy.exists()
        assert other_invoice.exists()
        assert lamm_same_name.exists()

    def test_missing_pdf_is_not_an_error(self, logged_in_client, invoice, invoices_dir):
        rv = logged_in_client.post(f"/api/invoice/{invoice.id}/delete")
        assert rv.status_code == 200

    def test_linked_sale_is_deleted_too(self, logged_in_client, sale_from_invoice, invoice, app, invoices_dir):
        sale_id = sale_from_invoice.id
        rv = logged_in_client.post(f"/api/invoice/{invoice.id}/delete")
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Sale
            from sh_portal import db
            assert db.session.get(Sale, sale_id) is None

    def test_pdf_removal_failure_is_reported(self, logged_in_client, invoice, app, invoices_dir, monkeypatch):
        _touch(invoices_dir / "andelsbiodling" / "2025" / "INV-TEST-001.pdf")

        def boom(path):
            raise PermissionError("denied")
        monkeypatch.setattr(os, "remove", boom)
        rv = logged_in_client.post(f"/api/invoice/{invoice.id}/delete")
        assert rv.status_code == 500
        assert "PDF could not be removed" in rv.get_json()["error"]

    def test_booking_can_be_invoiced_again(self, logged_in_client, invoice, booking, season, app, invoices_dir, monkeypatch,
                                           fake_invoice_pdf):
        logged_in_client.post(f"/api/invoice/{invoice.id}/delete")
        monkeypatch.setattr("sh_portal.andelsbiodling.send_mail_using_current_config", lambda *a, **k: None)
        rv = logged_in_client.post("/api/send-invoices", json={"booking_ids": [booking.id], "season_id": season.id, "vat_rate": 12})
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Invoice
            assert Invoice.query.filter_by(booking_id=booking.id).count() == 1


class TestDeleteInvoiceLammandel:
    def test_unauthorized_returns_401(self, client, lamm_invoice):
        assert client.post(f"/lammandel/api/invoice/{lamm_invoice.id}/delete").status_code == 401

    def test_not_found_returns_404(self, logged_in_client):
        assert logged_in_client.post("/lammandel/api/invoice/99999/delete").status_code == 404

    def test_removes_invoice_and_pdf_but_not_others(self, logged_in_client, lamm_invoice, app, invoices_dir):
        pdf = _touch(invoices_dir / "lammandel" / "2025" / "F-LAMM-2025-0001.pdf")
        other_invoice = _touch(invoices_dir / "lammandel" / "2025" / "F-LAMM-2025-0002.pdf")
        honey_same_name = _touch(invoices_dir / "andelsbiodling" / "2025" / "F-LAMM-2025-0001.pdf")

        rv = logged_in_client.post(f"/lammandel/api/invoice/{lamm_invoice.id}/delete")
        assert rv.status_code == 200

        with app.app_context():
            from sh_portal.models import InvoiceLamm
            from sh_portal import db
            assert db.session.get(InvoiceLamm, lamm_invoice.id) is None
        assert not pdf.exists()
        assert other_invoice.exists()
        assert honey_same_name.exists()
