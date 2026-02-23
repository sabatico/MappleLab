import logging
import secrets
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required
from app.admin import bp
from app.extensions import db, bcrypt
from app.models import User, VM, AppSettings
from app.utils import admin_required
from app.email import send_invite_email, send_test_email

logger = logging.getLogger(__name__)


def _int_field(name, default):
    value = request.form.get(name, '').strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _upsert_settings_from_form():
    settings = AppSettings.query.get(1)
    if not settings:
        settings = AppSettings(id=1)
        db.session.add(settings)
    settings.smtp_host = request.form.get('smtp_host', '').strip() or None
    settings.smtp_port = _int_field('smtp_port', 587)
    settings.smtp_user = request.form.get('smtp_user', '').strip() or None
    settings.smtp_password = request.form.get('smtp_password', '').strip() or None
    settings.smtp_from = request.form.get('smtp_from', '').strip() or None
    settings.smtp_use_tls = bool(request.form.get('smtp_use_tls'))
    return settings


@bp.route('/users')
@login_required
@admin_required
def users():
    user_rows = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=user_rows)


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


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    if request.method == 'POST':
        _upsert_settings_from_form()
        db.session.commit()
        flash('Settings saved.', 'success')
        return redirect(url_for('admin.settings'))
    settings_obj = AppSettings.query.get(1)
    return render_template('admin/settings.html', settings=settings_obj)


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
