from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify
from .models import Season, Bookings, Invoice
from . import db
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta
import re
import os
from .utils import import_bookings_from_sheet, generate_invoice_pdf
from flask_mail import Message

andelsbiodling = Blueprint('andelsbiodling', __name__)

def get_sheet_data(sheet_id, range_name):
    """
    Fetch data from Google Sheet using service account
    """
    # Use service account credentials
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    credentials = service_account.Credentials.from_service_account_file(
        'sh-web-portal-f370fff1378a.json',  # You'll need to create this
        scopes=SCOPES
    )
    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=sheet_id,
        range=range_name
    ).execute()

    return result.get('values', [])

def extract_sheet_id(sheet_link):
    """
    Extracts the Google Sheet ID from a full URL or returns the input if it's already an ID.
    """
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_link)
    if match:
        return match.group(1)
    return sheet_link  # fallback: assume it's already an ID

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
        'quantity': booking.quantity
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

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@andelsbiodling.route('/api/send-invoices', methods=['POST'])
def send_invoices():
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    booking_ids = request.json.get('booking_ids', [])
    if not booking_ids:
        return jsonify({'error': 'No bookings selected'}), 400

    bookings = Bookings.query.filter(Bookings.id.in_(booking_ids)).all()
    season = bookings[0].season if bookings else None

    if not season:
        return jsonify({'error': 'No season found for bookings'}), 400

    try:
        sent_count = 0
        skipped_count = 0
        for booking in bookings:
            # Check if invoice already exists
            existing_invoice = Invoice.query.filter_by(booking_id=booking.id).first()
            if existing_invoice:
                skipped_count += 1
                continue  # Skip if invoice already exists

            # Generate a unique invoice ID
            invoice_id = f"F-{season.year}-{booking.id:04d}"

            # Create new invoice
            invoice = Invoice(
                booking_id=booking.id,
                season_id=season.id,
                invoice_id=invoice_id,
                date_created=datetime.now(),
                sent=True,
                quantity=booking.quantity,  # Changed from number to quantity
                tot_sum=season.price * booking.quantity
            )
            db.session.add(invoice)
            # Commit the invoice first
            db.session.commit()
            # Now refresh to load relationships
            db.session.refresh(invoice)

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

            current_app.extensions['mail'].send(msg)
            sent_count += 1

        message = f'Invoices created, saved as PDF and sent to {sent_count} recipients.'
        if skipped_count > 0:
            message += f' {skipped_count} invoices already existed and were skipped.'

        return jsonify({
            'success': True,
            'message': message
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending invoices: {str(e)}")
        return jsonify({'error': str(e)}), 500