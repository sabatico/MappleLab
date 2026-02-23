import logging
import re
from datetime import datetime
from urllib.parse import urlparse
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.main import bp
from app.extensions import db
from app.models import VM, Node
from app.tart_client import TartAPIError

logger = logging.getLogger(__name__)

DEFAULT_VM_CPU = 4
DEFAULT_VM_MEMORY_MB = 4096
MAX_VM_CPU = 8
MAX_VM_MEMORY_MB = 16384


def _agent_vm_name(item):
    """Extract VM name from agent payload across key variants."""
    return (item or {}).get('name') or (item or {}).get('Name')


def _agent_vm_state(item):
    """Extract VM state/status from agent payload across key variants."""
    return (item or {}).get('status') or (item or {}).get('state') or (item or {}).get('State')


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _agent_vm_size_on_disk_gb(item):
    """
    Extract VM SizeOnDisk (GB) from agent payload across key variants.
    """
    if not item:
        return None
    candidates = (
        item.get('SizeOnDisk'),
        item.get('sizeOnDisk'),
        item.get('sizeondisk'),
        item.get('size_on_disk'),
    )
    for candidate in candidates:
        parsed = _as_float(candidate)
        if parsed is not None:
            return parsed
    return None


def _sanitize_registry_tag(tag):
    """
    Ensure OCI registry tag is tart-compatible.
    Strips URL schemes and removes accidental '/v2' host path segment.
    """
    value = (tag or '').strip()
    if not value:
        return value

    if value.startswith(('http://', 'https://')):
        parsed = urlparse(value)
        value = f'{parsed.netloc}{parsed.path}'

    value = value.strip('/')
    parts = [p for p in value.split('/') if p]
    if len(parts) >= 2 and parts[1].lower() == 'v2':
        parts.pop(1)
    elif parts and parts[0].lower() == 'v2':
        parts.pop(0)

    # Auto-heal legacy tags that still point to localhost by switching to
    # configured registry authority when it is non-localhost.
    if parts:
        configured_authority = _registry_authority_from_config()
        configured_host = (urlparse(f'//{configured_authority}').hostname or '').lower() if configured_authority else ''
        current_host = (urlparse(f'//{parts[0]}').hostname or '').lower()
        if (
            current_host in ('localhost', '127.0.0.1')
            and configured_host
            and configured_host not in ('localhost', '127.0.0.1')
        ):
            parts[0] = configured_authority

    # Normalize repository path components (everything after authority) to a
    # Tart-safe subset to avoid parse errors for values like email addresses.
    def _normalize_repo_segment(value):
        text = (value or '').strip().lower()
        if not text:
            return 'vm'
        text = re.sub(r'[^a-z0-9]+', '-', text)
        text = re.sub(r'-{2,}', '-', text).strip('-')
        return text or 'vm'

    for idx in range(1, len(parts)):
        segment = parts[idx]
        name_part = segment
        tag_part = None
        if idx == (len(parts) - 1) and ':' in segment:
            name_part, tag_part = segment.rsplit(':', 1)
        normalized = _normalize_repo_segment(name_part)
        parts[idx] = f'{normalized}:{tag_part}' if tag_part else normalized
    return '/'.join(parts)


def _registry_authority_from_config():
    """
    Extract registry authority (host[:port]) from REGISTRY_URL.
    Accepts host:port or http(s)://host:port[/...].
    """
    value = (current_app.config.get('REGISTRY_URL') or '').strip()
    if not value:
        return None
    if value.startswith(('http://', 'https://')):
        parsed = urlparse(value)
        return (parsed.netloc or '').strip() or None
    parsed = urlparse(f'//{value}')
    return (parsed.netloc or '').strip() or None


def _registry_host_from_config():
    authority = _registry_authority_from_config()
    if not authority:
        return None
    return (urlparse(f'//{authority}').hostname or '').strip() or None


def _registry_node_for_vm(vm):
    """
    Resolve which node hosts the Docker registry for this save/migrate operation.
    - REGISTRY_URL localhost/127.0.0.1 => source node itself
    - otherwise match configured host against known nodes
    """
    if not vm.node:
        return None

    host = (_registry_host_from_config() or '').lower()
    if host in ('', 'localhost', '127.0.0.1'):
        return vm.node

    candidate = Node.query.filter_by(host=host).first()
    return candidate or vm.node


