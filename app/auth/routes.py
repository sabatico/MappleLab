import logging
import secrets
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import bp
from app.extensions import db, bcrypt
from app.models import User

logger = logging.getLogger(__name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        identity = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=identity).first()
        if not user:
            user = User.query.filter_by(username=identity).first()
        password_ok = False
        if user:
            try:
                password_ok = bcrypt.check_password_hash(user.password_hash, password)
            except ValueError:
                password_ok = False
        if user and password_ok:
            if user.must_set_password:
                if not user.invite_token:
                    user.invite_token = secrets.token_urlsafe(32)
                    user.invited_at = datetime.utcnow()
                    db.session.commit()
                flash('Please set your password to continue.', 'info')
                return redirect(url_for('auth.set_password', token=user.invite_token))
            login_user(user)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            logger.info("User %r logged in", user.username)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    logger.info("User %r logged out", current_user.username)
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    flash('Account creation is invitation-only. Please contact an administrator.', 'warning')
    return redirect(url_for('auth.login'))


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        try:
            password_ok = bcrypt.check_password_hash(current_user.password_hash, current_password)
        except ValueError:
            password_ok = False
        if not password_ok:
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html')
        if len(new_password) < 8:
            flash('New password must be at least 8 characters.', 'danger')
            return render_template('auth/change_password.html')
        if new_password != confirm:
            flash('New passwords do not match.', 'danger')
            return render_template('auth/change_password.html')
        current_user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()
        logger.info("User %r changed their password", current_user.username)
        flash('Password changed successfully.', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('auth/change_password.html')


@bp.route('/set-password/<token>', methods=['GET', 'POST'])
def set_password(token):
    user = User.query.filter_by(invite_token=token).first()
    if not user or not user.invited_at:
        flash('Invite link is invalid.', 'danger')
        return redirect(url_for('auth.login'))

    if datetime.utcnow() > user.invited_at + timedelta(hours=72):
        flash('Invite link has expired. Ask admin to resend invite.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/set_password.html', user=user)
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/set_password.html', user=user)

        user.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        user.must_set_password = False
        user.invite_token = None
        user.invited_at = None
        user.last_login_at = datetime.utcnow()
        db.session.commit()
        login_user(user)
        flash('Password set successfully.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('auth/set_password.html', user=user)
