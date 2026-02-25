import logging
import re
import secrets
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from sqlalchemy.orm import selectinload
from app.admin import bp
from app.extensions import db, bcrypt
from app.models import User, VM, AppSettings, GoldImage
from app.registry_inventory import storage_breakdown, delete_orphan_by_digest
from app.registry_cleanup import cleanup_vm_registry_tag
from app.tart_client import TartAPIError
from app.api.routes import _advance_async_op
from app.utils import admin_required
from app.email import send_invite_email, send_test_email
from app.usage_events import ensure_vm_status_baseline, set_vm_status
from app.gold_distribution import trigger_gold_distribution
from app.admin.usage_metrics import build_usage_by_user
from app.main.routes import (
    _sanitize_registry_tag,
    _check_registry_space_for_save,
    _agent_vm_name,
    _agent_vm_size_on_disk_gb,
    _verify_vm_absent_on_node,
    _registry_authority_from_config,
)

logger = logging.getLogger(__name__)


def _op_stage_label(op_status):
    labels = {
        'stopping': 'Stopping VM',
        'pushing': 'Saving to registry',
        'deleting': 'Cleaning local VM',
        'pulling': 'Downloading VM from registry',
        'cloning': 'Finalizing local VM image',
        'starting': 'Starting VM',
        'done': 'Completed',
        'error': 'Failed',
        'idle': 'Idle',
    }
    return labels.get((op_status or '').strip().lower(), (op_status or 'Working').title())


def _int_field(name, default):
    value = request.form.get(name, '').strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _redirect_overview():
    return redirect(request.referrer or url_for('admin.overview'))


def _redirect_registry_storage():
    return redirect(request.referrer or url_for('admin.registry_storage'))


def _gold_registry_tag(name):
    """Build registry tag for gold image: gold-images/<name>:latest."""
    authority = _registry_authority_from_config()
    if not authority:
        return None
    safe = re.sub(r'[^a-z0-9]+', '-', (name or '').strip().lower())
    safe = re.sub(r'-{2,}', '-', safe).strip('-') or 'gold'
    raw = f'{authority}/gold-images/{safe}:latest'
    return _sanitize_registry_tag(raw)


def _upsert_settings_from_form():
    settings = AppSettings.query.get(1)
    if not settings:
        settings = AppSettings(id=1)
        db.session.add(settings)
    settings.smtp_host = request.form.get('smtp_host', '').strip() or None
    settings.smtp_port = _int_field('smtp_port', 587)
    settings.smtp_user = request.form.get('smtp_user', '').strip() or None
    # Never persist SMTP passwords in the DB. Password can be provided via
    # MAIL_PASSWORD env var or as a runtime-only override from the settings form.
    runtime_smtp_password = request.form.get('smtp_password', '').strip()
    settings.smtp_password = None
    settings.smtp_from = request.form.get('smtp_from', '').strip() or None
    security_mode = request.form.get('smtp_security', 'tls').strip().lower()
    if security_mode == 'ssl':
        settings.smtp_use_ssl = True
        settings.smtp_use_tls = False
    elif security_mode == 'none':
        settings.smtp_use_ssl = False
        settings.smtp_use_tls = False
    else:
        settings.smtp_use_ssl = False
        settings.smtp_use_tls = True
    return settings, runtime_smtp_password


@bp.route('/users')
@login_required
@admin_required
def users():
    user_rows = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=user_rows)