def _reconcile_local_vms_for_user(user_id):
    """
    Best-effort reconciliation of local VM DB statuses from node agent /vms.
    Used before first dashboard render to avoid stale status at page load.
    """
    vms = VM.query.filter_by(user_id=user_id).all()
    local_vms = [vm for vm in vms if vm.node and vm.status in ('creating', 'running', 'stopped', 'failed')]
    if not local_vms:
        return

    changed = False
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
        node_snapshot = node_vm_maps.get(vm.node_id) or {}
        node_vm = node_snapshot.get(vm.name)
        if not node_vm:
            continue
        node_state = (_agent_vm_state(node_vm) or '').strip().lower()
        if node_state in ('running', 'stopped') and vm.status != node_state:
            vm.status = node_state
            vm.status_detail = None
            if node_state == 'running':
                vm.last_started_at = datetime.utcnow()
            changed = True

    if changed:
        db.session.commit()


def _redirect_after_action(vm_name):
    """Return to current page when possible; fall back to vm detail."""
    return redirect(request.referrer or url_for('main.vm_detail', vm_name=vm_name))


def _active_vm_count_for_user(user_id):
    return VM.query.filter_by(user_id=user_id, status='running').count()


def _saved_vm_count_for_user(user_id):
    # "Inactive" includes both registry-archived VMs and stopped local VMs.
    return VM.query.filter_by(user_id=user_id).filter(
        VM.status.in_(('archived', 'stopped'))
    ).count()


def _saved_vm_disk_used_gb_for_user(user_id):
    rows = VM.query.filter_by(user_id=user_id, status='archived').all()
    return round(sum((vm.disk_size_gb or 0) for vm in rows), 1)


def _user_quota_snapshot(user):
    return {
        'active_count': _active_vm_count_for_user(user.id),
        'inactive_count': _saved_vm_count_for_user(user.id),
        'saved_disk_used_gb': _saved_vm_disk_used_gb_for_user(user.id),
        'max_active_vms': user.max_active_vms or 1,
        'max_saved_vms': user.max_saved_vms or 2,
        'disk_quota_gb': user.disk_quota_gb or 100,
    }


def _check_registry_space_for_save(vm):
    """
    Fast preflight for save/migrate:
    compare VM on-disk size to node free disk before starting push.
    Returns (ok, required_gb, available_gb, reason).
    """
    if not vm.node:
        return False, None, None, 'VM has no assigned source node.'

    try:
        node_vms = current_app.tart.list_vms(vm.node)
    except TartAPIError as e:
        return False, None, None, f'Could not read VM size from source node: {e}'

    node_vm = next((item for item in node_vms if _agent_vm_name(item) == vm.name), None)
    size_gb = _agent_vm_size_on_disk_gb(node_vm)
    if size_gb is None:
        return False, None, None, 'Could not determine VM SizeOnDisk from node.'

    registry_node = _registry_node_for_vm(vm)
    if not registry_node:
        return False, None, None, 'Could not resolve registry host node for this operation.'

    try:
        health = current_app.tart.get_health(registry_node)
    except TartAPIError as e:
        return False, None, None, f'Could not read registry free disk from "{registry_node.name}": {e}'

    free_gb = _as_float((health or {}).get('registry_free_gb'))
    probe = (health or {}).get('registry_probe')
    path = (health or {}).get('registry_path')
    if free_gb is None:
        # Fallback for older agents that don't expose registry-specific stats.
        free_gb = _as_float((health or {}).get('disk_free_gb'))
        probe = probe or 'legacy_disk_free_fallback'

    if free_gb is None:
        return False, None, None, (
            f'Registry node "{registry_node.name}" did not report free disk information.'
        )

    # Safety headroom for registry temp upload files and metadata.
    required_gb = round(size_gb + 2.0, 1)
    available_gb = round(free_gb, 1)
    if available_gb < required_gb:
        return False, required_gb, available_gb, (
            f'Not enough free space for save/migrate. '
            f'Required {required_gb:.1f} GB (VM size {size_gb:.1f} + 2.0 GB buffer), '
            f'available {available_gb:.1f} GB on registry storage '
            f'("{registry_node.name}" path={path or "unknown"} source={probe or "unknown"}).'
        )

    return True, required_gb, available_gb, None


def _migration_candidates(current_node_id):
    """
    Return nodes (excluding current) that are online and have free slots.
    """
    candidates = []
    for node, health in current_app.node_manager.get_all_nodes_health():
        if not health:
            continue
        free_slots = health.get('free_slots', 0)
        if node.id == current_node_id or free_slots <= 0:
            continue
        candidates.append((node, free_slots))
    return candidates


