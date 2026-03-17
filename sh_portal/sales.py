"""Sales management: list, filter, stats, and andel-only view."""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from .models import Sale, SaleCategory, Product, Customer
from . import db
from sqlalchemy import func

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

    query = _build_sales_query(year=year, category_id=category_id, product_id=product_id, andel_only=andel_only)
    sales = query.order_by(Sale.timestamp.desc()).all()

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

    return render_template(
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
        user=session.get('user'),
    )


@sales_bp.route('/sales/create', methods=['POST'])
def create_sale():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    date_str = request.form.get('timestamp')
    product_id = request.form.get('product_id', type=int)
    skord = (request.form.get('skord') or '').strip()
    burk = (request.form.get('burk') or '').strip() or None
    unit_price = request.form.get('unit_price', type=float)
    quantity = request.form.get('quantity', type=int)
    consistency = (request.form.get('consistency') or 'fast').strip()
    apiary = (request.form.get('apiary') or 'Solberg').strip()
    category_id = request.form.get('category_id', type=int)
    customer_id = request.form.get('customer_id', type=int) or None
    customer_name = (request.form.get('customer_name') or '').strip() or None

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
        burk=burk,
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
