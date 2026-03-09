from datetime import datetime
from flask import current_app, flash
import pandas as pd
import os
import re
import traceback
from google.oauth2 import service_account
from googleapiclient.discovery import build
from weasyprint import HTML
from jinja2 import Template
from io import BytesIO

def apply_mail_backend(app, backend):
    """Set app mail config for the given backend ('mailcatcher' or 'google'). Used for runtime switch from navbar."""
    b = (backend or 'mailcatcher').lower()
    if b == 'google':
        app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
        app.config['MAIL_USE_TLS'] = True
        app.config['MAIL_USE_SSL'] = False
        app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', '')
        app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', '')
    else:
        app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'mailcatcher')
        app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 1025))
        app.config['MAIL_USE_TLS'] = False
        app.config['MAIL_USE_SSL'] = False
        app.config['MAIL_USERNAME'] = ''
        app.config['MAIL_PASSWORD'] = ''


def send_mail_using_current_config(app, msg):
    """
    Send message via smtplib using app's current mail config (must call apply_mail_backend first).
    Flask-Mail reads server/port at init time, so we bypass it and send with the config we just set.
    """
    import smtplib
    server = app.config['MAIL_SERVER']
    port = int(app.config['MAIL_PORT'])
    use_tls = app.config.get('MAIL_USE_TLS', False)
    use_ssl = app.config.get('MAIL_USE_SSL', False)
    username = app.config.get('MAIL_USERNAME') or ''
    password = app.config.get('MAIL_PASSWORD') or ''
    from_addr = msg.sender
    to_addrs = list(msg.recipients) + list(getattr(msg, 'bcc', []) or []) + list(getattr(msg, 'cc', []) or [])
    to_addrs = [a for a in to_addrs if a]
    if not to_addrs:
        return
    # Use the same MIME the Message builds (as_bytes in Py3, as_string in Py2)
    try:
        payload = msg.as_bytes()
    except AttributeError:
        payload = (msg.as_string() if hasattr(msg, 'as_string') else str(msg)).encode(getattr(msg, 'charset', 'utf-8') or 'utf-8')
    if use_ssl:
        smtp = smtplib.SMTP_SSL(server, port)
    else:
        smtp = smtplib.SMTP(server, port)
    if use_tls and not use_ssl:
        smtp.starttls()
    if username and password:
        smtp.login(username, password)
    smtp.sendmail(from_addr, to_addrs, payload)
    smtp.quit()


def get_effective_mail_backend(app):
    """Return the mail backend to use: cookie (navbar) > session > app config (from env)."""
    backend, _ = get_effective_mail_backend_with_source(app)
    return backend


def get_effective_mail_backend_with_source(app):
    """
    Return (backend, source) so you know what will actually be used.
    - backend: 'mailcatcher' or 'google'
    - source: 'cookie' (navbar choice), 'session', or 'config' (env MAIL_BACKEND)
    """
    from flask import request, session
    cookie_val = request.cookies.get('mail_backend', '').strip().lower() if request else ''
    if cookie_val in ('mailcatcher', 'google'):
        return cookie_val, 'cookie'
    session_val = session.get('mail_backend')
    if session_val in ('mailcatcher', 'google'):
        return session_val, 'session'
    config_val = app.config.get('MAIL_BACKEND', 'mailcatcher')
    return (config_val if config_val in ('mailcatcher', 'google') else 'mailcatcher', 'config')


def format_exception_location(exc):
    """Return a string like 'andelsbiodling.py:274 in send_invoices' for the frame where the exception was raised."""
    if getattr(exc, '__traceback__', None) is None:
        return ''
    tb = traceback.extract_tb(exc.__traceback__)
    if not tb:
        return ''
    frame = tb[-1]
    return f" ({os.path.basename(frame.filename)}:{frame.lineno} in {frame.name})"


def generate_pdf_weasyprint(template_path, output_path, context, base_url=None):
    """
    Renders a template with Jinja2 and converts it to a PDF file using WeasyPrint.
    """
    try:
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 1. Read the template file
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # 2. Render the template with Jinja2 (direct approach like in development)
        template = Template(template_content)
        html_content = template.render(**context)

        # 3. Use WeasyPrint to generate PDF
        html = HTML(string=html_content, base_url=base_url, encoding='utf-8')
        html.write_pdf(target=output_path)

        current_app.logger.info(f"Successfully generated PDF at {output_path} using WeasyPrint and Jinja2 Template")
        return True
    except Exception as e:
        error_msg = f"Error generating PDF with WeasyPrint/Jinja2: {str(e)}\n{traceback.format_exc()}"
        current_app.logger.error(error_msg)
        return False

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
    Fetch data from Google Sheet using service account.
    Uses GOOGLE_APPLICATION_CREDENTIALS when set (e.g. in deployment);
    otherwise falls back to service-account.json in the current directory.
    """
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account.json')
    credentials = service_account.Credentials.from_service_account_file(
        creds_path,
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
    Converts HTML content to a PDF file using WeasyPrint.
    """
    try:
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Replace cid: references with local paths for PDF generation
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_dir = os.path.join(base_dir, 'sh_portal', 'static')

        # WeasyPrint handles paths better if we use file:// prefix for local files
        static_url = f"file://{static_dir}/"

        # Convert cid: references to relative paths that WeasyPrint can resolve with base_url
        html_content = html_content.replace('cid:logo', 'logo.png')
        html_content = html_content.replace('cid:swish_qr', 'swish_qr.png')
        html_content = html_content.replace('cid:honey', 'honey.png')
        html_content = html_content.replace('cid:bee_icon', 'bee_icon.png')

        # Use WeasyPrint to generate PDF
        html = HTML(string=html_content, base_url=static_url, encoding='utf-8')
        html.write_pdf(target=output_path)

        current_app.logger.info(f"Successfully generated invoice PDF at {output_path} using WeasyPrint")
        return True
    except Exception as e:
        current_app.logger.error(f"Error generating invoice PDF with WeasyPrint: {str(e)}")
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