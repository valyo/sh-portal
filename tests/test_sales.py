"""Tests for Sales list, create, edit, delete endpoints."""


class TestListSales:
    """GET /sales"""

    def test_unauthorized_redirects_to_home(self, client):
        rv = client.get("/sales", follow_redirects=False)
        assert rv.status_code in (302, 303)
        assert "/" in rv.location or rv.location.endswith("/")

    def test_logged_in_returns_200(self, logged_in_client, product, sale_category):
        rv = logged_in_client.get("/sales")
        assert rv.status_code == 200
        assert b"Sales" in rv.data

    def test_cache_control_headers_set(self, logged_in_client):
        rv = logged_in_client.get("/sales")
        assert rv.status_code == 200
        assert "no-store" in rv.headers.get("Cache-Control", "").lower() or "no-cache" in rv.headers.get("Cache-Control", "").lower()

    def test_show_list_param_loads_sales(self, logged_in_client, sale):
        rv = logged_in_client.get("/sales?list=1")
        assert rv.status_code == 200
        assert str(sale.skord).encode() in rv.data or b"List sales" in rv.data


class TestCreateSale:
    """POST /sales/create"""

    def test_unauthorized_redirects(self, client, product, sale_category):
        rv = client.post(
            "/sales/create",
            data={
                "timestamp": "2025-03-15",
                "product_id": product.id,
                "skord": "2025",
                "unit_price": "100",
                "quantity": "1",
                "consistency": "fast",
                "apiary": "Solberg",
                "category_id": sale_category.id,
            },
            follow_redirects=False,
        )
        assert rv.status_code in (302, 303)

    def test_success_creates_sale(self, logged_in_client, app, product, sale_category):
        rv = logged_in_client.post(
            "/sales/create",
            data={
                "timestamp": "2025-03-15",
                "product_id": product.id,
                "skord": "2025",
                "unit_price": "100",
                "quantity": "2",
                "consistency": "fast",
                "apiary": "Solberg",
                "category_id": sale_category.id,
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Sale
            from sh_portal import db
            sales = Sale.query.filter_by(skord="2025").all()
            assert len(sales) >= 1
            s = sales[-1]
            assert s.unit_price == 100.0
            assert s.quantity == 2
            assert s.invoice_id is None

    def test_validation_error_redirects(self, logged_in_client, product, sale_category):
        rv = logged_in_client.post(
            "/sales/create",
            data={
                "timestamp": "",
                "product_id": product.id,
                "skord": "2025",
                "unit_price": "100",
                "quantity": "1",
                "consistency": "fast",
                "apiary": "Solberg",
                "category_id": sale_category.id,
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200


class TestEditSale:
    """POST /sales/<id>/edit"""

    def test_unauthorized_redirects(self, client, sale):
        rv = client.post(
            f"/sales/{sale.id}/edit",
            data={
                "timestamp": "2025-03-20",
                "product_id": sale.product_id,
                "skord": "2025",
                "unit_price": "110",
                "quantity": "3",
                "consistency": "fast",
                "apiary": "Solberg",
                "category_id": sale.category_id,
            },
            follow_redirects=False,
        )
        assert rv.status_code in (302, 303)

    def test_not_found_returns_404(self, logged_in_client, product, sale_category):
        rv = logged_in_client.post(
            "/sales/99999/edit",
            data={
                "timestamp": "2025-03-20",
                "product_id": product.id,
                "skord": "2025",
                "unit_price": "110",
                "quantity": "3",
                "consistency": "fast",
                "apiary": "Solberg",
                "category_id": sale_category.id,
            },
            follow_redirects=False,
        )
        assert rv.status_code == 404

    def test_success_updates_sale(self, logged_in_client, app, sale):
        rv = logged_in_client.post(
            f"/sales/{sale.id}/edit",
            data={
                "timestamp": "2025-03-20",
                "product_id": sale.product_id,
                "skord": "2025",
                "unit_price": "110",
                "quantity": "3",
                "consistency": "flytande",
                "apiary": "Solberg",
                "category_id": sale.category_id,
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Sale
            from sh_portal import db
            s = db.session.get(Sale, sale.id)
            assert s.unit_price == 110.0
            assert s.quantity == 3
            assert s.consistency == "flytande"

    def test_invoice_sale_edit_redirects_with_error(self, logged_in_client, sale_from_invoice, product, sale_category):
        """Editing a sale created from an invoice is not allowed."""
        rv = logged_in_client.post(
            f"/sales/{sale_from_invoice.id}/edit",
            data={
                "timestamp": "2025-03-20",
                "product_id": product.id,
                "skord": "2025",
                "unit_price": "110",
                "quantity": "1",
                "consistency": "fast",
                "apiary": "Solberg",
                "category_id": sale_category.id,
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        assert b"cannot be edited" in rv.data or b"Sales created from an invoice" in rv.data


class TestDeleteSale:
    """POST /sales/<id>/delete"""

    def test_unauthorized_redirects(self, client, sale):
        rv = client.post(f"/sales/{sale.id}/delete", follow_redirects=False)
        assert rv.status_code in (302, 303)

    def test_not_found_returns_404(self, logged_in_client):
        rv = logged_in_client.post("/sales/99999/delete", follow_redirects=False)
        assert rv.status_code == 404

    def test_success_deletes_sale(self, logged_in_client, app, sale):
        sid = sale.id
        rv = logged_in_client.post(f"/sales/{sid}/delete", follow_redirects=True)
        assert rv.status_code == 200
        with app.app_context():
            from sh_portal.models import Sale
            from sh_portal import db
            assert db.session.get(Sale, sid) is None

    def test_invoice_sale_delete_redirects_with_error(self, logged_in_client, app, sale_from_invoice):
        """Deleting a sale created from an invoice is not allowed."""
        sid = sale_from_invoice.id
        rv = logged_in_client.post(f"/sales/{sid}/delete", follow_redirects=True)
        assert rv.status_code == 200
        assert b"cannot be deleted" in rv.data or b"Sales created from an invoice" in rv.data
        with app.app_context():
            from sh_portal.models import Sale
            from sh_portal import db
            assert db.session.get(Sale, sid) is not None
