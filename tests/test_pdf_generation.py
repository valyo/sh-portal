"""WeasyPrint smoke tests: certificate and invoice templates must produce a PDF."""
import os


class TestPdfGeneration:
    def test_certificate_pdf_starts_with_pdf_header(self, app, booking, season, tmp_path):
        from sh_portal.utils import build_certificate_template_context, generate_pdf_weasyprint

        template = os.path.join(app.root_path, "templates", "certificate_pdf_template.html")
        out = tmp_path / "certificate.pdf"
        with app.app_context():
            ok = generate_pdf_weasyprint(
                template,
                str(out),
                build_certificate_template_context(booking, season),
                base_url=app.root_path,
            )
        assert ok is True
        assert out.read_bytes()[:4] == b"%PDF"

    def test_invoice_pdf_starts_with_pdf_header(self, app, invoice, tmp_path):
        from datetime import timedelta

        from flask import render_template

        from sh_portal.utils import generate_invoice_pdf

        out = tmp_path / "invoice.pdf"
        with app.app_context(), app.test_request_context():
            html = render_template(
                "invoice_pdf_template.html",
                invoice=invoice,
                booking=invoice.booking,
                timedelta=timedelta,
                logo_cid="logo",
                swish_qr_cid="swish_qr",
            )
            ok = generate_invoice_pdf(html, str(out))
        assert ok is True
        assert out.read_bytes()[:4] == b"%PDF"

    def test_lammandel_invoice_pdf_with_mixed_prices(self, app, lamm_invoice, tmp_path):
        """The Lammandel invoice has its own template branch (one row per distinct price)."""
        import json
        from datetime import timedelta

        from flask import render_template

        from sh_portal import db
        from sh_portal.models import InvoiceLamm
        from sh_portal.utils import generate_invoice_pdf

        out = tmp_path / "invoice_lamm.pdf"
        with app.app_context(), app.test_request_context():
            invoice = db.session.get(InvoiceLamm, lamm_invoice.id)
            invoice.season.price_lamm_2 = 300.0
            invoice.booking.andel_tiers = json.dumps([1, 2])
            invoice.vat_rate = 6
            html = render_template(
                "invoice_pdf_template.html",
                invoice=invoice,
                booking=invoice.booking,
                timedelta=timedelta,
                logo_cid="logo",
                swish_qr_cid="swish_qr",
            )
            ok = generate_invoice_pdf(html, str(out))
        assert ok is True
        assert out.read_bytes()[:4] == b"%PDF"

