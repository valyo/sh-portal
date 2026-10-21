"""Tests for the INVOICES_DIR setting."""
import os


def _fresh_app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from sh_portal import create_app
    return create_app()


class TestInvoicesDir:
    def test_defaults_to_invoices_folder_next_to_the_package(self, monkeypatch):
        monkeypatch.delenv("INVOICES_DIR", raising=False)
        app = _fresh_app(monkeypatch)
        assert app.config["INVOICES_DIR"] == os.path.abspath(os.path.join(app.root_path, "..", "invoices"))

    def test_can_be_set_from_the_environment(self, monkeypatch, tmp_path):
        monkeypatch.setenv("INVOICES_DIR", str(tmp_path / "elsewhere"))
        app = _fresh_app(monkeypatch)
        assert app.config["INVOICES_DIR"] == str(tmp_path / "elsewhere")

    def test_test_app_never_uses_the_real_invoices_folder(self, app):
        real = os.path.abspath(os.path.join(app.root_path, "..", "invoices"))
        assert app.config["INVOICES_DIR"] != real
        assert not app.config["INVOICES_DIR"].startswith(real + os.sep)
