import logging
from datetime import datetime
from flask import jsonify, current_app, request, render_template
from flask_login import login_required, current_user
from app.api import bp
from app.extensions import db
from app.models import VM, Node, GoldImage, GoldImageNode
from app.registry_cleanup import cleanup_vm_registry_tag
from app.tart_client import TartAPIError
from app.usage_events import ensure_vm_status_baseline, set_vm_status
from app.utils import admin_required

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
        set_vm_status(vm, normalized, source='api_poller', context='sync_vm_status_from_agent')
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


def _parse_gold_name(status_detail):
    """Extract gold image name from status_detail 'gold:<name>' marker."""
    value = (status_detail or '').strip()
    if not value.startswith('gold:'):
        return None
    return value.split(':', 1)[1].strip() or None


from app.gold_distribution import trigger_gold_distribution


def _normalize_async_error(raw_error):
    """
    Convert verbose agent/tart errors into concise UI-friendly failure text.
    """
    text = (raw_error or 'Unknown error').strip()
    lowered = text.lower()
    if (
        'no space left on device' in lowered
        or 'err":28' in lowered
        or 'err\\":28' in lowered
        or "'err': 28" in lowered
        or 'errno 28' in lowered
        or 'enospc' in lowered
    ):
        return (
            'Registry storage is full (no space left on device). '
            'Free space in the registry data volume and retry.'
        )
    if 'could not connect to the server' in lowered:
        return (
            'Destination node could not reach the registry server. '
            'Verify REGISTRY_URL uses manager IP/hostname (not localhost) and is reachable from that node.'
        )
    if 'internet connection appears to be offline' in lowered:
        return (
            'Destination node cannot reach registry endpoint during tart pull. '
            'Check routing/firewall/proxy on the node and ensure REGISTRY_URL points to manager IP/hostname.'
        )
    if len(text) > 220:
        text = f'{text[:217]}...'
    return text


def _verify_vm_absent_on_node(node, vm_name, context):
    """
    Best-effort post-action verification for node cleanup.
    Logs vm_exists=false/true for operational auditing.
    """
    if not node:
        return
    try:
        node_vms = current_app.tart.list_vms(node)
        exists = any(_agent_vm_name(item) == vm_name for item in node_vms)
        logger.info("%s cleanup verification vm=%s node=%s vm_exists=%s",
                    context, vm_name, node.name, str(exists).lower())
    except TartAPIError as e:
        logger.warning(
            "%s cleanup verification skipped vm=%s node=%s error=%s",
            context,
            vm_name,
            node.name,
            e,
        )


def _advance_async_op(vm):
    """
    Progress VM async operations (pushing/pulling) from agent op status.
    Returns True when VM state was changed and should be committed.
    """
    if vm.status not in ('pushing', 'pulling') or not vm.node:
        return False

    op = current_app.tart.get_op_status(vm.node, vm.name)
    if op.get('status') == 'idle':
        set_vm_status(vm, 'failed', source='api_poller', context='advance_async_idle')
        vm.status_detail = (
            'Operation state was lost on the node agent (reported idle). '
            'Please retry save/resume/migrate.'
        )
        return True

    if op.get('status') == 'done':
        if vm.status == 'pushing':
            source_node = vm.node
            gold_name = _parse_gold_name(vm.status_detail)
            if gold_name:
                set_vm_status(vm, 'archived', source='api_poller', context='gold_push_done')
                vm.node_id = None
                vm.last_saved_at = datetime.utcnow()
                vm.status_detail = None
                _verify_vm_absent_on_node(source_node, vm.name, 'gold_push_done')
                trigger_gold_distribution(gold_name)
            else:
                target_node_id = _parse_migration_target(vm.status_detail)
                if target_node_id:
                    target_node = Node.query.filter_by(id=target_node_id, active=True).first()
                if not target_node:
                    set_vm_status(vm, 'archived', source='api_poller', context='migration_push_done_target_unavailable')
                    vm.node_id = None
                    vm.last_saved_at = datetime.utcnow()
                    vm.status_detail = (
                        'Migration push completed but target node is unavailable. '
                        'Use Resume to start from registry.'
                    )
                else:
                    registry_tag = (vm.registry_tag or '').strip()
                    current_app.tart.restore_vm(
                        target_node,
                        vm.name,
                        registry_tag,
                        expected_disk_gb=vm.disk_size_gb,
                    )
                    set_vm_status(vm, 'pulling', source='api_poller', context='migration_restore_started')
                    vm.node_id = target_node.id
                    vm.status_detail = None
                    _verify_vm_absent_on_node(source_node, vm.name, 'migration_push_done')
                else:
                    set_vm_status(vm, 'archived', source='api_poller', context='archive_push_done')
                    vm.node_id = None
                    vm.last_saved_at = datetime.utcnow()
                    vm.status_detail = None
                    _verify_vm_absent_on_node(source_node, vm.name, 'archive_push_done')
        elif vm.status == 'pulling':
            set_vm_status(vm, 'running', source='api_poller', context='restore_done')
            vm.last_started_at = datetime.utcnow()
            vm.status_detail = None
            cleanup_vm_registry_tag(vm, operation='restore_success')
        return True

    if op.get('status') == 'error':
        set_vm_status(vm, 'failed', source='api_poller', context='advance_async_error')
        vm.status_detail = _normalize_async_error(op.get('error', 'Unknown error'))
        return True

    return False


