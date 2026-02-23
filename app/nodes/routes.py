import logging
import time
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from app.nodes import bp
from app.extensions import db
from app.models import Node, VM
from app.tart_client import TartAPIError
from app.utils import admin_required

logger = logging.getLogger(__name__)


def _archive_vm_for_node_deactivation(node, vm, timeout_s=3600):
    """
    Archive one VM during node deactivation and wait until async save completes.
    """
    from flask import current_app
    from app.main.routes import (
        _sanitize_registry_tag,
        _check_registry_space_for_save,
        _agent_vm_name,
        _agent_vm_size_on_disk_gb,
    )

    ok, _, _, reason = _check_registry_space_for_save(vm)
    if not ok:
        raise RuntimeError(reason or 'Registry preflight failed.')

    if not vm.registry_tag:
        vm.registry_tag = current_app.node_manager.registry_tag_for(
            vm.owner.username,
            vm.name,
            current_app.config.get('REGISTRY_URL'),
        )

    # Refresh disk size snapshot before save, when available.
    try:
        node_vms = current_app.tart.list_vms(node)
        size_info = next((item for item in node_vms if _agent_vm_name(item) == vm.name), None)
        vm.disk_size_gb = _agent_vm_size_on_disk_gb(size_info) or vm.disk_size_gb
    except TartAPIError:
        pass

    registry_tag = _sanitize_registry_tag(vm.registry_tag)
    if registry_tag != vm.registry_tag:
        vm.registry_tag = registry_tag

    current_app.tart.save_vm(
        node,
        vm.name,
        registry_tag,
        expected_disk_gb=vm.disk_size_gb,
    )
    vm.status = 'pushing'
    vm.status_detail = None
    db.session.commit()

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        op = current_app.tart.get_op_status(node, vm.name)
        state = (op.get('status') or '').strip().lower()
        if state == 'done':
            vm.status = 'archived'
            vm.node_id = None
            vm.last_saved_at = datetime.utcnow()
            vm.status_detail = None
            db.session.commit()
            return
        if state == 'error':
            error = (op.get('error') or 'Unknown save error').strip()
            vm.status = 'failed'
            vm.status_detail = error[:255]
            db.session.commit()
            raise RuntimeError(error)
        if state == 'idle':
            vm.status = 'failed'
            vm.status_detail = 'Save operation state was lost on node agent (idle).'
            db.session.commit()
            raise RuntimeError(vm.status_detail)
        time.sleep(3)

    vm.status = 'failed'
    vm.status_detail = 'Timed out while archiving during node deactivation.'
    db.session.commit()
    raise RuntimeError(vm.status_detail)

@bp.route('/')
@login_required
@admin_required
def index():
    """Node status dashboard."""
    from flask import current_app
    nodes = Node.query.order_by(Node.name.asc()).all()
    nodes_health = []
    for node in nodes:
        health = None
        if node.active:
            try:
                health = current_app.tart.get_health(node)
            except TartAPIError:
                health = None
        nodes_health.append((node, health))
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

    # Activate path stays immediate.
    if not node.active:
        node.active = True
        db.session.commit()
        flash(f'Node "{node.name}" activated.', 'success')
        return redirect(url_for('nodes.index'))

    # Deactivate path: mark node inactive immediately so scheduler/migration
    # target selection cannot place new work here while drain is in progress.
    node.active = False
    db.session.commit()

    # Then archive local running/stopped VMs on this node.
    blocked = VM.query.filter_by(node_id=node.id).filter(
        VM.status.in_(('creating', 'pushing', 'pulling'))
    ).all()
    if blocked:
        names = ', '.join(vm.name for vm in blocked[:5])
        suffix = '...' if len(blocked) > 5 else ''
        flash(
            f'Node "{node.name}" marked inactive. '
            f'Some operations are still in progress (creating/pushing/pulling): '
            f'{names}{suffix}. Wait for completion, then verify remaining VMs are archived.',
            'warning',
        )
        return redirect(url_for('nodes.index'))

    to_archive = VM.query.filter_by(node_id=node.id).filter(
        VM.status.in_(('running', 'stopped'))
    ).all()

    archived_count = 0
    errors = []
    for vm in to_archive:
        try:
            _archive_vm_for_node_deactivation(node, vm)
            archived_count += 1
        except (RuntimeError, TartAPIError) as e:
            logger.error(
                'toggle_node() — deactivation archive failed node=%s vm=%s error=%s',
                node.name, vm.name, e,
            )
            errors.append(f'{vm.name}: {e}')

    if errors:
        flash(
            f'Node "{node.name}" remains inactive, but failed to archive {len(errors)} VM(s). '
            f'First error: {errors[0]}. Resolve VM issues before reactivating this node.',
            'warning',
        )
        return redirect(url_for('nodes.index'))

    flash(
        f'Node "{node.name}" deactivated. Archived {archived_count} VM(s) from this node first.',
        'success',
    )
    return redirect(url_for('nodes.index'))


@bp.route('/<int:node_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_node(node_id):
    node = Node.query.get_or_404(node_id)
    if node.active:
        flash(f'Node "{node.name}" must be inactive before deletion.', 'warning')
        return redirect(url_for('nodes.index'))

    attached = VM.query.filter_by(node_id=node.id).count()
    if attached > 0:
        flash(
            f'Node "{node.name}" cannot be deleted yet; {attached} VM record(s) still reference it.',
            'warning',
        )
        return redirect(url_for('nodes.index'))

    db.session.delete(node)
    db.session.commit()
    flash(f'Node "{node.name}" deleted.', 'success')
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
