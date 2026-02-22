import logging
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.main import bp
from app.extensions import db
from app.models import VM
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


def _reconcile_local_vms_for_user(user_id):
    """
    Best-effort reconciliation of local VM DB statuses from node agent /vms.
    Used before first dashboard render to avoid stale status at page load.
    """
    vms = VM.query.filter_by(user_id=user_id).all()
    local_vms = [vm for vm in vms if vm.node and vm.status in ('creating', 'running', 'stopped')]
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


@bp.route('/')
@login_required
def dashboard():
    """Main dashboard — lists VMs owned by the current user."""
    logger.debug("dashboard() — user=%s", current_user.username)
    _reconcile_local_vms_for_user(current_user.id)
    vms = VM.query.filter_by(user_id=current_user.id).all()
    return render_template('main/dashboard.html', vms=vms)


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
    return render_template('main/vm_detail.html',
                           vm=vm,
                           ip_address=ip_address,
                           console_port=console_port)


@bp.route('/vms/<vm_name>/save', methods=['POST'])
@login_required
def save_vm(vm_name):
    """Trigger Save & Shutdown: stops VM, pushes to registry, frees local disk."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status != 'running':
        flash(f'VM is not running (status: {vm.status}).', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    node = vm.node
    try:
        current_app.tart.save_vm(node, vm_name, vm.registry_tag)
        vm.status = 'pushing'
        db.session.commit()
        logger.info("save_vm() — %r pushing to registry", vm_name)
        flash(f'VM "{vm_name}" is saving. This may take a few minutes.', 'info')
    except TartAPIError as e:
        logger.error("save_vm() — failed: %s", e)
        flash(f'Save failed: {e}', 'danger')

    return redirect(url_for('main.vm_detail', vm_name=vm_name))


@bp.route('/vms/<vm_name>/resume', methods=['POST'])
@login_required
def resume_vm(vm_name):
    """Resume a saved VM: pull from registry and start on best available node."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status != 'archived':
        flash(f'VM is not archived (status: {vm.status}).', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    node = current_app.node_manager.find_best_node()
    if not node:
        flash('No Mac nodes available.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        current_app.tart.restore_vm(node, vm_name, vm.registry_tag)
        vm.status = 'pulling'
        vm.node_id = node.id
        db.session.commit()
        logger.info("resume_vm() — %r pulling from registry onto node %s", vm_name, node.name)
        flash(f'VM "{vm_name}" is resuming. Pull in progress\u2026', 'info')
    except TartAPIError as e:
        logger.error("resume_vm() — failed: %s", e)
        flash(f'Resume failed: {e}', 'danger')

    return redirect(url_for('main.vm_detail', vm_name=vm_name))


@bp.route('/vms/<vm_name>/start', methods=['POST'])
@login_required
def start_vm(vm_name):
    """Start a local VM currently in stopped state."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status != 'stopped':
        flash(f'VM is not stopped (status: {vm.status}).', 'warning')
        return _redirect_after_action(vm_name)
    if not vm.node:
        flash('VM has no assigned node. Use Resume for archived VMs.', 'warning')
        return _redirect_after_action(vm_name)

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
