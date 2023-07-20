from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func


class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(10))


class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    github_id = db.Column(db.Integer, unique=True)
    github_name = db.Column(db.String(150))
    name = db.Column(db.String(150))
    email = db.Column(db.String(150), unique=True)
    # password = db.Column(db.String(150))
