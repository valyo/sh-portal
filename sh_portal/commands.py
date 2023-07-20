"""Flask commands runable in container."""

# Imports

# Standard
import re

# Installed
import click
import flask

# Own
from sh_portal import db

@click.command("create-admin")
@click.option("--github_id", "-ghid", type=str, required=True)
@click.option("--github_name", "-ghn", type=str, required=True)
@click.option("--name", "-n", type=str, required=True)
@click.option("--email", "-e", type=str, required=True)
@flask.cli.with_appcontext
def create_new_admin(
    github_id,
    github_name,
    name,
    email,
):
    """Create a new admin.

    Use name and id from github account info, but not email.  
    """
    from sh_portal import models

    error_message = ""
    if re.findall(r"[^0-9]", github_id):
        error_message = "The 'github_id' can only contain numbers."
    elif github_id[0] in [".", "-"]:
        error_message = "The 'github_id' must begin with a letter or number."

    if error_message:
        flask.current_app.logger.error(error_message)
        return

    new_admin = models.Admin(
        github_id=github_id,
        github_name=github_name,
        name=name,
        email=email,
    )
    db.session.add(new_admin)
    db.session.commit()

    flask.current_app.logger.info(f"Admin '{name}' created")
