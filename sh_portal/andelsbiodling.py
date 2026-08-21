from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify, send_file, abort
from .models import Season, Bookings, Invoice, Sale, Product, SaleCategory
from . import db
import pandas as pd
from datetime import datetime, timedelta
import re
import os
from .utils import (
    import_bookings_from_sheet, generate_invoice_pdf, get_sheet_data, extract_sheet_id,
    format_exception_location, get_effective_mail_backend_with_source,
    get_mail_connection_params, send_mail_using_current_config,
    write_certificate_pdf_to_disk, certificate_download_filename, send_booking_certificate_email,
)
from flask_mail import Message

andelsbiodling = Blueprint('andelsbiodling', __name__)

@andelsbiodling.route('/api/booking/<int:booking_id>/certificate', methods=['GET'])
def generate_certificate(booking_id):
    """Download certificate PDF (optional; primary flow is POST …/certificate/send)."""
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = db.session.get(Bookings, booking_id)
    if booking is None:
        abort(404)
    season = booking.season

    ok, pdf_path = write_certificate_pdf_to_disk(booking, season, is_lamm=False)
    if ok:
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=certificate_download_filename(booking, season),
        )
    return jsonify({'error': 'Failed to generate certificate'}), 500


@andelsbiodling.route('/api/booking/<int:booking_id>/certificate/send', methods=['POST'])
def send_certificate(booking_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = db.session.get(Bookings, booking_id)
    if booking is None:
        abort(404)
    season = booking.season

    ok, err = send_booking_certificate_email(booking, season, is_lamm=False)
    if ok:
        booking.certificate_sent_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': f'Certificate sent to {booking.email}.'})
    return jsonify({'success': False, 'error': err or 'Failed to send certificate'}), 500

@andelsbiodling.route('/andelsbiodling/import-bookings', methods=['POST'])
def import_bookings():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    season_id = request.form.get('season_id')
    if not season_id:
        flash('Season ID is required.', 'error')
        return redirect(url_for('andelsbiodling.index'))

    season = db.session.get(Season, int(season_id))
    if season is None:
        abort(404)
    sheet_link = season.google_sheets_link_honey
    range_name = season.sheet_range_honey

    if not sheet_link or not range_name:
        flash('Google Sheet link and range are not configured for this season.', 'error')
        return redirect(url_for('andelsbiodling.index', season_id=season_id))

    try:
        sheet_id = extract_sheet_id(sheet_link)
        data = get_sheet_data(sheet_id, range_name)
        if not data:
            flash('The Google Sheet range is empty or no data was found.', 'error')
            return redirect(url_for('andelsbiodling.index', season_id=season_id))

        success = import_bookings_from_sheet(
            db=db,
            BookingsModel=Bookings,
            season_id=season_id,
            sheet_data=data
        )
        flash(f'Successfully imported bookings from Google Sheet.', 'success')
        return redirect(url_for('andelsbiodling.index', season_id=season_id))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing bookings: {str(e)}")
        flash(f'An error occurred while importing bookings: {str(e)}', 'error')

    return redirect(url_for('andelsbiodling.index', season_id=season_id))

@andelsbiodling.route('/andelsbiodling', methods=['GET', 'POST'])
def index():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    seasons = Season.query.order_by(Season.year.desc()).all()
    selected_season_id = request.form.get('season_id') or request.args.get('season_id')
    selected_season = None

    if selected_season_id:
        selected_season = db.session.get(Season, int(selected_season_id))
    elif seasons:
        selected_season = seasons[0]

    # Fetch bookings and invoices for the selected season
    bookings = []
    invoices = {}
    if selected_season:
        bookings = Bookings.query.filter_by(season_id=selected_season.id).all()
        # Create a dictionary of invoices by booking_id
        invoices = {invoice.booking_id: invoice for invoice in Invoice.query.filter_by(season_id=selected_season.id).all()}

    return render_template(
        'bookings_base.html',
        user=session.get('user'),
        seasons=seasons,
        selected_season=selected_season,
        bookings=bookings,
        invoices=invoices,  # Pass invoices as a dictionary
        page_title="Andelsbiodling",
        import_url=url_for('andelsbiodling.import_bookings')
    )

@andelsbiodling.route('/api/booking/<int:booking_id>', methods=['GET'])
def get_booking(booking_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = db.session.get(Bookings, booking_id)
    if booking is None:
        abort(404)
    # Check if there is a paid invoice for this booking
    invoice = Invoice.query.filter_by(booking_id=booking.id).first()
    is_paid = invoice.date_payed is not None if invoice else False

    return jsonify({
        'id': booking.id,
        'name': booking.name,
        'email': booking.email,
        'telephone': booking.telephone,
        'address': booking.address,
        'postnummer': booking.postnummer,
        'ort': booking.ort,
        'message': booking.message,
        'quantity': booking.quantity,
        'certificate_name': booking.certificate_name,
        'certificate_quantity': booking.certificate_quantity,
        'certificate_sent_at': booking.certificate_sent_at.isoformat() if booking.certificate_sent_at else None,
        'delivered_at': booking.delivered_at.isoformat() if booking.delivered_at else None,
        'is_paid': is_paid
    })

@andelsbiodling.route('/api/booking/<int:booking_id>', methods=['POST'])
def update_booking(booking_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = db.session.get(Bookings, booking_id)
    if booking is None:
        abort(404)

    try:
        booking.customer.name = request.form.get('name')
        booking.customer.email = request.form.get('email')
        booking.customer.telephone = request.form.get('telephone')
        booking.customer.address = request.form.get('address')
        booking.customer.postnummer = request.form.get('postnummer')
        booking.customer.ort = request.form.get('ort')
        booking.message = request.form.get('message')
        booking.quantity = int(request.form.get('quantity'))
        booking.certificate_name = request.form.get('certificate_name')
        cert_qty = request.form.get('certificate_quantity')
        booking.certificate_quantity = int(cert_qty) if cert_qty else None

        cert_mark = request.form.get('certificate_sent')
        if cert_mark == '1':
            if booking.certificate_sent_at is None:
                booking.certificate_sent_at = datetime.utcnow()
        elif cert_mark == '0':
            booking.certificate_sent_at = None

        delivered_mark = request.form.get('delivered')
        if delivered_mark == '1':
            if booking.delivered_at is None:
                booking.delivered_at = datetime.utcnow()
        elif delivered_mark == '0':
            booking.delivered_at = None

        db.session.commit()
        flash('Booking updated successfully', 'success')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@andelsbiodling.route('/api/send-invoices', methods=['POST'])
def send_invoices():
    if not session.get('user'):
        current_app.logger.error("Unauthorized attempt to send invoices")
        return jsonify({'error': 'Unauthorized'}), 401

    booking_ids = request.json.get('booking_ids', [])
    season_id = request.json.get('season_id')
    current_app.logger.info(f"Received request to send invoices for booking IDs: {booking_ids} in season: {season_id}")

    if not booking_ids:
        current_app.logger.error("No booking IDs provided")
        return jsonify({'error': 'No bookings selected'}), 400

    if not season_id:
        current_app.logger.error("No season ID provided")
        return jsonify({'error': 'No season selected'}), 400

    season = db.session.get(Season, season_id)
    if not season:
        current_app.logger.error(f"Season {season_id} not found")
        return jsonify({'error': 'Season not found'}), 400

    bookings = Bookings.query.filter(
        Bookings.id.in_(booking_ids),
        Bookings.season_id == season_id
    ).all()
    current_app.logger.info(f"Found {len(bookings)} bookings for season {season_id}")

    sent_count = 0
    skipped_count = 0
    errors = []

    try:
        for booking in bookings:
            current_app.logger.info(f"Processing booking {booking.id} for {booking.name}")

            # Check if invoice already exists
            existing_invoice = Invoice.query.filter_by(booking_id=booking.id).first()
            if existing_invoice:
                current_app.logger.info(f"Invoice already exists for booking {booking.id}")
                skipped_count += 1
                continue

            # Generate a unique invoice ID
            invoice_id = f"F-{season.year}-{booking.id:04d}"
            current_app.logger.info(f"Generated invoice ID: {invoice_id}")

            try:
                # Create new invoice
                invoice = Invoice(
                    booking_id=booking.id,
                    season_id=season.id,
                    invoice_id=invoice_id,
                    date_created=datetime.now(),
                    sent=False,  # Set to False initially
                    quantity=booking.quantity,
                    tot_sum=season.price * booking.quantity
                )
                db.session.add(invoice)
                # Commit the invoice first
                db.session.commit()
                # Now refresh to load relationships
                db.session.refresh(invoice)
                current_app.logger.info(f"Created invoice object for booking {booking.id}")

                # Send email
                msg = Message(
                    f'Faktura från Solberg Honung (Andelsbiodling {season.year}) - {booking.name}',
                    sender='noreply@example.com',
                    recipients=[booking.email]
                )
                msg.html = render_template(
                    'invoice_template.html',
                    invoice=invoice,
                    booking=booking,
                    timedelta=timedelta,
                    logo_cid='logo',
                    swish_qr_cid='swish_qr'
                )
                # Attach logo as inline image
                with current_app.open_resource('static/logo.png') as fp:
                    msg.attach('logo.png', 'image/png', fp.read(), 'inline', headers=[['Content-ID','<logo>']])
                # Attach swish QR as inline image
                with current_app.open_resource('static/swish_qr.png') as fp:
                    msg.attach('swish_qr.png', 'image/png', fp.read(), 'inline', headers=[['Content-ID','<swish_qr>']])

                # Generate PDF content for attachment
                pdf_html = render_template(
                    'invoice_pdf_template.html',
                    invoice=invoice,
                    booking=booking,
                    timedelta=timedelta,
                    logo_cid='logo',
                    swish_qr_cid='swish_qr'
                )
                pdf_filename = f"{invoice.invoice_id}.pdf"
                pdf_path = os.path.join(current_app.root_path, '..', 'invoices', 'andelsbiodling', str(season.year), pdf_filename)

                # Save the PDF to file
                if generate_invoice_pdf(pdf_html, pdf_path):
                    # Attach the PDF to the email
                    with open(pdf_path, 'rb') as fp:
                        msg.attach(pdf_filename, 'application/pdf', fp.read())

                effective, source = get_effective_mail_backend_with_source(current_app)
                params = get_mail_connection_params(effective)
                current_app.logger.info(
                    f"Mail backend: {effective!r} (source={source}), server={params['server']}:{params['port']}. Sending to {booking.email}"
                )
                send_mail_using_current_config(current_app, msg)

                # Only mark as sent if email was successful
                invoice.sent = True
                sent_count += 1
                current_app.logger.info(f"Successfully sent invoice for booking {booking.id}")

            except Exception as e:
                error_msg = f"Error processing booking {booking.id}: {str(e)}{format_exception_location(e)}"
                current_app.logger.error(error_msg)
                errors.append(error_msg)
                continue

        db.session.commit()
        current_app.logger.info(f"Successfully processed {sent_count} invoices, {skipped_count} skipped")

        message = f'Invoices created, saved as PDF and sent to {sent_count} recipients.'
        if skipped_count > 0:
            message += f' {skipped_count} invoices already existed and were skipped.'

        flash(message, 'success')
        for err in errors:
            flash(err, 'error')
        return jsonify({
            'success': True,
            'message': message,
            'errors': errors if errors else None
        })
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error sending invoices: {str(e)}{format_exception_location(e)}"
        current_app.logger.error(error_msg)
        return jsonify({'error': error_msg}), 500

def create_sale_from_invoice(invoice):
    """Create a Sale record when an andel invoice is marked as paid. Idempotent: no-op if sale already exists for this invoice."""
    if hasattr(invoice, 'sale') and invoice.sale is not None:
        return invoice.sale
    product = Product.query.filter_by(name='solberg honung').first()
    category = SaleCategory.query.filter_by(name='andel').first()
    if not product or not category:
        current_app.logger.warning('Cannot create sale from invoice: missing Product "solberg honung" or SaleCategory "andel".')
        return None
    booking = invoice.booking
    season = invoice.season
    unit_price = round(invoice.tot_sum / invoice.quantity, 2) if invoice.quantity else 0
    sale_date = invoice.date_payed or datetime.utcnow()
    sale = Sale(
        timestamp=sale_date,
        product_id=product.id,
        skord=str(season.year) if season else 'okänd',
        burk_kg=2.5,
        unit_price=unit_price,
        quantity=invoice.quantity,
        consistency='fast',
        apiary='Solberg',
        category_id=category.id,
        customer_id=booking.customer_id,
        customer_name=None,
        invoice_id=invoice.id,
    )
    db.session.add(sale)
    return sale


@andelsbiodling.route('/api/invoice/<int:invoice_id>/payment', methods=['POST'])
def update_invoice_payment(invoice_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        abort(404)
    date_paid = request.json.get('date_paid')
    was_already_paid = invoice.date_payed is not None

    try:
        if date_paid:
            invoice.date_payed = datetime.strptime(date_paid, '%Y-%m-%d')
            # Only create a sale when first marking as paid; do not recreate if the user
            # had deleted the sale and then changes the payment date again.
            if not was_already_paid:
                create_sale_from_invoice(invoice)
            elif hasattr(invoice, 'sale') and invoice.sale is not None:
                # Update existing sale timestamp when payment date is changed
                invoice.sale.timestamp = invoice.date_payed
        else:
            invoice.date_payed = None
            if hasattr(invoice, 'sale') and invoice.sale is not None:
                db.session.delete(invoice.sale)

        db.session.commit()
        flash('Invoice updated.', 'success')
        return jsonify({
            'success': True,
            'message': 'Invoice updated'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})