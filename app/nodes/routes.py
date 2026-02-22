import logging
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.nodes import bp
from app.extensions import db
from app.models import Node
from app.tart_client import TartAPIError

logger = logging.getLogger(__name__)


def admin_required(f):
    """Decorator: requires current_user.is_admin."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)

    return decorated


@bp.route('/')
@login_required
@admin_required
def index():
    """Node status dashboard."""
    nodes_health = current_app_node_manager().get_all_nodes_health()
    return render_template('nodes/index.html', nodes_health=nodes_health)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_node():
    if request.method == 'POST':
        name = request.form['name'].strip()
        host = request.form['host'].strip()
        ssh_user = request.form['ssh_user'].strip()
        ssh_key_path = request.form['ssh_key_path'].strip()
        agent_port = int(request.form.get('agent_port', 7000))
        max_vms = int(request.form.get('max_vms', 2))

        if Node.query.filter_by(name=name).first():
            flash(f'Node "{name}" already exists.', 'danger')
        else:
            node = Node(
                name=name,
                host=host,
                ssh_user=ssh_user,
                ssh_key_path=ssh_key_path,
                agent_port=agent_port,
                max_vms=max_vms,
            )
            db.session.add(node)
            db.session.commit()
            logger.info("Node added: %s (%s)", name, host)
            flash(f'Node "{name}" added.', 'success')
            return redirect(url_for('nodes.index'))
    return render_template('nodes/index.html', nodes_health=[], show_add_form=True)


@bp.route('/<int:node_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_node(node_id):
    node = Node.query.get_or_404(node_id)
    node.active = not node.active
    db.session.commit()
    state = 'activated' if node.active else 'deactivated'
    flash(f'Node "{node.name}" {state}.', 'success')
    return redirect(url_for('nodes.index'))


@bp.route('/<int:node_id>/health')
@login_required
@admin_required
def node_health(node_id):
    node = Node.query.get_or_404(node_id)
    try:
        from flask import current_app
        health = current_app.tart.get_health(node)
        return jsonify(health)
    except TartAPIError as e:
        return jsonify({'error': str(e)}), 502


def current_app_node_manager():
    from flask import current_app
    return current_app.node_manager
