import flask
from flask import Blueprint,render_template,redirect,url_for,flash

from flask_dance.contrib.github import make_github_blueprint, github
from flask_login import login_user, current_user, logout_user, login_required

from .models import Admin

admin   = Blueprint("auth", __name__)


@admin.route('/login')
def login():
    if not github.authorized:
        return redirect(url_for('github.login'))
    else:
        account_info = github.get('/user')
        if account_info.ok:
            account_info_json = account_info.json()
            github_id = account_info_json['id']
            # flask.current_app.logger.info(github_id)
            local_user = Admin.query.filter_by(github_id=github_id).first()
            flask.current_app.logger.info(local_user)
            if github_id == local_user.github_id:
            # if github_id == 435342:
                flash('Logged in successfully!', category='success')
                login_user(local_user, remember=True)
                return redirect(url_for('dashboard.display'))
            else:
                flash('Nothing to do here!', category='error')
                return render_template('index.html', user=current_user, message=f"Hello Sulyoipulyo, you've nothing to do here!", data=account_info_json['id'])


            

@admin.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('views.home'))