@bp.route('/overview')
@login_required
@admin_required
def overview():
    """
    Admin operational overview: all users and their running/stopped/archived VMs
    with status-aware action controls.
    """
    users = User.query.order_by(User.created_at.desc()).all()
    status_groups = ('running', 'stopped', 'archived', 'failed', 'pushing', 'pulling')
    vm_rows = (
        VM.query
        .options(selectinload(VM.node))
        .filter(VM.status.in_(status_groups))
        .order_by(VM.user_id.asc(), VM.name.asc())
        .all()
    )

    # Advance async ops (including gold push completion) before rendering.
    for vm in vm_rows:
        if vm.status in ('pushing', 'pulling') and vm.node:
            try:
                if _advance_async_op(vm):
                    db.session.commit()
            except TartAPIError:
                pass

    grouped = {
        user.id: {status: [] for status in status_groups}
        for user in users
    }
    for vm in vm_rows:
        grouped.setdefault(vm.user_id, {status: [] for status in status_groups})
        grouped[vm.user_id][vm.status].append(vm)

    # One-time snapshot of async op status for in-progress rows.
    op_snapshots = {}
    for vm in vm_rows:
        if vm.status not in ('pushing', 'pulling') or not vm.node:
            continue
        try:
            op = current_app.tart.get_op_status(vm.node, vm.name) or {}
            op_snapshots[vm.id] = {
                'stage': _op_stage_label(op.get('status')),
                'progress_pct': op.get('progress_pct'),
                'transferred_gb': op.get('transferred_gb'),
                'total_gb': op.get('total_gb'),
                'last_progress_line': op.get('last_progress_line'),
            }
        except TartAPIError:
            op_snapshots[vm.id] = {'stage': 'Node unreachable'}

    return render_template(
        'admin/overview.html',
        users=users,
        grouped=grouped,
        status_groups=status_groups,
        op_snapshots=op_snapshots,
    )


@bp.route('/registry-storage')
@login_required
@admin_required
def registry_storage():
    registry_url = (current_app.config.get('REGISTRY_URL') or '').strip()
    configured_total = current_app.config.get('REGISTRY_STORAGE_TOTAL_GB')
    try:
        breakdown = storage_breakdown(registry_url, configured_total_gb=configured_total)
    except Exception as e:
        logger.warning('registry_storage() inventory load failed: %s', e)
        flash(f'Could not load full registry inventory: {e}', 'warning')
        breakdown = {
            'trackable': [],
            'orphaned': [],
            'trackable_used_gb': 0,
            'orphaned_used_gb': 0,
            'used_gb': 0,
            'total_gb': configured_total,
            'free_gb': configured_total,
        }
    return render_template(
        'admin/registry_storage.html',
        registry_url=registry_url,
        breakdown=breakdown,
        trackable=breakdown['trackable'],
        orphaned=breakdown['orphaned'],
    )


@bp.route('/registry-storage/orphans/delete', methods=['POST'])
@login_required
@admin_required
def delete_registry_orphan():
    registry_url = (current_app.config.get('REGISTRY_URL') or '').strip()
    repo = request.form.get('repo', '').strip()
    digest = request.form.get('digest', '').strip()
    result = delete_orphan_by_digest(registry_url, repo, digest)
    if result.get('ok'):
        logger.info(
            'admin.delete_registry_orphan ok repo=%s digest=%s status=%s',
            repo,
            digest,
            result.get('status_code'),
        )
        flash('Orphaned registry artefact deleted.', 'success')
    else:
        logger.warning(
            'admin.delete_registry_orphan failed repo=%s digest=%s status=%s error=%s',
            repo,
            digest,
            result.get('status_code'),
            result.get('error'),
        )
        flash(f'Orphan delete failed: {result.get("error") or "unknown error"}', 'warning')
    return _redirect_registry_storage()


@bp.route('/users/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', 'user').strip().lower()
    if not email:
        flash('Email is required.', 'danger')
        return redirect(url_for('admin.users'))
    if User.query.filter((User.email == email) | (User.username == email)).first():
        flash('User with this email already exists.', 'danger')
        return redirect(url_for('admin.users'))

    user = User(
        username=email,
        email=email,
        password_hash=bcrypt.generate_password_hash(secrets.token_urlsafe(24)).decode('utf-8'),
        is_admin=(role == 'admin'),
        max_active_vms=_int_field('max_active_vms', 1),
        max_saved_vms=_int_field('max_saved_vms', 2),
        disk_quota_gb=_int_field('disk_quota_gb', 100),
        must_set_password=True,
        invite_token=secrets.token_urlsafe(32),
        invited_at=datetime.utcnow(),
    )
    db.session.add(user)
    db.session.commit()
    sent = send_invite_email(user)
    flash(
        f'User "{email}" created. ' + ('Invite email sent.' if sent else 'SMTP not configured; invite email not sent.'),
        'success' if sent else 'warning',
    )
    logger.info("Admin created user %s (admin=%s)", email, user.is_admin)
    return redirect(url_for('admin.users'))