@bp.route('/')
@login_required
def dashboard():
    """Main dashboard — lists VMs owned by the current user."""
    logger.debug("dashboard() — user=%s", current_user.username)
    _reconcile_local_vms_for_user(current_user.id)
    vms = VM.query.filter_by(user_id=current_user.id).all()
    quota = _user_quota_snapshot(current_user)
    return render_template('main/dashboard.html', vms=vms, quota=quota)


@bp.route('/vms/create', methods=['GET', 'POST'])
@login_required
def create_vm():
    """GET: Show the create VM form. POST: Create VM via TART agent."""
    if request.method == 'GET':
        logger.debug("create_vm() GET — rendering form")
        return render_template('main/create_vm.html',
                               images=current_app.config['TART_IMAGES'])

    name = request.form.get('name', '').strip()
    image = request.form.get('image', '').strip()
    cpu = request.form.get('cpu', type=int)
    memory = request.form.get('memory', type=int)
    cpu = cpu or DEFAULT_VM_CPU
    memory = memory or DEFAULT_VM_MEMORY_MB

    if cpu < 1 or cpu > MAX_VM_CPU:
        flash(f'CPU must be between 1 and {MAX_VM_CPU}.', 'warning')
        return render_template('main/create_vm.html',
                               images=current_app.config['TART_IMAGES'])
    if memory < 1024 or memory > MAX_VM_MEMORY_MB:
        flash(f'Memory must be between 1024 and {MAX_VM_MEMORY_MB} MB.', 'warning')
        return render_template('main/create_vm.html',
                               images=current_app.config['TART_IMAGES'])

    logger.info("create_vm() POST — name=%r, image=%r, cpu=%r, memory=%r",
                name, image, cpu, memory)

    if not name:
        flash('VM name is required.', 'warning')
        return render_template('main/create_vm.html',
                               images=current_app.config['TART_IMAGES'])
    if not image:
        flash('Image is required.', 'warning')
        return render_template('main/create_vm.html',
                               images=current_app.config['TART_IMAGES'])

    if _active_vm_count_for_user(current_user.id) >= (current_user.max_active_vms or 1):
        flash(f'Active VM limit ({current_user.max_active_vms}) reached.', 'danger')
        return redirect(url_for('main.dashboard'))

    node = current_app.node_manager.find_best_node()
    if not node:
        flash('No Mac nodes available with free VM slots.', 'danger')
        return redirect(url_for('main.dashboard'))

    registry_tag = current_app.node_manager.registry_tag_for(
        current_user.username, name, current_app.config['REGISTRY_URL']
    )

    vm = VM(
        name=name,
        user_id=current_user.id,
        node_id=node.id,
        status='creating',
        base_image=image,
        registry_tag=registry_tag,
        cpu=cpu,
        memory_mb=memory,
    )
    db.session.add(vm)
    db.session.commit()

    try:
        current_app.tart.create_vm(node, name, image, cpu, memory)
        current_app.tart.start_vm(node, name)
        # Confirm effective state from node to avoid stale optimistic status.
        vm.status = 'running'
        try:
            node_vms = current_app.tart.list_vms(node)
            node_vm = next((item for item in node_vms if _agent_vm_name(item) == name), None)
            node_status = (_agent_vm_state(node_vm) or '').strip().lower()
            if node_status in ('running', 'stopped'):
                vm.status = node_status
        except TartAPIError as e:
            logger.warning("create_vm() — status reconcile skipped: %s", e)

        if vm.status == 'running':
            vm.last_started_at = datetime.utcnow()
        db.session.commit()
        logger.info("create_vm() — VM %r created on node %s with status=%s", name, node.name, vm.status)
        if vm.status == 'running':
            flash(f'VM "{name}" created and started.', 'success')
        else:
            flash(f'VM "{name}" created, but is currently {vm.status}.', 'warning')
    except TartAPIError as e:
        logger.error("create_vm() — failed: %s", e)
        vm.status = 'failed'
        vm.status_detail = str(e)
        db.session.commit()
        flash(f'Failed to create VM: {e}', 'danger')

    return redirect(url_for('main.dashboard'))


