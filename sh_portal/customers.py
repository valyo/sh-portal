from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify, abort
from sqlalchemy import func
from .models import Customer, Bookings, BookingsLamm
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
    booked_emails = set()
    if kind and season_id is not None:
        model = booking_models[kind]
        rows = (
            db.session.query(Customer.email)
            .join(model, model.customer_id == Customer.id)
            .filter(model.season_id == season_id)
            .all()
        )
        booked_emails = {email.lower() for (email,) in rows}

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
            'booked': c.email.lower() in booked_emails,
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
    })


@customers_bp.route('/api/customer/<int:customer_id>', methods=['POST'])
def update_customer(customer_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    customer = db.session.get(Customer, customer_id)
    if customer is None:
        abort(404)

    try:
        customer.name = request.form.get('name') or customer.name
        customer.email = request.form.get('email') or customer.email
        customer.telephone = request.form.get('telephone') or customer.telephone
        customer.address = request.form.get('address') or customer.address
        customer.postnummer = request.form.get('postnummer') or customer.postnummer
        customer.ort = request.form.get('ort') or customer.ort
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