@bp.route('/vms/<int:vm_id>/start', methods=['POST'])
@login_required
@admin_required
def start_vm(vm_id):
    vm = VM.query.get_or_404(vm_id)
    ensure_vm_status_baseline(vm, source='system', context='admin_start_baseline')
    if vm.status not in ('stopped', 'failed'):
        flash(f'VM "{vm.name}" is not startable (status: {vm.status}).', 'warning')
        return _redirect_overview()
    if not vm.node:
        flash(f'VM "{vm.name}" has no assigned node.', 'warning')
        return _redirect_overview()
    if not vm.node.active:
        flash(
            f'Node "{vm.node.name}" is deactivated; start is blocked for "{vm.name}".',
            'warning',
        )
        return _redirect_overview()

    try:
        current_app.tart.start_vm(vm.node, vm.name)
        set_vm_status(vm, 'running', source='ui', context='admin_start_vm')
        vm.last_started_at = datetime.utcnow()
        vm.status_detail = None
        db.session.commit()
        flash(f'VM "{vm.name}" started.', 'success')
    except TartAPIError as e:
        flash(f'Start failed for "{vm.name}": {e}', 'danger')
    return _redirect_overview()


@bp.route('/vms/<int:vm_id>/stop', methods=['POST'])
@login_required
@admin_required
def stop_vm(vm_id):
    vm = VM.query.get_or_404(vm_id)
    ensure_vm_status_baseline(vm, source='system', context='admin_stop_baseline')
    if vm.status != 'running':
        flash(f'VM "{vm.name}" is not running (status: {vm.status}).', 'warning')
        return _redirect_overview()
    if not vm.node:
        flash(f'VM "{vm.name}" has no assigned node.', 'warning')
        return _redirect_overview()

    try:
        current_app.direct_tcp_proxy.stop_proxy(vm.name)
        current_app.tart.stop_vnc(vm.node, vm.name)
    except TartAPIError:
        pass

    try:
        current_app.tart.stop_vm(vm.node, vm.name)
        set_vm_status(vm, 'stopped', source='ui', context='admin_stop_vm')
        vm.status_detail = None
        db.session.commit()
        flash(f'VM "{vm.name}" stopped.', 'success')
    except TartAPIError as e:
        flash(f'Stop failed for "{vm.name}": {e}', 'danger')
    return _redirect_overview()


