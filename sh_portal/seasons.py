from flask import Blueprint, render_template, redirect, url_for, session, request, current_app, flash, jsonify
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

    season = Season.query.get_or_404(season_id)
    return jsonify({
        'id': season.id,
        'year': season.year,
        'price': season.price,
        'price_lamm': season.price_lamm
    })

@seasons.route('/api/season/<int:season_id>', methods=['POST'])
def update_season(season_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401

    season = Season.query.get_or_404(season_id)

    try:
        season.year = request.form.get('year')
        season.price = float(request.form.get('price'))
        season.price_lamm = float(request.form.get('price_lamm'))

        db.session.commit()
        flash(f'Säsong {season.year} uppdaterad!', 'success')
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

    # Check if season already exists
    existing_season = Season.query.filter_by(year=year).first()
    if existing_season:
        flash('En säsong med detta år finns redan.', 'error')
        return redirect(url_for('seasons.list_seasons'))
    
    # Create new season
    new_season = Season(
        year=year,
        price=price,
        price_lamm=price_lamm
    )
    db.session.add(new_season)
    db.session.commit()
    
    flash('Ny säsong skapad!', 'success')
    return redirect(url_for('seasons.list_seasons')) 