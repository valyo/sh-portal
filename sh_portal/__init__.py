import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session
from flask_mail import Mail

# Load environment variables from .env file
load_dotenv()

db = SQLAlchemy()
migrate = Migrate()

# Import models
from .models import Season, Admin

# GitHub OAuth settings
GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET')
GITHUB_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
GITHUB_API_URL = 'https://api.github.com/user'

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

mail = Mail()

def create_app():
    app = Flask(__name__)

    # Configure the Flask application using environment variables
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # GitHub OAuth configuration
    app.config['GITHUB_CLIENT_ID'] = GITHUB_CLIENT_ID
    app.config['GITHUB_CLIENT_SECRET'] = GITHUB_CLIENT_SECRET
    app.config['GITHUB_AUTHORIZE_URL'] = GITHUB_AUTHORIZE_URL
    app.config['GITHUB_TOKEN_URL'] = GITHUB_TOKEN_URL
    app.config['GITHUB_API_URL'] = GITHUB_API_URL
    app.config['OAUTH_REDIRECT_URI'] = os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:8087/callback')
    app.config['GOOGLE_SHEET_ID'] = os.getenv('GOOGLE_SHEET_ID')

    # Mail configuration: MAIL_BACKEND=mailcatcher (default) or google
    mail_backend = os.getenv('MAIL_BACKEND', 'mailcatcher').lower()
    if mail_backend == 'google':
        app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
        app.config['MAIL_USE_TLS'] = True
        app.config['MAIL_USE_SSL'] = False
        app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', '')
        app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', '')
    else:
        # mailcatcher (default): local catch-all, no auth (ignore credentials in .env)
        app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'mailcatcher')
        app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 1025))
        app.config['MAIL_USE_TLS'] = False
        app.config['MAIL_USE_SSL'] = False
        app.config['MAIL_USERNAME'] = ''
        app.config['MAIL_PASSWORD'] = ''
    app.config['MAIL_DEBUG'] = False
    app.config['MAIL_BACKEND'] = mail_backend  # for templates/debug if needed

    # Initialize database and migrations
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # Create database tables
    with app.app_context():
        db.create_all()
        print('Database tables created successfully!')

    # Import flask commands - all
    from sh_portal.commands import (
        create_new_admin
    )
    # Add flask commands - general
    app.cli.add_command(create_new_admin)

    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Register blueprints
    from sh_portal.home import main
    from sh_portal.seasons import seasons
    from sh_portal.customers import customers_bp
    from sh_portal.andelsbiodling import andelsbiodling
    from sh_portal.lammandel import lammandel

    app.register_blueprint(main)
    app.register_blueprint(seasons)
    app.register_blueprint(customers_bp)
    app.register_blueprint(andelsbiodling)
    app.register_blueprint(lammandel)

    @app.context_processor
    def inject_version_and_mail():
        from .utils import get_effective_mail_backend_with_source
        version_path = os.path.join(os.path.dirname(__file__), '..', 'VERSION')
        try:
            with open(version_path) as f:
                version = f.read().strip() or 'dev'
        except OSError:
            version = 'dev'
        effective_mail, mail_backend_source = get_effective_mail_backend_with_source(app)
        return {
            'app_version': version,
            'mail_backend': effective_mail,
            'mail_backend_source': mail_backend_source,
        }

    return app