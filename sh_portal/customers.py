from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify, abort
from .models import Customer
from . import db

customers_bp = Blueprint('customers', __name__)


@customers_bp.route('/customers')
def list_customers():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    customers_list = db.session.query(Customer).order_by(Customer.name).all()
    return render_template('customers.html', customers=customers_list, user=session.get('user'))


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
