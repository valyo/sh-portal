from flask import Blueprint, render_template, redirect, url_for, session, request, current_app, flash, jsonify, abort
from .models import Season
from . import db

seasons = Blueprint('seasons', __name__)

@seasons.route('/seasons')
def list_seasons():
    if not session.get('user'):
        return redirect(url_for('main.home'))
    
    seasons = Season.query.order_by(Season.year.desc()).all()
    return render_template('seasons.html', seasons=seasons, user=session.get('user'))

@seasons.route('/api/season/<int:season_id>')
def get_season(season_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    season = db.session.get(Season, season_id)
    if season is None:
        abort(404)
    return jsonify({
        'id': season.id,
        'year': season.year,
        'price': season.price,
        'price_lamm': season.price_lamm,
        'kg_honey': season.kg_honey,
        'google_sheets_link_honey': season.google_sheets_link_honey,
        'sheet_range_honey': season.sheet_range_honey,
        'google_sheets_link_lamm': season.google_sheets_link_lamm,
        'sheet_range_lamm': season.sheet_range_lamm
    })

@seasons.route('/api/season/<int:season_id>', methods=['POST'])
def update_season(season_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    season = db.session.get(Season, season_id)
    if season is None:
        abort(404)

    try:
        season.year = request.form.get('year')
        season.price = float(request.form.get('price'))
        season.price_lamm = float(request.form.get('price_lamm'))
        kg_honey = request.form.get('kg_honey')
        season.kg_honey = float(kg_honey) if kg_honey else None
        season.google_sheets_link_honey = request.form.get('google_sheets_link_honey')
        season.sheet_range_honey = request.form.get('sheet_range_honey')
        season.google_sheets_link_lamm = request.form.get('google_sheets_link_lamm')
        season.sheet_range_lamm = request.form.get('sheet_range_lamm')

        db.session.commit()
        flash(f'Season {season.year} updated!', 'success')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@seasons.route('/api/season/<int:season_id>/delete', methods=['POST'])
def delete_season(season_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    season = db.session.get(Season, season_id)
    if season is None:
        abort(404)

    # Check if there are any bookings or invoices associated with this season
    if season.bookings or season.bookings_lamm or season.invoices or season.invoices_lamm:
        return jsonify({
            'success': False,
            'message': 'Cannot delete season because it has associated bookings or invoices.'
        }), 400

    try:
        db.session.delete(season)
        db.session.commit()
        flash(f'Season {season.year} deleted!', 'success')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@seasons.route('/seasons/create', methods=['POST'])
def create_season():
    if not session.get('user'):
        return redirect(url_for('main.home'))
    
    year = request.form.get('year')
    price = request.form.get('price')
    price_lamm = request.form.get('price_lamm')
    kg_honey = request.form.get('kg_honey')
    google_sheets_link_honey = request.form.get('google_sheets_link_honey')
    sheet_range_honey = request.form.get('sheet_range_honey')
    google_sheets_link_lamm = request.form.get('google_sheets_link_lamm')
    sheet_range_lamm = request.form.get('sheet_range_lamm')

    # Check if season already exists
    existing_season = Season.query.filter_by(year=year).first()
    if existing_season:
        flash('A season for this year already exists.', 'error')
        return redirect(url_for('seasons.list_seasons'))
    
    # Create new season
    new_season = Season(
        year=year,
        price=price,
        price_lamm=price_lamm,
        kg_honey=float(kg_honey) if kg_honey else None,
        google_sheets_link_honey=google_sheets_link_honey,
        sheet_range_honey=sheet_range_honey,
        google_sheets_link_lamm=google_sheets_link_lamm,
        sheet_range_lamm=sheet_range_lamm
    )
    db.session.add(new_season)
    db.session.commit()
    
    flash('New season created!', 'success')
    return redirect(url_for('seasons.list_seasons')) 