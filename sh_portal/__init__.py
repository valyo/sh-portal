import os
from urllib.parse import urlparse
from flask import Flask, jsonify, request
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
    # Default DB: instance/sh.db so app and manual edits use the same file (set DATABASE_URL in .env to override)
    default_db = 'sqlite:///' + os.path.join(app.instance_path, 'sh.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # GitHub OAuth configuration
    app.config['GITHUB_CLIENT_ID'] = GITHUB_CLIENT_ID
    app.config['GITHUB_CLIENT_SECRET'] = GITHUB_CLIENT_SECRET
    app.config['GITHUB_AUTHORIZE_URL'] = GITHUB_AUTHORIZE_URL
    app.config['GITHUB_TOKEN_URL'] = GITHUB_TOKEN_URL
    app.config['GITHUB_API_URL'] = GITHUB_API_URL
    app.config['OAUTH_REDIRECT_URI'] = os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:8087/callback')
    app.config['GOOGLE_SHEET_ID'] = os.getenv('GOOGLE_SHEET_ID')
    # Urlencoded forms are no longer capped by Werkzeug's max_form_memory_size
    # (3.1.9+); cap the whole request body instead.
    app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

    # The login cookie is not sent on cross-site POSTs (CSRF); see reject_cross_origin_writes below.
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # Hosts allowed as the Origin of state-changing requests, besides the Host the request came in on.
    app.config['ALLOWED_ORIGIN_HOSTS'] = {
        h.strip() for h in (os.getenv('ALLOWED_ORIGIN_HOSTS') or '').split(',') if h.strip()
    }

    # Where generated invoice PDFs are stored: <INVOICES_DIR>/<andelsbiodling|lammandel>/<season year>/
    app.config['INVOICES_DIR'] = os.path.abspath(
        os.getenv('INVOICES_DIR') or os.path.join(app.root_path, '..', 'invoices')
    )

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
        create_new_admin,
        import_sales,
        link_sales_customers,
    )
    # Add flask commands - general
    app.cli.add_command(create_new_admin)
    app.cli.add_command(import_sales)
    app.cli.add_command(link_sales_customers)

    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Register blueprints
    from sh_portal.home import main
    from sh_portal.seasons import seasons
    from sh_portal.customers import customers_bp
    from sh_portal.andelsbiodling import andelsbiodling
    from sh_portal.lammandel import lammandel
    from sh_portal.sales import sales_bp

    from .utils import MAX_QUANTITY
    app.jinja_env.globals['MAX_QUANTITY'] = MAX_QUANTITY
    from .models import MAX_CUSTOM_PRICE
    app.jinja_env.globals['MAX_CUSTOM_PRICE'] = MAX_CUSTOM_PRICE

    @app.before_request
    def reject_cross_origin_writes():
        """Block POST/PUT/PATCH/DELETE whose Origin header names another site.

        Browsers always send Origin on cross-site form posts and fetches, so this stops a
        malicious page from making a logged-in admin's browser delete invoices etc. Requests
        without an Origin header (scripts, tests) are not browser cross-site requests and pass.
        """
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None
        origin = request.headers.get('Origin')
        if not origin:
            return None
        allowed = {request.host, urlparse(app.config['OAUTH_REDIRECT_URI']).netloc}
        allowed |= app.config['ALLOWED_ORIGIN_HOSTS']
        if urlparse(origin).netloc in allowed - {''}:
            return None
        app.logger.warning(f"Blocked cross-origin {request.method} {request.path} from Origin {origin!r}")
        return jsonify({'error': 'Cross-origin request blocked'}), 403

    app.register_blueprint(main)
    app.register_blueprint(seasons)
    app.register_blueprint(customers_bp)
    app.register_blueprint(andelsbiodling)
    app.register_blueprint(lammandel)
    app.register_blueprint(sales_bp)

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