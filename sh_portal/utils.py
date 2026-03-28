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


def normalize_customer_name(s):
    """
    Normalize a free-text customer name for consistent storage and statistics.
    Trims and collapses whitespace, then title-cases each word.
    Returns None for empty/whitespace-only input.
    """
    if not s or not isinstance(s, str):
        return None
    s = " ".join(s.split()).strip()
    if not s:
        return None
    return s.title()


def get_mail_connection_params(backend):
    """
    Return SMTP connection params for the given backend. Does not touch app.config.
    Returns dict: server, port, use_tls, use_ssl, username, password.
    """
    b = (backend or 'mailcatcher').lower()
    if b == 'google':
        return {
            'server': os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
            'port': int(os.getenv('MAIL_PORT', 587)),
            'use_tls': True,
            'use_ssl': False,
            'username': os.getenv('MAIL_USERNAME', ''),
            'password': os.getenv('MAIL_PASSWORD', ''),
        }
    return {
        'server': os.getenv('MAIL_SERVER', 'mailcatcher'),
        'port': int(os.getenv('MAIL_PORT', 1025)),
        'use_tls': False,
        'use_ssl': False,
        'username': '',
        'password': '',
    }


def get_effective_mail_backend(app):
    """Return the mail backend to use: cookie (navbar) > env MAIL_BACKEND."""
    backend, _ = get_effective_mail_backend_with_source(app)
    return backend


def get_effective_mail_backend_with_source(app):
    """
    Return (backend, source). Single override: cookie. Fallback: env MAIL_BACKEND.
    - backend: 'mailcatcher' or 'google'
    - source: 'cookie' or 'config'
    """
    from flask import request
    cookie_val = request.cookies.get('mail_backend', '').strip().lower() if request else ''
    if cookie_val in ('mailcatcher', 'google'):
        return cookie_val, 'cookie'
    config_val = app.config.get('MAIL_BACKEND', 'mailcatcher')
    return (config_val if config_val in ('mailcatcher', 'google') else 'mailcatcher', 'config')


def send_mail_using_current_config(app, msg):
    """
    Single entry point: resolve effective backend, build SMTP params, send via smtplib.
    Does not mutate app.config.
    """
    import smtplib
    effective, _ = get_effective_mail_backend_with_source(app)
    params = get_mail_connection_params(effective)
    from_addr = msg.sender
    to_addrs = list(msg.recipients) + list(getattr(msg, 'bcc', []) or []) + list(getattr(msg, 'cc', []) or [])
    to_addrs = [a for a in to_addrs if a]
    if not to_addrs:
        return
    try:
        payload = msg.as_bytes()
    except AttributeError:
        payload = (msg.as_string() if hasattr(msg, 'as_string') else str(msg)).encode(
            getattr(msg, 'charset', 'utf-8') or 'utf-8'
        )
    if params['use_ssl']:
        smtp = smtplib.SMTP_SSL(params['server'], params['port'])
    else:
        smtp = smtplib.SMTP(params['server'], params['port'])
    if params['use_tls'] and not params['use_ssl']:
        smtp.starttls()
    if params['username'] and params['password']:
        smtp.login(params['username'], params['password'])
    smtp.sendmail(from_addr, to_addrs, payload)
    smtp.quit()


CERTIFICATE_EMAIL_SUBJECT = "Tack för din betalning och varmt välkommen!"


def _first_name_for_certificate_greeting(name):
    """First whitespace-delimited token of the booking name for email salutation."""
    if not name or not str(name).strip():
        return "du"
    return str(name).strip().split()[0]


def _parse_season_year_int(year_value):
    """Parse season.year string to int, or None if not a plain calendar year."""
    if year_value is None:
        return None
    try:
        return int(str(year_value).strip())
    except (TypeError, ValueError):
        return None


def honey_customer_has_prior_season_booking(booking, current_season):
    """
    True if this person has at least one honey (Bookings) row in a strictly earlier season
    (by numeric season year). Lammandel is ignored.

    Matching is by email (case-insensitive, trimmed), not only customer_id, so returning
    customers are detected even if duplicate Customer rows exist for the same email.

    If the current season year does not parse as an integer, returns False.
    """
    from sqlalchemy import func

    from sh_portal import db
    from sh_portal.models import Bookings, Customer, Season

    cur_y = _parse_season_year_int(getattr(current_season, "year", None))
    if cur_y is None:
        return False

    bid = getattr(booking, "id", None)
    if bid is None:
        return False
    b = db.session.get(Bookings, bid)
    if b is None:
        return False

    cid = b.customer_id
    if cid is None:
        return False

    cust = db.session.get(Customer, cid)
    if cust is None or not (cust.email or "").strip():
        return False

    email_norm = str(cust.email).strip().lower()

    # All honey seasons this email has booked (any Customer row with same email)
    years_rows = (
        db.session.query(Season.year)
        .join(Bookings, Bookings.season_id == Season.id)
        .join(Customer, Customer.id == Bookings.customer_id)
        .filter(
            Customer.email.isnot(None),
            func.lower(func.trim(Customer.email)) == email_norm,
        )
        .distinct()
        .all()
    )

    for (year_str,) in years_rows:
        py = _parse_season_year_int(year_str)
        if py is not None and py < cur_y:
            return True
    return False


