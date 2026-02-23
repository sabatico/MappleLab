import logging
from datetime import datetime
from flask import jsonify, current_app, request, render_template
from flask_login import login_required, current_user
from app.api import bp
from app.extensions import db
from app.models import VM, Node
from app.tart_client import TartAPIError

logger = logging.getLogger(__name__)


def _agent_vm_name(item):
    """Extract VM name from agent payload across key variants."""
    return (item or {}).get('name') or (item or {}).get('Name')


def _agent_vm_state(item):
    """Extract VM state/status from agent payload across key variants."""
    return (item or {}).get('status') or (item or {}).get('state') or (item or {}).get('State')


def _normalize_agent_vm_status(status):
    """Map agent VM status values to the UI/DB status vocabulary."""
    value = (status or '').strip().lower()
    if value in ('running', 'stopped'):
        return value
    return None


def _sync_vm_status_from_agent(vm, node_vms_by_name=None):
    """
    Best-effort status reconciliation for local node-backed VMs.
    Keeps DB status aligned with actual agent VM state.
    """
    if not vm.node or vm.status not in ('creating', 'running', 'stopped', 'failed'):
        return False

    if node_vms_by_name is None:
        try:
            node_vms = current_app.tart.list_vms(vm.node)
        except TartAPIError:
            return False
        node_vms_by_name = {
            _agent_vm_name(item): item
            for item in node_vms
            if _agent_vm_name(item)
        }

    node_vm = node_vms_by_name.get(vm.name)
    if not node_vm:
        return False

    normalized = _normalize_agent_vm_status(_agent_vm_state(node_vm))
    if normalized and vm.status != normalized:
        vm.status = normalized
        vm.status_detail = None
        if normalized == 'running':
            vm.last_started_at = datetime.utcnow()
        return True
    return False


def _parse_migration_target(status_detail):
    value = (status_detail or '').strip()
    if not value.startswith('migrate:'):
        return None
    try:
        return int(value.split(':', 1)[1])
    except (TypeError, ValueError):
        return None


@bp.route('/vms')
@login_required
def list_vms():
    """
    List all VMs for the current user.
    HTMX request → HTML partial; otherwise → JSON.
    Used by dashboard for auto-refresh polling.
    """
    is_htmx = bool(request.headers.get('HX-Request'))
    logger.debug("list_vms() — htmx=%s user=%s", is_htmx, current_user.username)

    vms = VM.query.filter_by(user_id=current_user.id).all()

    # Reconcile stale local statuses from agent-reported VM states.
    changed = False
    local_vms = [vm for vm in vms if vm.node and vm.status in ('creating', 'running', 'stopped', 'failed')]
    node_vm_maps = {}
    for vm in local_vms:
        if vm.node_id in node_vm_maps:
            continue
        try:
            node_vms = current_app.tart.list_vms(vm.node)
            node_vm_maps[vm.node_id] = {
                _agent_vm_name(item): item
                for item in node_vms
                if _agent_vm_name(item)
            }
        except TartAPIError:
            node_vm_maps[vm.node_id] = None

    for vm in local_vms:
        node_snapshot = node_vm_maps.get(vm.node_id)
        if node_snapshot and _sync_vm_status_from_agent(vm, node_snapshot):
            changed = True
    if changed:
        db.session.commit()

    if is_htmx:
        return render_template('_partials/vm_table.html', vms=vms)

    return jsonify([{
        'id': vm.id,
        'name': vm.name,
        'status': vm.status,
        'base_image': vm.base_image,
        'node': vm.node.name if vm.node else None,
    } for vm in vms])


@bp.route('/vms/<vm_name>/status')
@login_required
def vm_status(vm_name):
    """
    Status for a single VM. Polls agent if an async op is in progress.
    HTMX request → status badge HTML; otherwise → JSON.
    """
    is_htmx = bool(request.headers.get('HX-Request'))
    logger.debug("vm_status(vm_name=%r) — htmx=%s", vm_name, is_htmx)

    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()

    # If async op in progress, poll the agent for completion.
    if vm.status in ('pushing', 'pulling') and vm.node:
        try:
            op = current_app.tart.get_op_status(vm.node, vm_name)
            if op.get('status') == 'done':
                if vm.status == 'pushing':
                    target_node_id = _parse_migration_target(vm.status_detail)
                    if target_node_id:
                        target_node = Node.query.filter_by(id=target_node_id, active=True).first()
                        if not target_node:
                            vm.status = 'archived'
                            vm.node_id = None
                            vm.last_saved_at = datetime.utcnow()
                            vm.status_detail = (
                                'Migration push completed but target node is unavailable. '
                                'Use Resume to start from registry.'
                            )
                        else:
                            registry_tag = (vm.registry_tag or '').strip()
                            current_app.tart.restore_vm(target_node, vm_name, registry_tag)
                            vm.status = 'pulling'
                            vm.node_id = target_node.id
                            vm.status_detail = None
                    else:
                        vm.status = 'archived'
                        vm.node_id = None
                        vm.last_saved_at = datetime.utcnow()
                elif vm.status == 'pulling':
                    vm.status = 'running'
                    vm.last_started_at = datetime.utcnow()
                    vm.status_detail = None
                db.session.commit()
                logger.info("vm_status() — %r op done → %s", vm_name, vm.status)
            elif op.get('status') == 'error':
                vm.status = 'failed'
                vm.status_detail = op.get('error', 'Unknown error')
                db.session.commit()
                logger.error("vm_status() — %r op error: %s", vm_name, vm.status_detail)
        except TartAPIError:
            pass  # agent unreachable; keep polling
    elif _sync_vm_status_from_agent(vm):
        db.session.commit()

    if is_htmx:
        return render_template('_partials/vm_status_badge.html', vm=vm)

    return jsonify({'name': vm_name, 'status': vm.status})
