import logging
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
        user = User.query.filter_by(username=request.form['username']).first()
        if user and bcrypt.check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            logger.info("User %r logged in", user.username)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    logger.info("User %r logged out", current_user.username)
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        if not username:
            flash('Username is required.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
        else:
            pw_hash = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
            user = User(username=username, password_hash=pw_hash)
            db.session.add(user)
            db.session.commit()
            logger.info("New user registered: %r", username)
            flash('Account created. Please log in.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('auth/register.html')
