from flask import Blueprint

bp = Blueprint('console', __name__, template_folder='../templates/console')

from app.console import routes  # noqa: F401
