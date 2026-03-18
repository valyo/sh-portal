"""Sales management: list, filter, stats, and andel-only view.

The sales list is loaded from the database on every request (no server-side cache).
To avoid stale data, the list response is sent with Cache-Control: no-store so the
browser does not cache it. After changing data elsewhere (e.g. deleting rows in the DB
or marking invoices paid/unpaid), refresh the page to see the current state.
"""
import json
import os
from datetime import datetime
from flask import Blueprint, current_app, render_template, redirect, url_for, session, request, flash, make_response, abort
from .models import Sale, SaleCategory, Product, Customer
from .utils import normalize_customer_name
from . import db
from sqlalchemy import func


def _get_sqlite_db_path():
    """Return the resolved absolute path of the SQLite DB file, or None if not SQLite."""
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite'):
        return None
    # sqlite:///app.db -> path is /app.db (leading slash); sqlite:///./instance/sh.db -> /./instance/sh.db
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    path = (parsed.path or '').lstrip('/')
    if not path or path == ':memory:':
        return ':memory:'
    return os.path.abspath(path)

sales_bp = Blueprint('sales', __name__)


def _build_sales_query(year=None, category_id=None, product_id=None, andel_only=False):
    """Build filtered Sale query (no order yet)."""
    query = Sale.query
    if year:
        query = query.filter(func.strftime('%Y', Sale.timestamp) == year)
    if category_id:
        query = query.filter(Sale.category_id == category_id)
    if product_id:
        query = query.filter(Sale.product_id == product_id)
    if andel_only:
        query = query.filter(Sale.invoice_id.isnot(None))
    return query


@sales_bp.route('/sales')
def list_sales():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    year = request.args.get('year')
    category_id = request.args.get('category_id', type=int)
    product_id = request.args.get('product_id', type=int)
    andel_only = request.args.get('andel_only') == '1'
    show_list = request.args.get('list') == '1'

    query = _build_sales_query(year=year, category_id=category_id, product_id=product_id, andel_only=andel_only)
    # Load full sales list only when user clicks "List sales" to avoid heavy queries by default
    sales = query.order_by(Sale.timestamp.desc()).all() if show_list else []

    categories = SaleCategory.query.order_by(SaleCategory.name).all()
    products = Product.query.order_by(Product.name).all()
    customers = Customer.query.order_by(Customer.name).all()

    years = db.session.query(func.strftime('%Y', Sale.timestamp).label('y')).distinct().order_by('y').all()
    years = [r[0] for r in years if r[0]]

    # Stats for the current filtered set (subquery to avoid loading all rows)
    base_query = _build_sales_query(year=year, category_id=category_id, product_id=product_id, andel_only=andel_only)
    subq = base_query.with_entities(Sale.id).subquery()
    total_revenue = db.session.query(func.coalesce(func.sum(Sale.unit_price * Sale.quantity), 0)).filter(
        Sale.id.in_(db.session.query(subq.c.id))
    ).scalar()
    total_revenue = float(total_revenue) if total_revenue is not None else 0
    total_count = base_query.count()

    # By year (same filters except year)
    q_year = _build_sales_query(category_id=category_id, product_id=product_id, andel_only=andel_only)
    subq_year = q_year.with_entities(Sale.id).subquery()
    by_year_rows = (
        db.session.query(
            func.strftime('%Y', Sale.timestamp).label('y'),
            func.sum(Sale.unit_price * Sale.quantity).label('revenue'),
            func.count(Sale.id).label('count'),
        )
        .filter(Sale.id.in_(db.session.query(subq_year.c.id)))
        .group_by(func.strftime('%Y', Sale.timestamp))
        .order_by('y')
        .all()
    )
    by_year = [{'year': r[0], 'revenue': float(r[1] or 0), 'count': r[2]} for r in by_year_rows if r[0]]

    # By category (same filters except category)
    q_cat = _build_sales_query(year=year, product_id=product_id, andel_only=andel_only)
    subq_cat = q_cat.with_entities(Sale.id).subquery()
    by_cat_rows = (
        db.session.query(
            SaleCategory.name,
            func.sum(Sale.unit_price * Sale.quantity).label('revenue'),
            func.count(Sale.id).label('count'),
        )
        .select_from(Sale)
        .join(SaleCategory, Sale.category_id == SaleCategory.id)
        .filter(Sale.id.in_(db.session.query(subq_cat.c.id)))
        .group_by(SaleCategory.name)
        .order_by(func.sum(Sale.unit_price * Sale.quantity).desc())
        .all()
    )
    by_cat = [{'name': r[0], 'revenue': float(r[1] or 0), 'count': r[2]} for r in by_cat_rows]

    customers_json = json.dumps([{'id': c.id, 'name': c.name, 'email': c.email} for c in customers])
    db_path = _get_sqlite_db_path()

    response = make_response(render_template(
        'sales.html',
        sales=sales,
        categories=categories,
        products=products,
        years=years,
        selected_year=year,
        selected_category_id=category_id,
        selected_product_id=product_id,
        andel_only=andel_only,
        total_revenue=total_revenue,
        total_count=total_count,
        stats_by_year=by_year,
        stats_by_category=by_cat,
        customers=customers,
        customers_json=customers_json,
        database_path=db_path,
        show_list=show_list,
        user=session.get('user'),
    ))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


