from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app
from .models import Season, BookingsLamm, InvoiceLamm
from . import db
import re
from .utils import import_bookings_from_sheet

lammandel = Blueprint('lammandel', __name__)

def extract_sheet_id(sheet_link):
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_link)
    if match:
        return match.group(1)
    return sheet_link

@lammandel.route('/lammandel/import-bookings', methods=['POST'])
def import_bookings():
    if not session.get('user'):
        return redirect(url_for('main.home'))

    try:
        season_id = request.form.get('season_id')
        sheet_link = request.form.get('sheet_link')
        range_name = request.form.get('range_name', 'Form Responses 1!A2:I')
        if not season_id or not sheet_link or not range_name:
            flash('Season, Google Sheet link and range are required.', 'error')
            return redirect(url_for('lammandel.index'))

        sheet_id = extract_sheet_id(sheet_link)

        # You should reuse your get_sheet_data function from andelsbiodling.py
        from .andelsbiodling import get_sheet_data
        data = get_sheet_data(sheet_id, range_name)
        if not data:
            flash('Could not fetch data from Google Sheet.', 'error')
            return redirect(url_for('lammandel.index'))

        success = import_bookings_from_sheet(
            db=db,
            BookingsModel=BookingsLamm,
            season_id=season_id,
            sheet_data=data
        )
        return redirect(url_for('lammandel.index', season_id=season_id))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing bookings: {str(e)}")
        flash('An error occurred while importing bookings.', 'error')

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
    invoices = []
    if selected_season:
        bookings = BookingsLamm.query.filter_by(season_id=selected_season.id).all()
        invoices = InvoiceLamm.query.filter_by(season_id=selected_season.id).all()

    return render_template(
        'bookings_base.html',
        user=session.get('user'),
        seasons=seasons,
        selected_season=selected_season,
        bookings=bookings,
        invoices=invoices,  # Pass invoices to the template
        page_title="Lammandel",
        import_url=url_for('lammandel.import_bookings')
    ) 