import flask
from flask import Blueprint, render_template
from flask_login import login_required, current_user

views = Blueprint("views", __name__)

@views.route("/")
# @login_required
def home():
    flask.current_app.logger.debug(current_user.is_authenticated)
    return render_template("index.html", user=current_user)