def certificate_email_plain_text(season_year, first_name, honey_returning_customer=False):
    y = str(season_year)
    if honey_returning_customer:
        welcome = f"Varmt välkommen återigen som andelsbiodlare {y}."
    else:
        welcome = f"Varmt välkommen som andelsbiodlare {y}."
    return (
        f"Hej {first_name},\n\n"
        f"{welcome}\n\n"
        f"Villkor {y}\n"
        f"Villkor för andelsbiodlingen säsong {y} finns på vår hemsida http://solberghonung.se/\n\n"
        f"Andelsbevis finns bifogat.\n\n"
        f"Hälsningar,\n"
        f"Valentin och Polina\n"
    )


def lamm_certificate_email_plain_text(season_year, first_name):
    y = str(season_year)
    return (
        f"Hej {first_name},\n\n"
        f"Varmt välkommen som lammandelsägare {y}.\n\n"
        f"Vi hör av oss med mer information när det närmar sig hämtning av ditt lamm.\n\n"
        f"Hälsningar,\n"
        f"Valentin och Lasse\n"
    )


def certificate_download_filename(booking, season):
    """Filename for certificate PDF attachment (matches previous download naming)."""
    cert_name = booking.certificate_name if booking.certificate_name else booking.name
    year_s = str(season.year)
    suffix = year_s[-2:] if len(year_s) >= 2 else year_s
    andelsnummer = f"{suffix}-{booking.id:03d}"
    safe = (cert_name or "kund").replace(" ", "_")
    return f"Andelsbevis_{andelsnummer}_{safe}.pdf"


def build_certificate_template_context(booking, season):
    return {
        "booking": booking,
        "season": season,
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "logo_cid": "logo",
    }


def write_certificate_pdf_to_disk(booking, season, is_lamm=False):
    """
    Render certificate PDF to the certificates/ folder.
    Returns (success: bool, pdf_path: str).
    """
    template_path = os.path.join(current_app.root_path, "templates", "certificate_pdf_template.html")
    internal_pdf = (
        f"certificate_lamm_{booking.id}.pdf" if is_lamm else f"certificate_{booking.id}.pdf"
    )
    pdf_path = os.path.join(current_app.root_path, "..", "certificates", internal_pdf)
    context = build_certificate_template_context(booking, season)
    ok = generate_pdf_weasyprint(template_path, pdf_path, context, base_url=current_app.root_path)
    return ok, pdf_path


def send_booking_certificate_email(booking, season, is_lamm=False):
    """
    Email booking.email: honey andelsbiodling includes a PDF certificate; lammandel is text-only.
    Returns (True, None) on success or (False, error_message) on failure.
    """
    from flask_mail import Message

    first = _first_name_for_certificate_greeting(booking.name)
    if is_lamm:
        body = lamm_certificate_email_plain_text(season.year, first)
    else:
        returning = honey_customer_has_prior_season_booking(booking, season)
        body = certificate_email_plain_text(
            season.year, first, honey_returning_customer=returning
        )

    msg = Message(
        CERTIFICATE_EMAIL_SUBJECT,
        sender="noreply@example.com",
        recipients=[booking.email],
        body=body,
    )

    if not is_lamm:
        ok, pdf_path = write_certificate_pdf_to_disk(booking, season, is_lamm=False)
        if not ok:
            return False, "Failed to generate certificate"
        attachment_name = certificate_download_filename(booking, season)
        try:
            with open(pdf_path, "rb") as fp:
                msg.attach(attachment_name, "application/pdf", fp.read())
        except OSError as e:
            current_app.logger.error("Certificate attach failed: %s", e)
            return False, "Failed to read certificate file"

    try:
        effective, source = get_effective_mail_backend_with_source(current_app)
        params = get_mail_connection_params(effective)
        current_app.logger.info(
            "Certificate mail: backend=%r (source=%s), %s:%s, to=%s",
            effective,
            source,
            params["server"],
            params["port"],
            booking.email,
        )
        send_mail_using_current_config(current_app, msg)
    except Exception as e:
        current_app.logger.error(
            "Certificate email send failed: %s\n%s", e, traceback.format_exc()
        )
        return False, str(e)

    return True, None


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


