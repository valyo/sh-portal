from datetime import datetime
from flask import current_app, flash
import pandas as pd
import os
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from xhtml2pdf import pisa
from io import BytesIO

def extract_sheet_id(sheet_link):
    """
    Extracts the Google Sheet ID from a full URL or returns the input if it's already an ID.
    """
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_link)
    if match:
        return match.group(1)
    return sheet_link  # fallback: assume it's already an ID

def get_sheet_data(sheet_id, range_name):
    """
    Fetch data from Google Sheet using service account
    """
    # Use service account credentials
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    credentials = service_account.Credentials.from_service_account_file(
        'sh-web-portal-f370fff1378a.json',
        scopes=SCOPES
    )
    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=sheet_id,
        range=range_name
    ).execute()

    return result.get('values', [])

def generate_invoice_pdf(html_content, output_path):
    """
    Converts HTML content to a PDF file.
    """
    try:
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Replace cid: references with local paths for PDF generation
        # This is a simple hack since xhtml2pdf doesn't support CIDs
        # We assume the images are in sh_portal/static/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_dir = os.path.join(base_dir, 'sh_portal', 'static')

        # Convert cid:logo to actual path
        html_content = html_content.replace('cid:logo', os.path.join(static_dir, 'logo.png'))
        html_content = html_content.replace('cid:swish_qr', os.path.join(static_dir, 'swish_qr.png'))

        with open(output_path, "wb") as f:
            pisa_status = pisa.CreatePDF(html_content, dest=f)

        return not pisa_status.err
    except Exception as e:
        current_app.logger.error(f"Error generating PDF: {str(e)}")
        return False

def import_bookings_from_sheet(
    db,
    BookingsModel,
    season_id,
    sheet_data,
    column_map=None
):
    """
    Imports bookings from Google Sheet data into the specified BookingsModel.
    - db: SQLAlchemy db object
    - BookingsModel: The model class to use (Bookings or BookingsLamm)
    - season_id: The season to associate bookings with
    - sheet_data: List of rows from Google Sheets
    - column_map: Optional dict to map sheet columns to model fields
    """
    if not sheet_data:
        flash('No data to import.', 'error')
        return False

    # Check if the first row is a header (contains 'timestamp' or 'Timestamp')
    if sheet_data and sheet_data[0][0].lower() in ('timestamp', 'tid', 'date'):
        sheet_data = sheet_data[1:]  # Skip header row

    columns = [
        'timestamp', 'email', 'name', 'telephone',
        'address', 'postnummer', 'ort', 'message', 'number'
    ]
    if column_map:
        columns = [column_map.get(col, col) for col in columns]

    df = pd.DataFrame(sheet_data, columns=columns)

    imported_count = 0
    for _, row in df.iterrows():
        try:
            timestamp_obj = datetime.strptime(row['timestamp'], '%m/%d/%Y %H:%M:%S')
            current_app.logger.info(f"Timestamp: {timestamp_obj}")
        except Exception as e:
            current_app.logger.error(f"Error parsing timestamp: {str(e)}")
            flash(f'Error parsing timestamp for booking: {row["email"]}', 'error')
            continue

        existing_booking = BookingsModel.query.filter_by(
            email=row['email'],
            season_id=season_id
        ).first()

        if not existing_booking:
            booking = BookingsModel(
                season_id=season_id,
                timestamp=timestamp_obj,
                email=row['email'],
                name=row['name'],
                telephone=row['telephone'],
                address=row['address'],
                postnummer=row['postnummer'],
                ort=row['ort'],
                message=row['message'],
                quantity=int(row['number'])
            )
            db.session.add(booking)
            imported_count += 1

    try:
        db.session.commit()
        flash(f'{imported_count} bookings imported successfully!', 'success')
        return True
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing bookings: {str(e)}")
        flash('An error occurred while importing bookings.', 'error')
        return False