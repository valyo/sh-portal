from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify, abort
from sqlalchemy import func
from .models import Customer, Bookings, BookingsLamm
from .utils import clean_optional, CUSTOMER_DETAIL_FIELDS, CUSTOMER_NAME_MAX
from . import db

customers_bp = Blueprint('customers', __name__)


@customers_bp.route('/customers')
def list_customers():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    customers_list = db.session.query(Customer).order_by(Customer.name).all()
    return render_template('customers.html', customers=customers_list, user=session.get('user'))


@customers_bp.route('/api/customers')
def customers_json():
    """All customers for the booking form's customer picker, sorted by name.

    With ?kind=andelsbiodling|lammandel&season_id=N each customer also gets `booked`: True if
    someone with that email (case-insensitive) already has a booking of that kind in the season.
    """
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking_models = {'andelsbiodling': Bookings, 'lammandel': BookingsLamm}
    kind = request.args.get('kind')
    if kind is not None and kind not in booking_models:
        return jsonify({'error': 'kind must be andelsbiodling or lammandel'}), 400

    season_id = request.args.get('season_id', type=int)
    booked_ids = set()
    booked_emails = set()
    if kind and season_id is not None:
        model = booking_models[kind]
        rows = (
            db.session.query(Customer.id, Customer.email)
            .join(model, model.customer_id == Customer.id)
            .filter(model.season_id == season_id)
            .all()
        )
        booked_ids = {cid for cid, _ in rows}
        booked_emails = {email.lower() for _, email in rows if email}

    customers = db.session.query(Customer).order_by(func.lower(Customer.name), Customer.id).all()
    return jsonify([
        {
            'id': c.id,
            'name': c.name,
            'email': c.email,
            'telephone': c.telephone,
            'address': c.address,
            'postnummer': c.postnummer,
            'ort': c.ort,
            'booked': c.id in booked_ids or bool(c.email and c.email.lower() in booked_emails),
        }
        for c in customers
    ])


@customers_bp.route('/api/customer/<int:customer_id>')
def get_customer(customer_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    customer = db.session.get(Customer, customer_id)
    if customer is None:
        abort(404)

    # Build list of seasons they have bookings in (andelsbiodling + lammandel)
    bookings_info = []
    for b in customer.bookings:
        bookings_info.append({
            'season_id': b.season_id,
            'year': b.season.year,
            'type': 'andelsbiodling',
            'booking_id': b.id,
        })
    for b in customer.bookings_lamm:
        bookings_info.append({
            'season_id': b.season_id,
            'year': b.season.year,
            'type': 'lammandel',
            'booking_id': b.id,
        })
    # Sort by year desc then by type
    bookings_info.sort(key=lambda x: (-int(x['year']) if x['year'].isdigit() else 0, x['type']))

    return jsonify({
        'id': customer.id,
        'name': customer.name,
        'email': customer.email,
        'telephone': customer.telephone,
        'address': customer.address,
        'postnummer': customer.postnummer,
        'ort': customer.ort,
        'bookings': bookings_info,
        'sales_count': len(customer.sales),
    })


def _customer_form_values():
    """(name, {optional detail: cleaned value or None}) from the posted form."""
    name = (request.form.get('name') or '').strip()
    return name, {f: clean_optional(request.form.get(f)) for f in CUSTOMER_DETAIL_FIELDS}


def _customer_error(name, values, customer=None):
    """First problem with the submitted customer data, or None. `customer` is the one being edited."""
    if not name:
        return 'Name is required.'
    if len(name) > CUSTOMER_NAME_MAX:
        return f'The name is too long (at most {CUSTOMER_NAME_MAX} characters).'
    if customer is not None and (customer.bookings or customer.bookings_lamm):
        missing = [f for f in CUSTOMER_DETAIL_FIELDS if not values[f]]
        if missing:
            return ('This customer has bookings, so invoices and certificates need their details. '
                    f'Missing: {", ".join(missing)}.')
    email = values['email']
    if email:
        if '@' not in email:
            return 'The email address does not look valid.'
        clash = db.session.query(Customer).filter(
            func.lower(Customer.email) == email.lower(),
            Customer.id != (customer.id if customer is not None else 0),
        ).first()
        if clash:
            return f'{clash.name} already has this email address.'
    return None


@customers_bp.route('/api/customer', methods=['POST'])
def create_customer():
    """Add a customer by hand. Only the name is required."""
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    name, values = _customer_form_values()
    error = _customer_error(name, values)
    if error:
        return jsonify({'success': False, 'message': error}), 400
    customer = Customer(name=name, **values)
    db.session.add(customer)
    db.session.commit()
    return jsonify({'success': True, 'customer_id': customer.id})


@customers_bp.route('/api/customer/<int:customer_id>', methods=['POST'])
def update_customer(customer_id):
    """Update a customer. Only the name is required; an emptied optional field is cleared."""
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    customer = db.session.get(Customer, customer_id)
    if customer is None:
        abort(404)

    name, values = _customer_form_values()
    error = _customer_error(name, values, customer)
    if error:
        return jsonify({'success': False, 'message': error}), 400
    try:
        customer.name = name
        for field, value in values.items():
            setattr(customer, field, value)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@customers_bp.route('/api/customer/<int:customer_id>/delete', methods=['POST'])
def delete_customer(customer_id):
    """Delete a customer who has no bookings.

    Bookings (and their invoices and certificates) cannot exist without a customer, so a
    customer with bookings is refused. Sales do not need one: they stay in the sales list,
    keep the customer's name as plain text, and are simply no longer linked.
    """
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    customer = db.session.get(Customer, customer_id)
    if customer is None:
        abort(404)

    booked = sorted(
        {f"{b.season.year} Andelsbiodling" for b in customer.bookings}
        | {f"{b.season.year} Lammandel" for b in customer.bookings_lamm}
    )
    if booked:
        return jsonify({
            'success': False,
            'message': f'{customer.name} has bookings ({", ".join(booked)}), and bookings need a customer, '
                       'so this customer cannot be deleted.',
        }), 400

    try:
        sales_kept = len(customer.sales)
        for sale in customer.sales:
            sale.customer_name = customer.name
            sale.customer_id = None
        name = customer.name
        db.session.delete(customer)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'message': f'Customer {name} deleted', 'sales_kept': sales_kept})