def get_or_create_customer(db, email, name, telephone, address, postnummer, ort):
    """
    Return a Customer for the given contact data. If a customer with this email exists,
    update their fields and return it; otherwise create and return a new one.
    """
    from .models import Customer
    customer = db.session.query(Customer).filter_by(email=email).first()
    if customer:
        customer.name = name
        customer.telephone = telephone
        customer.address = address
        customer.postnummer = postnummer
        customer.ort = ort
        return customer
    customer = Customer(
        email=email,
        name=name,
        telephone=telephone,
        address=address,
        postnummer=postnummer,
        ort=ort,
    )
    db.session.add(customer)
    return customer


def _parse_booking_timestamp(s):
    """
    Parse a timestamp string from Google Sheets (or similar) into a datetime.
    Tries several common formats, then normalizes M/D/YY H:M:S (single digits ok).
    Returns datetime or None if unparseable.
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None

    # Try strict formats first
    formats = [
        '%m/%d/%Y %H:%M:%S',   # 09/29/2024 19:12:04
        '%m/%d/%y %H:%M:%S',   # 09/29/24 19:12:04
        '%Y-%m-%d %H:%M:%S',   # 2024-09-29 19:12:04
        '%Y-%m-%d %H:%M:%S.%f',  # with microseconds
        '%Y-%m-%dT%H:%M:%S',   # ISO-like
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%y %H:%M:%S',
        '%d.%m.%Y %H:%M:%S',
        '%d.%m.%y %H:%M:%S',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s[:26], fmt)  # cap length for %f
        except ValueError:
            continue

    # Normalize M/D/YY H:M:S (single-digit month, day, second; 2-digit year)
    try:
        parts = s.split(None, 1)
        if len(parts) != 2:
            return None
        date_part, time_part = parts
    except (ValueError, AttributeError):
        return None

    try:
        date_segments = date_part.replace('.', '/').split('/')
        if len(date_segments) != 3:
            return None
        m, d, y = [x.zfill(2) for x in date_segments]
        if len(y) == 2:
            y = '20' + y
        date_normalized = f'{m}/{d}/{y}'
    except (ValueError, AttributeError):
        return None

    try:
        time_segments = time_part.split(':')
        if len(time_segments) < 3:
            return None
        # Drop fractional seconds if present (e.g. 04.123 -> 04)
        time_segments = [x.split('.')[0].zfill(2) for x in time_segments[:3]]
        time_normalized = ':'.join(time_segments)
    except (ValueError, AttributeError):
        return None

    normalized = f'{date_normalized} {time_normalized}'
    try:
        return datetime.strptime(normalized, '%m/%d/%Y %H:%M:%S')
    except ValueError:
        return None


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

    # Check if the first row is a header (timestamp column header in various languages)
    if sheet_data:
        first_cell = (sheet_data[0][0] or '').strip().lower()
        if first_cell in ('timestamp', 'tid', 'date', 'tidstämpel'):
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
        timestamp_obj = _parse_booking_timestamp(row['timestamp'])
        if timestamp_obj is None:
            current_app.logger.error(f"Error parsing timestamp: {row['timestamp']!r}")
            flash(f'Error parsing timestamp for booking: {row["email"]}', 'error')
            continue

        # Quantity: allow missing or empty (default 1)
        try:
            raw_num = row.get('number')
            if raw_num is None or (isinstance(raw_num, float) and pd.isna(raw_num)) or str(raw_num).strip() == '':
                quantity = 1
            else:
                quantity = int(float(raw_num))
        except (ValueError, TypeError):
            quantity = 1
        if quantity < 1:
            quantity = 1

        current_app.logger.info(f"Timestamp: {timestamp_obj}")

        customer = get_or_create_customer(
            db,
            email=row['email'],
            name=row['name'],
            telephone=row['telephone'],
            address=row['address'],
            postnummer=row['postnummer'],
            ort=row['ort'],
        )
        existing_booking = BookingsModel.query.filter_by(
            customer_id=customer.id,
            season_id=season_id
        ).first()

        if not existing_booking:
            booking = BookingsModel(
                season_id=season_id,
                customer_id=customer.id,
                timestamp=timestamp_obj,
                message=row.get('message', ''),
                quantity=quantity
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