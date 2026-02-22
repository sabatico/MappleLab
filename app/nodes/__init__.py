from flask import Blueprint

bp = Blueprint('nodes', __name__, template_folder='../templates/nodes')
from app.nodes import routes  # noqa: F401