@bp.route('/vms/<vm_name>')
@login_required
def vm_detail(vm_name):
    """Detail page for a single VM."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()

    ip_address = None
    if vm.status == 'running' and vm.node:
        try:
            ip_address = current_app.tart.get_vm_ip(vm.node, vm_name)
        except TartAPIError:
            pass

    console_port = current_app.tunnel_manager.get_tunnel_port(vm_name)
    migrate_targets = []
    if vm.node and vm.status in ('running', 'stopped', 'failed'):
        migrate_targets = _migration_candidates(vm.node_id)
    return render_template('main/vm_detail.html',
                           vm=vm,
                           ip_address=ip_address,
                           console_port=console_port,
                           migrate_targets=migrate_targets)


@bp.route('/vms/<vm_name>/save', methods=['POST'])
@login_required
def save_vm(vm_name):
    """Save VM to registry and archive it."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status not in ('running', 'stopped'):
        flash(f'VM is not savable (status: {vm.status}).', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    node = vm.node

    inactive_now = _saved_vm_count_for_user(current_user.id)
    inactive_limit = current_user.max_saved_vms or 2
    # Saving a stopped VM keeps it inactive (stopped -> archived), while
    # saving a running VM increases inactive count by 1.
    inactive_delta = 0 if vm.status == 'stopped' else 1
    if (inactive_now + inactive_delta) > inactive_limit:
        flash(f'Inactive VM limit ({inactive_limit}) reached.', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    size_info = None
    try:
        node_vms = current_app.tart.list_vms(node)
        size_info = next((item for item in node_vms if _agent_vm_name(item) == vm.name), None)
    except TartAPIError:
        size_info = None
    current_vm_size_gb = _agent_vm_size_on_disk_gb(size_info) or 0
    used_saved_gb = _saved_vm_disk_used_gb_for_user(current_user.id)
    projected_gb = round(used_saved_gb + current_vm_size_gb, 1)
    if projected_gb > (current_user.disk_quota_gb or 100):
        flash(
            f'Disk quota exceeded. Required {projected_gb:.1f} GB, '
            f'quota is {current_user.disk_quota_gb} GB.',
            'danger',
        )
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    ok, required_gb, available_gb, reason = _check_registry_space_for_save(vm)
    if not ok:
        flash(reason, 'danger')
        logger.warning(
            "save_vm() — preflight failed for %r on %s: required=%s available=%s reason=%s",
            vm_name,
            node.name if node else 'unknown',
            required_gb,
            available_gb,
            reason,
        )
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    try:
        registry_tag = _sanitize_registry_tag(vm.registry_tag)
        if registry_tag != vm.registry_tag:
            vm.registry_tag = registry_tag
        vm.disk_size_gb = current_vm_size_gb or vm.disk_size_gb
        current_app.tart.save_vm(
            node,
            vm_name,
            registry_tag,
            expected_disk_gb=(current_vm_size_gb or vm.disk_size_gb),
        )
        vm.status = 'pushing'
        db.session.commit()
        logger.info("save_vm() — %r pushing to registry", vm_name)
        flash(f'VM "{vm_name}" is saving. This may take a few minutes.', 'info')
    except TartAPIError as e:
        logger.error("save_vm() — failed: %s", e)
        flash(f'Save failed: {e}', 'danger')

    return redirect(url_for('main.vm_detail', vm_name=vm_name))


@bp.route('/vms/<vm_name>/migrate', methods=['POST'])
@login_required
def migrate_vm(vm_name):
    """
    Migrate VM to another node:
    source node save/push -> target node restore/start.
    The restore leg starts automatically once push finishes.
    """
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status not in ('running', 'stopped', 'failed'):
        flash(f'VM is not migratable (status: {vm.status}).', 'warning')
        return _redirect_after_action(vm_name)
    if not vm.node:
        flash('VM has no assigned node to migrate from.', 'warning')
        return _redirect_after_action(vm_name)

    target_node_id = request.form.get('target_node_id', type=int)
    if not target_node_id:
        flash('Please select a target node for migration.', 'warning')
        return _redirect_after_action(vm_name)

    target_node = Node.query.filter_by(id=target_node_id, active=True).first()
    if not target_node:
        flash('Selected target node is not available.', 'danger')
        return _redirect_after_action(vm_name)
    if target_node.id == vm.node_id:
        flash('Select a different node for migration.', 'warning')
        return _redirect_after_action(vm_name)

    try:
        health = current_app.tart.get_health(target_node)
        if health.get('free_slots', 0) <= 0:
            flash(f'Target node "{target_node.name}" has no free VM slots.', 'danger')
            return _redirect_after_action(vm_name)
    except TartAPIError as e:
        flash(f'Target node "{target_node.name}" is unreachable: {e}', 'danger')
        return _redirect_after_action(vm_name)

    ok, required_gb, available_gb, reason = _check_registry_space_for_save(vm)
    if not ok:
        flash(reason, 'danger')
        logger.warning(
            "migrate_vm() — preflight failed for %r on %s: required=%s available=%s reason=%s",
            vm_name,
            vm.node.name if vm.node else 'unknown',
            required_gb,
            available_gb,
            reason,
        )
        return _redirect_after_action(vm_name)

    try:
        registry_tag = _sanitize_registry_tag(vm.registry_tag)
        if registry_tag != vm.registry_tag:
            vm.registry_tag = registry_tag
        current_app.tart.save_vm(
            vm.node,
            vm_name,
            registry_tag,
            expected_disk_gb=vm.disk_size_gb,
        )
        vm.status = 'pushing'
        # status_detail marker consumed by api.vm_status when push completes.
        vm.status_detail = f'migrate:{target_node.id}'
        db.session.commit()
        logger.info(
            "migrate_vm() — %r pushing on %s for restore onto %s",
            vm_name,
            vm.node.name,
            target_node.name,
        )
        flash(
            f'VM "{vm_name}" migration started. Saving on "{vm.node.name}" '
            f'then restoring on "{target_node.name}".',
            'info',
        )
    except TartAPIError as e:
        logger.error("migrate_vm() — failed: %s", e)
        flash(f'Migrate failed: {e}', 'danger')

    return _redirect_after_action(vm_name)


@bp.route('/vms/<vm_name>/resume', methods=['POST'])
@login_required
def resume_vm(vm_name):
    """Resume a saved VM: pull from registry and start on best available node."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status != 'archived':
        flash(f'VM is not archived (status: {vm.status}).', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    if _active_vm_count_for_user(current_user.id) >= (current_user.max_active_vms or 1):
        flash(f'Active VM limit ({current_user.max_active_vms}) reached.', 'danger')
        return redirect(url_for('main.dashboard'))

    node = current_app.node_manager.find_best_node()
    if not node:
        flash('No Mac nodes available.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        registry_tag = _sanitize_registry_tag(vm.registry_tag)
        if registry_tag != vm.registry_tag:
            vm.registry_tag = registry_tag
        current_app.tart.restore_vm(
            node,
            vm_name,
            registry_tag,
            expected_disk_gb=vm.disk_size_gb,
        )
        vm.status = 'pulling'
        vm.node_id = node.id
        db.session.commit()
        logger.info("resume_vm() — %r pulling from registry onto node %s", vm_name, node.name)
        flash(f'VM "{vm_name}" is resuming. Pull in progress\u2026', 'info')
    except TartAPIError as e:
        logger.error("resume_vm() — failed: %s", e)
        flash(f'Resume failed: {e}', 'danger')

    return redirect(url_for('main.vm_detail', vm_name=vm_name))


@bp.route('/vms/<vm_name>/repull', methods=['POST'])
@login_required
def repull_vm(vm_name):
    """
    Retry pull/restore for failed migrations/resumes on the currently assigned node.
    """
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status != 'failed':
        flash(f'VM is not in failed state (status: {vm.status}).', 'warning')
        return _redirect_after_action(vm_name)
    if not vm.node:
        flash('VM has no assigned node for re-pull.', 'warning')
        return _redirect_after_action(vm_name)
    if not vm.registry_tag:
        flash('VM has no registry tag; cannot re-pull.', 'danger')
        return _redirect_after_action(vm_name)

    try:
        registry_tag = _sanitize_registry_tag(vm.registry_tag)
        if registry_tag != vm.registry_tag:
            vm.registry_tag = registry_tag
        current_app.tart.restore_vm(
            vm.node,
            vm_name,
            registry_tag,
            expected_disk_gb=vm.disk_size_gb,
        )
        vm.status = 'pulling'
        vm.status_detail = None
        db.session.commit()
        logger.info("repull_vm() — %r pulling from registry onto node %s", vm_name, vm.node.name)
        flash(f'Re-pull started for VM "{vm_name}" on "{vm.node.name}".', 'info')
    except TartAPIError as e:
        logger.error("repull_vm() — failed: %s", e)
        flash(f'Re-pull failed: {e}', 'danger')

    return _redirect_after_action(vm_name)


@bp.route('/vms/<vm_name>/start', methods=['POST'])
@login_required
def start_vm(vm_name):
    """Start a local VM currently in stopped state."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status not in ('stopped', 'failed'):
        flash(f'VM is not startable (status: {vm.status}).', 'warning')
        return _redirect_after_action(vm_name)
    if not vm.node:
        flash('VM has no assigned node. Use Resume for archived VMs.', 'warning')
        return _redirect_after_action(vm_name)
    if _active_vm_count_for_user(current_user.id) >= (current_user.max_active_vms or 1):
        flash(f'Active VM limit ({current_user.max_active_vms}) reached.', 'danger')
        return _redirect_after_action(vm_name)

    # If VM is already running/stopped on node, recover status first.
    try:
        node_vms = current_app.tart.list_vms(vm.node)
        node_vm = next((item for item in node_vms if _agent_vm_name(item) == vm_name), None)
        node_state = (_agent_vm_state(node_vm) or '').strip().lower()
        if node_state == 'running':
            vm.status = 'running'
            vm.status_detail = None
            vm.last_started_at = datetime.utcnow()
            db.session.commit()
            flash(f'VM "{vm_name}" is already running; status was recovered.', 'info')
            return _redirect_after_action(vm_name)
    except TartAPIError:
        pass

    try:
        current_app.tart.start_vm(vm.node, vm_name)
        vm.status = 'running'
        vm.last_started_at = datetime.utcnow()
        vm.status_detail = None
        db.session.commit()
        logger.info("start_vm() — %r started", vm_name)
        flash(f'VM "{vm_name}" started.', 'success')
    except TartAPIError as e:
        logger.error("start_vm() — failed: %s", e)
        flash(f'Start failed: {e}', 'danger')

    return _redirect_after_action(vm_name)


@bp.route('/vms/<vm_name>/stop', methods=['POST'])
@login_required
def stop_vm(vm_name):
    """Gracefully stop a running VM on its assigned node."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status != 'running':
        flash(f'VM is not running (status: {vm.status}).', 'warning')
        return _redirect_after_action(vm_name)
    if not vm.node:
        flash('VM has no assigned node.', 'danger')
        return _redirect_after_action(vm_name)
    inactive_limit = current_user.max_saved_vms or 2
    inactive_now = _saved_vm_count_for_user(current_user.id)
    # Stopping a running VM turns it into inactive (stopped), so enforce +1.
    if (inactive_now + 1) > inactive_limit:
        flash(
            f'Inactive VM limit ({inactive_limit}) reached. '
            'Delete or start an older inactive VM first.',
            'danger',
        )
        return _redirect_after_action(vm_name)

    current_app.tunnel_manager.stop_tunnel(vm_name)
    try:
        current_app.tart.stop_vnc(vm.node, vm_name)
    except TartAPIError:
        pass

    try:
        current_app.tart.stop_vm(vm.node, vm_name)
        vm.status = 'stopped'
        vm.status_detail = None
        db.session.commit()
        logger.info("stop_vm() — %r stopped", vm_name)
        flash(f'VM "{vm_name}" stopped.', 'success')
    except TartAPIError as e:
        logger.error("stop_vm() — failed: %s", e)
        flash(f'Stop failed: {e}', 'danger')

    return _redirect_after_action(vm_name)


@bp.route('/vms/<vm_name>/delete', methods=['POST'])
@login_required
def delete_vm(vm_name):
    """Delete a VM. Stops VNC tunnel and removes from agent + DB."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()

    current_app.tunnel_manager.stop_tunnel(vm_name)

    if vm.node:
        try:
            current_app.tart.stop_vnc(vm.node, vm_name)
        except TartAPIError:
            pass
        try:
            current_app.tart.stop_vm(vm.node, vm_name)
        except TartAPIError:
            pass
        try:
            current_app.tart.delete_vm(vm.node, vm_name)
        except TartAPIError as e:
            logger.error("delete_vm() — agent delete failed: %s", e)
            vm.status = 'failed'
            vm.status_detail = f'Delete failed on node: {e}'
            db.session.commit()
            flash(
                f'Failed to delete VM "{vm_name}" on node. '
                'VM was kept in dashboard so you can retry.',
                'danger'
            )
            return redirect(url_for('main.vm_detail', vm_name=vm_name))

    db.session.delete(vm)
    db.session.commit()
    logger.info("delete_vm() — %r deleted", vm_name)
    flash(f'VM "{vm_name}" has been deleted.', 'success')
    return redirect(url_for('main.dashboard'))
