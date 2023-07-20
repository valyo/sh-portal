import os

from flask import Flask,render_template,redirect,url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

from flask_dance.contrib.github import make_github_blueprint, github
from flask_login import LoginManager

db = SQLAlchemy()
load_dotenv()

def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_prefixed_env()

    from .models import Admin, Season
    db.init_app(app)
    create_database(app)

    login_manager = LoginManager()
    login_manager.login_view = 'views.home'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return Admin.query.get(int(id))

    # Import flask commands - all
    from sh_portal.commands import (
        create_new_admin
    )


    # Add flask commands - general
    app.cli.add_command(create_new_admin)
    
    
    
    # if test_config is None:
    #     # load the instance config, if it exists, when not testing
    #     app.config.from_pyfile('config.py', silent=True)
    # else:
    #     # load the test config if passed in
    #     app.config.from_mapping(test_config)

     # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass


    from sh_portal.views import views
    from sh_portal.admin import admin
    from sh_portal.dashboard import dashboard

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(admin, url_prefix='/')
    app.register_blueprint(dashboard, url_prefix='/')
    
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    github_blueprint = make_github_blueprint(client_id='c7d3b33e1a319dbd4147', client_secret='aff79429bb7f89f4de455410b4aed6ac87886e62')
    app.register_blueprint(github_blueprint, url_prefix='/github_login')

    return app

def create_database(app):
    if not os.path.exists('sh_portal/' + os.getenv("DB_NAME")):
        with app.app_context():
            db.create_all()
        print('Created Database!')