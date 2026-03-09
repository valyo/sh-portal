from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify, send_file
from .models import Season, BookingsLamm, InvoiceLamm
from . import db
import re
import os
from .utils import (
    import_bookings_from_sheet, generate_invoice_pdf, get_sheet_data, extract_sheet_id,
    generate_pdf_weasyprint, format_exception_location, get_effective_mail_backend,
    get_effective_mail_backend_with_source, apply_mail_backend, send_mail_using_current_config,
)
from datetime import datetime, timedelta
from flask_mail import Message

lammandel = Blueprint('lammandel', __name__)

@lammandel.route('/lammandel/api/booking/<int:booking_id>/certificate', methods=['GET'])
def generate_certificate(booking_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = BookingsLamm.query.get_or_404(booking_id)
    season = booking.season

    # Prepare context for template
    context = {
        'booking': booking,
        'season': season,
        'current_date': datetime.now().strftime('%Y-%m-%d'),
        'logo_cid': 'logo'
    }

    pdf_filename = f"certificate_lamm_{booking.id}.pdf"
    pdf_path = os.path.join(current_app.root_path, '..', 'certificates', pdf_filename)
    template_path = os.path.join(current_app.root_path, 'templates', 'certificate_pdf_template.html')

    # Use WeasyPrint for certificates with direct Jinja2 rendering
    if generate_pdf_weasyprint(template_path, pdf_path, context, base_url=current_app.root_path):
        cert_name = booking.certificate_name if booking.certificate_name else booking.name
        andelsnummer = f"{season.year[-2:]}-{booking.id:03d}"
        return send_file(pdf_path, as_attachment=True, download_name=f"Andelsbevis_{andelsnummer}_{cert_name.replace(' ', '_')}.pdf")
    else:
        return jsonify({'error': 'Failed to generate certificate'}), 500

@lammandel.route('/lammandel/import-bookings', methods=['POST'])
def import_bookings():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    season_id = request.form.get('season_id')
    if not season_id:
        flash('Season ID is required.', 'error')
        return redirect(url_for('lammandel.index'))

    season = Season.query.get_or_404(season_id)
    sheet_link = season.google_sheets_link_lamm
    range_name = season.sheet_range_lamm

    if not sheet_link or not range_name:
        flash('Google Sheet link and range are not configured for this season.', 'error')
        return redirect(url_for('lammandel.index', season_id=season_id))

    try:
        sheet_id = extract_sheet_id(sheet_link)
        data = get_sheet_data(sheet_id, range_name)
        if not data:
            flash('The Google Sheet range is empty or no data was found.', 'error')
            return redirect(url_for('lammandel.index', season_id=season_id))

        success = import_bookings_from_sheet(
            db=db,
            BookingsModel=BookingsLamm,
            season_id=season_id,
            sheet_data=data
        )
        flash(f'Successfully imported bookings from Google Sheet.', 'success')
        return redirect(url_for('lammandel.index', season_id=season_id))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing bookings: {str(e)}")
        flash(f'An error occurred while importing bookings: {str(e)}', 'error')

    return redirect(url_for('lammandel.index', season_id=season_id))

@lammandel.route('/lammandel', methods=['GET', 'POST'])
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
        bookings = BookingsLamm.query.filter_by(season_id=selected_season.id).all()
        # Create a dictionary of invoices by booking_id
        invoices = {invoice.booking_id: invoice for invoice in InvoiceLamm.query.filter_by(season_id=selected_season.id).all()}

    return render_template(
        'bookings_base.html',
        user=session.get('user'),
        seasons=seasons,
        selected_season=selected_season,
        bookings=bookings,
        invoices=invoices,  # Pass invoices as a dictionary
        page_title="Lammandel",
        import_url=url_for('lammandel.import_bookings')
    )

@lammandel.route('/lammandel/api/booking/<int:booking_id>', methods=['GET'])
def get_booking(booking_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = BookingsLamm.query.get_or_404(booking_id)
    # Check if there is a paid invoice for this booking
    invoice = InvoiceLamm.query.filter_by(booking_id=booking.id).first()
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
        'is_paid': is_paid
    })