def _op_stage_label(op_status):
    labels = {
        'stopping': 'Stopping VM',
        'pushing': 'Saving to registry',
        'deleting': 'Cleaning local VM',
        'pulling': 'Downloading VM from registry',
        'cloning': 'Finalizing local VM image',
        'starting': 'Starting VM',
    }
    return labels.get((op_status or '').strip().lower(), (op_status or 'Working').title())


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
    for vm in vms:
        ensure_vm_status_baseline(vm, source='system', context='list_vms_baseline')

    # Advance async ops and reconcile local statuses from agent VM states.
    changed = False
    async_vms = [vm for vm in vms if vm.status in ('pushing', 'pulling') and vm.node]
    for vm in async_vms:
        try:
            if _advance_async_op(vm):
                changed = True
                logger.info("list_vms() — %r op advanced → %s", vm.name, vm.status)
        except TartAPIError:
            pass

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
    ensure_vm_status_baseline(vm, source='system', context='vm_status_baseline')

    # If async op in progress, poll the agent for completion.
    if vm.status in ('pushing', 'pulling') and vm.node:
        try:
            if _advance_async_op(vm):
                db.session.commit()
                if vm.status == 'failed':
                    logger.error("vm_status() — %r op error: %s", vm_name, vm.status_detail)
                else:
                    logger.info("vm_status() — %r op advanced → %s", vm_name, vm.status)
        except TartAPIError:
            pass  # agent unreachable; keep polling
    elif _sync_vm_status_from_agent(vm):
        db.session.commit()

    if is_htmx:
        return render_template('_partials/vm_status_area.html', vm=vm)

    return jsonify({'name': vm_name, 'status': vm.status})


@bp.route('/vms/<vm_name>/operation')
@login_required
def vm_operation(vm_name):
    """
    Operation details for VM detail page.
    Includes live stage and transfer metrics when agent reports them.
    """
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    ensure_vm_status_baseline(vm, source='system', context='vm_operation_baseline')
    op = None
    changed = False

    if vm.status in ('pushing', 'pulling') and vm.node:
        try:
            op = current_app.tart.get_op_status(vm.node, vm.name)
            if _advance_async_op(vm):
                changed = True
                if vm.status in ('pushing', 'pulling') and vm.node:
                    op = current_app.tart.get_op_status(vm.node, vm.name)
        except TartAPIError:
            op = None
    elif _sync_vm_status_from_agent(vm):
        changed = True

    if changed:
        db.session.commit()

    return render_template(
        '_partials/vm_operation_progress.html',
        vm=vm,
        op=op,
        op_stage_label=_op_stage_label,
    )


def _advance_gold_image_node(gn):
    """
    Poll agent for image pull status and update GoldImageNode.
    Returns True if status changed.
    """
    if gn.status != 'pulling' or not gn.op_key or not gn.gold_image:
        return False
    node = Node.query.get(gn.node_id)
    if not node:
        return False
    try:
        op = current_app.tart.get_image_op_status(node, gn.op_key)
    except TartAPIError:
        return False
    status = (op or {}).get('status')
    if status == 'done':
        gn.status = 'ready'
        gn.status_detail = None
        gn.completed_at = datetime.utcnow()
        return True
    if status == 'error':
        gn.status = 'failed'
        gn.status_detail = (op or {}).get('error', 'Unknown error')
        gn.completed_at = datetime.utcnow()
        return True
    return False


@bp.route('/gold-images/<int:gold_id>/distribution')
@login_required
@admin_required
def gold_image_distribution(gold_id):
    """
    HTMX-polled partial for gold image node distribution status.
    Advances GoldImageNode status from agent poll, returns HTML.
    """
    gold = GoldImage.query.get_or_404(gold_id)
    gold.nodes  # force load relationship

    for gn in gold.nodes:
        if gn.status == 'pulling':
            try:
                if _advance_gold_image_node(gn):
                    db.session.commit()
            except Exception:
                pass

    return render_template(
        'admin/_partials/gold_image_distribution.html',
        gold=gold,
    )