@sales_bp.route('/sales/create', methods=['POST'])
def create_sale():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    date_str = request.form.get('timestamp')
    product_id = request.form.get('product_id', type=int)
    skord = (request.form.get('skord') or '').strip()
    burk_kg = request.form.get('burk_kg', type=float)
    unit_price = request.form.get('unit_price', type=float)
    quantity = request.form.get('quantity', type=int)
    consistency = (request.form.get('consistency') or 'fast').strip()
    apiary = (request.form.get('apiary') or 'Solberg').strip()
    category_id = request.form.get('category_id', type=int)
    customer_id = request.form.get('customer_id', type=int) or None
    raw_name = (request.form.get('customer_name') or '').strip() or None
    customer_name = normalize_customer_name(raw_name) if raw_name and not customer_id else None

    errors = []
    if not date_str:
        errors.append('Date is required.')
    if not product_id:
        errors.append('Product is required.')
    if not skord:
        errors.append('Skörd is required.')
    if unit_price is None:
        errors.append('Unit price is required.')
    if quantity is None or quantity < 1:
        errors.append('Quantity must be at least 1.')
    if consistency not in ('fast', 'flytande', 'fryst'):
        errors.append('Consistency must be fast, flytande, or fryst.')
    if not apiary:
        errors.append('Apiary is required.')
    if not category_id:
        errors.append('Category is required.')

    if errors:
        for msg in errors:
            flash(msg, 'error')
        return redirect(url_for('sales.list_sales'))

    try:
        ts = datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        flash('Invalid date format.', 'error')
        return redirect(url_for('sales.list_sales'))

    sale = Sale(
        timestamp=ts,
        product_id=product_id,
        skord=skord,
        burk_kg=burk_kg,
        unit_price=unit_price,
        quantity=quantity,
        consistency=consistency,
        apiary=apiary,
        category_id=category_id,
        customer_id=customer_id,
        customer_name=customer_name if not customer_id else None,
        invoice_id=None,
    )
    db.session.add(sale)
    db.session.commit()
    flash('Sale created successfully.', 'success')
    return redirect(url_for('sales.list_sales'))


def _sale_form_data(request):
    """Parse and return (timestamp, product_id, skord, burk_kg, ...) from request.form. Returns None for optional fields."""
    date_str = request.form.get('timestamp')
    product_id = request.form.get('product_id', type=int)
    skord = (request.form.get('skord') or '').strip()
    burk_kg = request.form.get('burk_kg', type=float)
    unit_price = request.form.get('unit_price', type=float)
    quantity = request.form.get('quantity', type=int)
    consistency = (request.form.get('consistency') or 'fast').strip()
    apiary = (request.form.get('apiary') or 'Solberg').strip()
    category_id = request.form.get('category_id', type=int)
    customer_id = request.form.get('customer_id', type=int) or None
    raw_name = (request.form.get('customer_name') or '').strip() or None
    customer_name = normalize_customer_name(raw_name) if raw_name and not customer_id else None
    return (date_str, product_id, skord, burk_kg, unit_price, quantity, consistency, apiary, category_id, customer_id, customer_name)


def _validate_sale_form(date_str, product_id, skord, unit_price, quantity, consistency, apiary, category_id):
    """Return list of error messages, or empty list if valid."""
    errors = []
    if not date_str:
        errors.append('Date is required.')
    if not product_id:
        errors.append('Product is required.')
    if not skord:
        errors.append('Skörd is required.')
    if unit_price is None:
        errors.append('Unit price is required.')
    if quantity is None or quantity < 1:
        errors.append('Quantity must be at least 1.')
    if consistency not in ('fast', 'flytande', 'fryst'):
        errors.append('Consistency must be fast, flytande, or fryst.')
    if not apiary:
        errors.append('Apiary is required.')
    if not category_id:
        errors.append('Category is required.')
    return errors


@sales_bp.route('/sales/<int:sale_id>/edit', methods=['POST'])
def edit_sale(sale_id):
    if not session.get('user'):
        return redirect(url_for('main.home'))
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        abort(404)
    if sale.invoice_id is not None:
        flash('Sales created from an invoice cannot be edited.', 'error')
        return redirect(url_for('sales.list_sales'))

    # Update from form
    (date_str, product_id, skord, burk_kg, unit_price, quantity, consistency, apiary, category_id, customer_id, customer_name) = _sale_form_data(request)
    errors = _validate_sale_form(date_str, product_id, skord, unit_price, quantity, consistency, apiary, category_id)
    if errors:
        for msg in errors:
            flash(msg, 'error')
        return redirect(url_for('sales.list_sales', list=1))
    try:
        ts = datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        flash('Invalid date format.', 'error')
        return redirect(url_for('sales.list_sales', list=1))

    sale.timestamp = ts
    sale.product_id = product_id
    sale.skord = skord
    sale.burk_kg = burk_kg
    sale.unit_price = unit_price
    sale.quantity = quantity
    sale.consistency = consistency
    sale.apiary = apiary
    sale.category_id = category_id
    sale.customer_id = customer_id
    sale.customer_name = customer_name if not customer_id else None
    db.session.commit()
    flash('Sale updated.', 'success')
    return redirect(url_for('sales.list_sales'))


@sales_bp.route('/sales/<int:sale_id>/delete', methods=['POST'])
def delete_sale(sale_id):
    if not session.get('user'):
        return redirect(url_for('main.home'))
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        abort(404)
    if sale.invoice_id is not None:
        flash('Sales created from an invoice cannot be deleted.', 'error')
        return redirect(url_for('sales.list_sales'))
    db.session.delete(sale)
    db.session.commit()
    flash('Sale deleted.', 'success')
    return redirect(url_for('sales.list_sales'))