@lammandel.route('/lammandel/api/booking/<int:booking_id>', methods=['POST'])
def update_booking(booking_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking = BookingsLamm.query.get_or_404(booking_id)

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
        cert_qty = request.form.get('certificate_quantity')
        booking.certificate_quantity = int(cert_qty) if cert_qty else None

        db.session.commit()
        flash('Booking updated successfully', 'success')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@lammandel.route('/lammandel/api/send-invoices', methods=['POST'])
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

    bookings = BookingsLamm.query.filter(
        BookingsLamm.id.in_(booking_ids),
        BookingsLamm.season_id == season_id
    ).all()
    current_app.logger.info(f"Found {len(bookings)} bookings for season {season_id}")

    sent_count = 0
    skipped_count = 0
    errors = []

    try:
        for booking in bookings:
            current_app.logger.info(f"Processing booking {booking.id} for {booking.name}")

            # Check if invoice already exists
            existing_invoice = InvoiceLamm.query.filter_by(booking_id=booking.id).first()
            if existing_invoice:
                current_app.logger.info(f"Invoice already exists for booking {booking.id}")
                skipped_count += 1
                continue

            # Generate a unique invoice ID
            invoice_id = f"F-LAMM-{season.year}-{booking.id:04d}"
            current_app.logger.info(f"Generated invoice ID: {invoice_id}")

            try:
                # Create new invoice
                invoice = InvoiceLamm(
                    booking_id=booking.id,
                    season_id=season.id,
                    invoice_id=invoice_id,
                    date_created=datetime.now(),
                    sent=False,  # Set to False initially
                    quantity=booking.quantity,
                    tot_sum=season.price_lamm * booking.quantity
                )
                db.session.add(invoice)
                # Commit the invoice first
                db.session.commit()
                # Now refresh to load relationships
                db.session.refresh(invoice)
                current_app.logger.info(f"Created invoice object for booking {booking.id}")

                # Send email
                msg = Message(
                    f'Faktura från Solberg Honung (Lammandel {season.year}) - {booking.name}',
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
                pdf_path = os.path.join(current_app.root_path, '..', 'invoices', 'lammandel', str(season.year), pdf_filename)

                # Save the PDF to file
                if generate_invoice_pdf(pdf_html, pdf_path):
                    # Attach the PDF to the email
                    with open(pdf_path, 'rb') as fp:
                        msg.attach(pdf_filename, 'application/pdf', fp.read())

                effective, source = get_effective_mail_backend_with_source(current_app)
                old_cfg = {k: current_app.config.get(k) for k in ('MAIL_SERVER', 'MAIL_PORT', 'MAIL_USE_TLS', 'MAIL_USE_SSL', 'MAIL_USERNAME', 'MAIL_PASSWORD')}
                apply_mail_backend(current_app, effective)
                server = current_app.config['MAIL_SERVER']
                port = current_app.config['MAIL_PORT']
                current_app.logger.info(
                    f"Mail backend: {effective!r} (source={source}), server={server}:{port}. Sending to {booking.email}"
                )
                try:
                    send_mail_using_current_config(current_app, msg)
                finally:
                    for k, v in old_cfg.items():
                        current_app.config[k] = v

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

@lammandel.route('/lammandel/api/invoice/<int:invoice_id>/payment', methods=['POST'])
def update_invoice_payment(invoice_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    invoice = InvoiceLamm.query.get_or_404(invoice_id)
    date_paid = request.json.get('date_paid')

    try:
        if date_paid:
            invoice.date_payed = datetime.strptime(date_paid, '%Y-%m-%d')
        else:
            invoice.date_payed = None

        db.session.commit()
        flash('Invoice updated.', 'success')
        return jsonify({
            'success': True,
            'message': 'Invoice updated'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})