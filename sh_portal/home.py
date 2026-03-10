from flask import Blueprint, render_template, redirect, url_for, session, request, current_app, jsonify
from requests_oauthlib import OAuth2Session
import os
from .models import Admin, Season, Bookings, BookingsLamm
from . import db
main = Blueprint('main', __name__)

ALLOWED_MAIL_BACKENDS = ('mailcatcher', 'google')

def get_oauth():
    return OAuth2Session(
        client_id=current_app.config['GITHUB_CLIENT_ID'],
        redirect_uri=current_app.config['OAUTH_REDIRECT_URI'],
        scope=['user:email']
    )

def _season_stats(latest_season):
    """Return dict with booking counts, total andelar, and new vs returning customers for a season."""
    if not latest_season:
        return None
    # Bookings count (andelsbiodling + lammandel)
    num_bookings_honey = len(latest_season.bookings)
    num_bookings_lamm = len(latest_season.bookings_lamm)
    num_bookings = num_bookings_honey + num_bookings_lamm
    # Total andelar (quantity) per product
    total_andelar_honey = sum(b.quantity for b in latest_season.bookings)
    total_andelar_lamm = sum(b.quantity for b in latest_season.bookings_lamm)
    total_andelar = total_andelar_honey + total_andelar_lamm
    # Unique customers in this season
    customer_ids_this_season = set()
    for b in latest_season.bookings:
        customer_ids_this_season.add(b.customer_id)
    for b in latest_season.bookings_lamm:
        customer_ids_this_season.add(b.customer_id)
    # New = first booking ever is in this season; returning = had a booking in an earlier season
    try:
        current_year_int = int(latest_season.year)
    except (TypeError, ValueError):
        current_year_int = 0
    new_count = 0
    returning_count = 0
    for cid in customer_ids_this_season:
        # Earliest season year this customer has a booking in (any product)
        min_year = current_year_int
        for b in Bookings.query.filter_by(customer_id=cid).all():
            try:
                y = int(b.season.year)
                if y < min_year:
                    min_year = y
            except (TypeError, ValueError):
                pass
        for b in BookingsLamm.query.filter_by(customer_id=cid).all():
            try:
                y = int(b.season.year)
                if y < min_year:
                    min_year = y
            except (TypeError, ValueError):
                pass
        if min_year >= current_year_int:
            new_count += 1
        else:
            returning_count += 1
    return {
        'num_bookings': num_bookings,
        'num_bookings_honey': num_bookings_honey,
        'num_bookings_lamm': num_bookings_lamm,
        'total_andelar': total_andelar,
        'total_andelar_honey': total_andelar_honey,
        'total_andelar_lamm': total_andelar_lamm,
        'new_customers': new_count,
        'returning_customers': returning_count,
    }


@main.route('/')
def home():
    current_app.logger.info(f"Session: {session.get('user')}")
    just_logged_in = session.pop('just_logged_in', False)

    # Get the latest season
    latest_season = Season.query.order_by(Season.year.desc()).first()
    season_stats = _season_stats(latest_season) if latest_season else None

    return render_template('home.html',
                         user=session.get('user'),
                         just_logged_in=just_logged_in,
                         latest_season=latest_season,
                         season_stats=season_stats)

@main.route('/login')
def login():
    oauth = get_oauth()
    authorization_url, state = oauth.authorization_url(current_app.config['GITHUB_AUTHORIZE_URL'])
    session['oauth_state'] = state
    return redirect(authorization_url)

@main.route('/callback')
def callback():
    oauth = get_oauth()
    token = oauth.fetch_token(
        current_app.config['GITHUB_TOKEN_URL'],
        client_secret=current_app.config['GITHUB_CLIENT_SECRET'],
        authorization_response=request.url
    )

    # Get user info from GitHub
    resp = oauth.get(current_app.config['GITHUB_API_URL'])
    user_info = resp.json()

    # Check if user already exists in database
    existing_user = Admin.query.filter_by(github_id=user_info['id']).first()

    #if not, redirect to login page
    if not existing_user:
        return render_template('home.html', message=f"Hello Sulyoipulyo, you've nothing to do here!")
    else:
        # Store user info in session
        session['user'] = {
        'username': user_info['login'],  # GitHub username is in the 'login' field
        'name': user_info.get('name', ''),
        'avatar_url': user_info.get('avatar_url', ''),
        'id': user_info['id']
        }
        session['just_logged_in'] = True
        current_app.logger.info(f"User info: {user_info}")
        return redirect(url_for('main.home'))

@main.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('main.home'))


@main.route('/api/mail-backend', methods=['GET', 'POST'])
def mail_backend():
    """GET: return current effective mail backend. POST: set cookie (body: {"backend": "mailcatcher"|"google"})."""
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401
    if request.method == 'GET':
        from .utils import get_effective_mail_backend_with_source
        effective, source = get_effective_mail_backend_with_source(current_app)
        return jsonify({'mail_backend': effective, 'mail_backend_source': source})
    data = request.get_json() or {}
    backend = (data.get('backend') or '').strip().lower()
    if backend not in ALLOWED_MAIL_BACKENDS:
        return jsonify({'error': f'Invalid backend. Use one of: {", ".join(ALLOWED_MAIL_BACKENDS)}'}), 400
    current_app.logger.info(f"Setting mail backend to {backend!r} (cookie)")
    resp = jsonify({'success': True, 'mail_backend': backend})
    resp.set_cookie('mail_backend', backend, max_age=60 * 60 * 24 * 7, samesite='Lax', path='/')
    return resp

