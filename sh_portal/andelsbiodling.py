from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify, send_file
from .models import Season, Bookings, Invoice
from . import db
import pandas as pd
from datetime import datetime, timedelta
import re
import os
from .utils import import_bookings_from_sheet, generate_invoice_pdf, get_sheet_data, extract_sheet_id, generate_pdf_weasyprint
from flask_mail import Message

andelsbiodling = Blueprint('andelsbiodling', __name__)

@andelsbiodling.route('/api/booking/<int:booking_id>/certificate', methods=['GET'])
def generate_certificate(booking_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = Bookings.query.get_or_404(booking_id)
    season = booking.season

    # Generate PDF
    pdf_html = render_template(
        'certificate_pdf_template.html',
        booking=booking,
        season=season,
        current_date=datetime.now().strftime('%Y-%m-%d'),
        logo_cid='logo'
    )

    pdf_filename = f"certificate_{booking.id}.pdf"
    pdf_path = os.path.join(current_app.root_path, '..', 'temp', pdf_filename)

    # Use WeasyPrint for certificates
    static_folder = os.path.join(current_app.root_path, 'static')
    if generate_pdf_weasyprint(pdf_html, pdf_path, base_url=static_folder):
        cert_name = booking.certificate_name if booking.certificate_name else booking.name
        andelsnummer = f"{season.year[-2:]}-{booking.id:03d}"
        return send_file(pdf_path, as_attachment=True, download_name=f"Andelsbevis_{andelsnummer}_{cert_name.replace(' ', '_')}.pdf")
    else:
        return jsonify({'error': 'Failed to generate certificate'}), 500

@andelsbiodling.route('/andelsbiodling/import-bookings', methods=['POST'])
def import_bookings():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    try:
        season_id = request.form.get('season_id')
        sheet_link = request.form.get('sheet_link')
        range_name = request.form.get('range_name', 'Form Responses 1!A2:I')
        if not season_id or not sheet_link or not range_name:
            flash('Season, Google Sheet link and range are required.', 'error')
            return redirect(url_for('andelsbiodling.index'))

        sheet_id = extract_sheet_id(sheet_link)

        data = get_sheet_data(sheet_id, range_name)
        if not data:
            flash('The Google Sheet range is empty or no data was found.', 'error')
            return redirect(url_for('andelsbiodling.index'))

        success = import_bookings_from_sheet(
            db=db,
            BookingsModel=Bookings,
            season_id=season_id,
            sheet_data=data
        )
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
        selected_season = Season.query.get(selected_season_id)
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

    booking = Bookings.query.get_or_404(booking_id)
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
        'certificate_name': booking.certificate_name
    })

@andelsbiodling.route('/api/booking/<int:booking_id>', methods=['POST'])
def update_booking(booking_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = Bookings.query.get_or_404(booking_id)

    try:
        booking.name = request.form.get('name')
        booking.email = request.form.get('email')
        booking.telephone = request.form.get('telephone')
        booking.address = request.form.get('address')
        booking.postnummer = request.form.get('postnummer')
        booking.ort = request.form.get('ort')
        booking.message = request.form.get('message')
        booking.quantity = int(request.form.get('quantity'))
        booking.certificate_name = request.form.get('certificate_name')

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

    season = Season.query.get(season_id)
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

                current_app.logger.info(f"Sending email to {booking.email}")
                current_app.extensions['mail'].send(msg)

                # Only mark as sent if email was successful
                invoice.sent = True
                sent_count += 1
                current_app.logger.info(f"Successfully sent invoice for booking {booking.id}")

            except Exception as e:
                error_msg = f"Error processing booking {booking.id}: {str(e)}"
                current_app.logger.error(error_msg)
                errors.append(error_msg)
                continue

        current_app.logger.info(f"Successfully processed {sent_count} invoices, {skipped_count} skipped")

        message = f'Invoices created, saved as PDF and sent to {sent_count} recipients.'
        if skipped_count > 0:
            message += f' {skipped_count} invoices already existed and were skipped.'

        return jsonify({
            'success': True,
            'message': message,
            'errors': errors if errors else None
        })
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error sending invoices: {str(e)}"
        current_app.logger.error(error_msg)
        return jsonify({'error': error_msg}), 500

@andelsbiodling.route('/api/invoice/<int:invoice_id>/payment', methods=['POST'])
def update_invoice_payment(invoice_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    invoice = Invoice.query.get_or_404(invoice_id)
    paid = request.json.get('paid', False)

    try:
        if paid:
            invoice.date_payed = datetime.now()
        else:
            invoice.date_payed = None

        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Invoice marked as {"paid" if paid else "unpaid"}.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})