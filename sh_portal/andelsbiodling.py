from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app
from .models import Season, Bookings, Invoice
from . import db
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime
import re
from .utils import import_bookings_from_sheet

andelsbiodling = Blueprint('andelsbiodling', __name__)

def get_sheet_data(sheet_id, range_name):
    """
    Fetch data from Google Sheet using service account
    """
    try:
        # Use service account credentials
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        credentials = service_account.Credentials.from_service_account_file(
            'sh-web-portal-f370fff1378a.json',  # You'll need to create this
            scopes=SCOPES
        )
        current_app.logger.info(f"Credentials: {type(credentials)}")
        service = build('sheets', 'v4', credentials=credentials)
        sheet = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=sheet_id,
            range=range_name
        ).execute()

        return result.get('values', [])
    except Exception as e:
        current_app.logger.error(f"Error fetching sheet data: {str(e)}")
        return None

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
            flash('Could not fetch data from Google Sheet.', 'error')
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
        flash('An error occurred while importing bookings.', 'error')

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
    invoices = []
    if selected_season:
        bookings = Bookings.query.filter_by(season_id=selected_season.id).all()
        invoices = Invoice.query.filter_by(season_id=selected_season.id).all()

    return render_template(
        'bookings_base.html',
        user=session.get('user'),
        seasons=seasons,
        selected_season=selected_season,
        bookings=bookings,
        invoices=invoices,  # Pass invoices to the template
        page_title="Andelsbiodling",
        import_url=url_for('andelsbiodling.import_bookings')
    )