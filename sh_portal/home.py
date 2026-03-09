from flask import Blueprint, render_template, redirect, url_for, session, request, current_app, jsonify
from requests_oauthlib import OAuth2Session
import os
from .models import Admin, Season
from . import db
main = Blueprint('main', __name__)

ALLOWED_MAIL_BACKENDS = ('mailcatcher', 'google')

def get_oauth():
    return OAuth2Session(
        client_id=current_app.config['GITHUB_CLIENT_ID'],
        redirect_uri=current_app.config['OAUTH_REDIRECT_URI'],
        scope=['user:email']
    )

@main.route('/')
def home():
    current_app.logger.info(f"Session: {session.get('user')}")
    just_logged_in = session.pop('just_logged_in', False)

    # Get the latest season
    latest_season = Season.query.order_by(Season.year.desc()).first()

    return render_template('home.html',
                         user=session.get('user'),
                         just_logged_in=just_logged_in,
                         latest_season=latest_season)

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
    """GET: return current effective mail backend. POST: set cookie + session (body: {"backend": "mailcatcher"|"google"})."""
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
    session['mail_backend'] = backend
    current_app.logger.info(f"Setting mail backend to {backend!r} (session + cookie)")
    resp = jsonify({'success': True, 'mail_backend': backend})
    # Cookie ensures the choice persists even if session doesn't (e.g. in some Docker/proxy setups)
    resp.set_cookie('mail_backend', backend, max_age=60 * 60 * 24 * 7, samesite='Lax', path='/')
    return resp