@bp.route('/vms/<int:vm_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_vm(vm_id):
    vm = VM.query.get_or_404(vm_id)
    ensure_vm_status_baseline(vm, source='system', context='admin_archive_baseline')
    if vm.status not in ('running', 'stopped'):
        flash(f'VM "{vm.name}" is not archivable (status: {vm.status}).', 'warning')
        return _redirect_overview()
    if not vm.node:
        flash(f'VM "{vm.name}" has no assigned source node.', 'warning')
        return _redirect_overview()

    ok, required_gb, available_gb, reason = _check_registry_space_for_save(vm)
    if not ok:
        logger.warning(
            'admin.archive_vm(%s) preflight failed: required=%s available=%s reason=%s',
            vm.name, required_gb, available_gb, reason,
        )
        flash(reason, 'danger')
        return _redirect_overview()

    size_info = None
    try:
        node_vms = current_app.tart.list_vms(vm.node)
        size_info = next((item for item in node_vms if _agent_vm_name(item) == vm.name), None)
    except TartAPIError:
        size_info = None

    try:
        registry_tag = _sanitize_registry_tag(vm.registry_tag)
        if registry_tag != vm.registry_tag:
            vm.registry_tag = registry_tag
        vm.disk_size_gb = _agent_vm_size_on_disk_gb(size_info) or vm.disk_size_gb
        current_app.tart.save_vm(vm.node, vm.name, registry_tag)
        set_vm_status(vm, 'pushing', source='ui', context='admin_archive_vm')
        vm.status_detail = None
        db.session.commit()
        flash(f'VM "{vm.name}" archiving started (push in progress).', 'info')
    except TartAPIError as e:
        flash(f'Archive failed for "{vm.name}": {e}', 'danger')
    return _redirect_overview()


@bp.route('/vms/<int:vm_id>/resume', methods=['POST'])
@login_required
@admin_required
def resume_vm(vm_id):
    vm = VM.query.get_or_404(vm_id)
    ensure_vm_status_baseline(vm, source='system', context='admin_resume_baseline')
    if vm.status != 'archived':
        flash(f'VM "{vm.name}" is not archived (status: {vm.status}).', 'warning')
        return _redirect_overview()

    node = current_app.node_manager.find_best_node()
    if not node:
        flash(f'No available node to resume "{vm.name}".', 'danger')
        return _redirect_overview()

    try:
        registry_tag = _sanitize_registry_tag(vm.registry_tag)
        if registry_tag != vm.registry_tag:
            vm.registry_tag = registry_tag
        current_app.tart.restore_vm(node, vm.name, registry_tag)
        set_vm_status(vm, 'pulling', source='ui', context='admin_resume_vm')
        vm.node_id = node.id
        vm.status_detail = None
        db.session.commit()
        flash(f'VM "{vm.name}" resume started on "{node.name}".', 'info')
    except TartAPIError as e:
        flash(f'Resume failed for "{vm.name}": {e}', 'danger')
    return _redirect_overview()


@bp.route('/vms/<int:vm_id>/make-gold', methods=['GET', 'POST'])
@login_required
@admin_required
def make_gold_image(vm_id):
    vm = VM.query.get_or_404(vm_id)
    ensure_vm_status_baseline(vm, source='system', context='admin_make_gold_baseline')
    if vm.status not in ('running', 'stopped'):
        flash(f'VM "{vm.name}" must be running or stopped to capture as gold image.', 'warning')
        return _redirect_overview()
    if not vm.node:
        flash(f'VM "{vm.name}" has no assigned node.', 'warning')
        return _redirect_overview()

    if request.method == 'GET':
        return render_template(
            'admin/make_gold_image.html',
            vm=vm,
        )

    gold_name = request.form.get('gold_name', '').strip()
    description = request.form.get('description', '').strip() or None
    if not gold_name:
        flash('Gold image name is required.', 'warning')
        return render_template(
            'admin/make_gold_image.html',
            vm=vm,
            gold_name=gold_name,
            description=description,
        )

    registry_tag = _gold_registry_tag(gold_name)
    if not registry_tag:
        flash('Could not build registry tag. Check REGISTRY_URL configuration.', 'danger')
        return _redirect_overview()

    ok, required_gb, available_gb, reason = _check_registry_space_for_save(vm)
    if not ok:
        flash(reason, 'danger')
        return _redirect_overview()

    size_info = None
    try:
        node_vms = current_app.tart.list_vms(vm.node)
        size_info = next((item for item in node_vms if _agent_vm_name(item) == vm.name), None)
    except TartAPIError:
        pass

    try:
        vm.disk_size_gb = _agent_vm_size_on_disk_gb(size_info) or vm.disk_size_gb
        current_app.tart.save_vm(vm.node, vm.name, registry_tag, expected_disk_gb=vm.disk_size_gb)
        set_vm_status(vm, 'pushing', source='ui', context='admin_make_gold')
        vm.status_detail = f'gold:{gold_name}'
        db.session.commit()

        gold = GoldImage.query.filter_by(name=gold_name).first()
        if gold:
            gold.registry_tag = registry_tag
            gold.base_image = vm.base_image
            gold.disk_size_gb = vm.disk_size_gb
            gold.description = description
            gold.source_vm_name = vm.name
            gold.updated_at = datetime.utcnow()
            gold.created_by_id = current_user.id
        else:
            gold = GoldImage(
                name=gold_name,
                registry_tag=registry_tag,
                base_image=vm.base_image,
                disk_size_gb=vm.disk_size_gb,
                description=description,
                source_vm_name=vm.name,
                created_by_id=current_user.id,
            )
            db.session.add(gold)
        db.session.commit()

        flash(f'Gold image "{gold_name}" capture started. VM will be archived when push completes.', 'info')
    except TartAPIError as e:
        flash(f'Failed to start gold capture for "{vm.name}": {e}', 'danger')
    return _redirect_overview()


@bp.route('/vms/<int:vm_id>/repull', methods=['POST'])
@login_required
@admin_required
def repull_vm(vm_id):
    vm = VM.query.get_or_404(vm_id)
    ensure_vm_status_baseline(vm, source='system', context='admin_repull_baseline')
    if vm.status != 'failed':
        flash(f'VM "{vm.name}" is not in failed state (status: {vm.status}).', 'warning')
        return _redirect_overview()
    if not vm.node:
        flash(f'VM "{vm.name}" has no assigned node for re-pull.', 'warning')
        return _redirect_overview()
    if not vm.node.active:
        flash(
            f'Node "{vm.node.name}" is deactivated; re-pull is blocked for "{vm.name}".',
            'warning',
        )
        return _redirect_overview()
    if not vm.registry_tag:
        flash(f'VM "{vm.name}" has no registry tag; cannot re-pull.', 'danger')
        return _redirect_overview()

    try:
        registry_tag = _sanitize_registry_tag(vm.registry_tag)
        if registry_tag != vm.registry_tag:
            vm.registry_tag = registry_tag
        current_app.tart.restore_vm(
            vm.node,
            vm.name,
            registry_tag,
            expected_disk_gb=vm.disk_size_gb,
        )
        set_vm_status(vm, 'pulling', source='ui', context='admin_repull_vm')
        vm.status_detail = None
        db.session.commit()
        flash(f'Re-pull started for VM "{vm.name}" on "{vm.node.name}".', 'info')
    except TartAPIError as e:
        flash(f'Re-pull failed for "{vm.name}": {e}', 'danger')
    return _redirect_overview()


@bp.route('/vms/<int:vm_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_vm(vm_id):
    vm = VM.query.get_or_404(vm_id)
    if vm.node:
        try:
            current_app.direct_tcp_proxy.stop_proxy(vm.name)
            current_app.tart.stop_vnc(vm.node, vm.name)
        except TartAPIError:
            pass
        try:
            current_app.tart.stop_vm(vm.node, vm.name)
        except TartAPIError:
            pass
        try:
            current_app.tart.delete_vm(vm.node, vm.name)
            _verify_vm_absent_on_node(vm.node, vm.name, 'admin_delete_vm')
        except TartAPIError as e:
            set_vm_status(vm, 'failed', source='ui', context='admin_delete_vm_failed')
            vm.status_detail = f'Admin delete failed on node: {e}'
            db.session.commit()
            flash(f'Failed to delete VM "{vm.name}" on node: {e}', 'danger')
            return _redirect_overview()

    cleanup_result = cleanup_vm_registry_tag(vm, operation='admin_delete_vm')
    if not cleanup_result.get('ok'):
        flash(
            f'VM "{vm.name}" deleted locally, but registry cleanup failed. Check logs and retry cleanup later.',
            'warning',
        )

    db.session.delete(vm)
    db.session.commit()
    flash(f'VM "{vm.name}" deleted.', 'success')
    return _redirect_overview()


@bp.route('/vms/<int:vm_id>/cleanup-retry', methods=['POST'])
@login_required
@admin_required
def cleanup_retry(vm_id):
    vm = VM.query.get_or_404(vm_id)
    if not vm.registry_tag:
        flash(f'VM "{vm.name}" has no registry tag to clean up.', 'warning')
        return _redirect_overview()
    if vm.cleanup_status == 'pending':
        flash(f'Cleanup retry for "{vm.name}" is already in progress.', 'info')
        return _redirect_overview()

    vm.cleanup_status = 'pending'
    vm.cleanup_last_error = None
    db.session.commit()
    result = cleanup_vm_registry_tag(vm, operation='admin_cleanup_retry')
    db.session.commit()
    if result.get('ok'):
        flash(f'Cleanup retry succeeded for "{vm.name}".', 'success')
    else:
        flash(
            f'Cleanup retry failed for "{vm.name}": {vm.cleanup_last_error or "Unknown error"}',
            'warning',
        )
    return _redirect_overview()


@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        role = request.form.get('role', 'user').strip().lower()
        user.is_admin = (role == 'admin')
        user.max_active_vms = _int_field('max_active_vms', user.max_active_vms or 1)
        user.max_saved_vms = _int_field('max_saved_vms', user.max_saved_vms or 2)
        user.disk_quota_gb = _int_field('disk_quota_gb', user.disk_quota_gb or 100)
        db.session.commit()
        flash(f'Updated settings for {user.email or user.username}.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/edit_user.html', user=user)


@bp.route('/users/<int:user_id>/resend-invite', methods=['POST'])
@login_required
@admin_required
def resend_invite(user_id):
    user = User.query.get_or_404(user_id)
    if not user.email:
        flash('User has no email address.', 'danger')
        return redirect(url_for('admin.users'))
    user.invite_token = secrets.token_urlsafe(32)
    user.invited_at = datetime.utcnow()
    user.must_set_password = True
    db.session.commit()
    sent = send_invite_email(user)
    flash(
        f'Invite regenerated for {user.email}. ' + ('Email sent.' if sent else 'SMTP not configured; email not sent.'),
        'success' if sent else 'warning',
    )
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        flash('Cannot delete the last admin account.', 'danger')
        return redirect(url_for('admin.users'))

    VM.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash('User deleted.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/gold-images')
@login_required
@admin_required
def gold_images():
    gold_images_list = GoldImage.query.order_by(GoldImage.updated_at.desc()).all()
    return render_template('admin/gold_images.html', gold_images=gold_images_list)


@bp.route('/gold-images/<int:gold_id>/redistribute', methods=['POST'])
@login_required
@admin_required
def gold_image_redistribute(gold_id):
    gold = GoldImage.query.get_or_404(gold_id)
    if trigger_gold_distribution(gold.name):
        flash(f'Re-distribution started for "{gold.name}".', 'info')
    else:
        flash(f'Could not start re-distribution for "{gold.name}".', 'warning')
    return redirect(url_for('admin.gold_images'))


@bp.route('/gold-images/<int:gold_id>/delete', methods=['POST'])
@login_required
@admin_required
def gold_image_delete(gold_id):
    gold = GoldImage.query.get_or_404(gold_id)
    name = gold.name
    db.session.delete(gold)
    db.session.commit()
    flash(f'Gold image "{name}" deleted. Registry artefact left for manual cleanup.', 'success')
    return redirect(url_for('admin.gold_images'))


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    if request.method == 'POST':
        _, runtime_smtp_password = _upsert_settings_from_form()
        if runtime_smtp_password:
            current_app.config['MAIL_PASSWORD'] = runtime_smtp_password
            flash(
                'SMTP password applied for current runtime only. '
                'Set MAIL_PASSWORD in environment for persistent secure config.',
                'warning',
            )
        db.session.commit()
        flash('Settings saved.', 'success')
        return redirect(url_for('admin.settings'))
    settings_obj = AppSettings.query.get(1)
    return render_template('admin/settings.html', settings=settings_obj)


@bp.route('/usage')
@login_required
@admin_required
def usage():
    usage_metrics = build_usage_by_user()
    return render_template(
        'admin/usage.html',
        usage_by_user=usage_metrics['users'],
        usage_generated_at=usage_metrics['generated_at'],
        usage_running_warn_seconds=usage_metrics['running_warn_seconds'],
        usage_vnc_warn_seconds=usage_metrics['vnc_warn_seconds'],
        format_duration=usage_metrics['format_duration'],
    )


@bp.route('/settings/test-email', methods=['POST'])
@login_required
@admin_required
def test_email():
    to_email = request.form.get('test_email_to', '').strip()
    if not to_email:
        flash('Test email recipient is required.', 'warning')
        return redirect(url_for('admin.settings'))
    sent = send_test_email(to_email)
    flash(
        'Test email sent.' if sent else 'Failed to send test email. Check SMTP settings/logs.',
        'success' if sent else 'danger',
    )
    return redirect(url_for('admin.settings'))
