import logging
from flask import current_app, url_for, render_template
from flask_mail import Message
from app.extensions import mail
from app.models import AppSettings

logger = logging.getLogger(__name__)


def _smtp_settings():
    settings = AppSettings.query.get(1)
    if not settings or not settings.smtp_host:
        return None
    return settings


def _apply_mail_config(settings):
    current_app.config['MAIL_SERVER'] = settings.smtp_host or ''
    current_app.config['MAIL_PORT'] = settings.smtp_port or 587
    current_app.config['MAIL_USE_TLS'] = bool(settings.smtp_use_tls)
    current_app.config['MAIL_USE_SSL'] = False
    current_app.config['MAIL_USERNAME'] = settings.smtp_user or ''
    current_app.config['MAIL_PASSWORD'] = settings.smtp_password or ''
    current_app.config['MAIL_DEFAULT_SENDER'] = settings.smtp_from or settings.smtp_user or ''


def send_invite_email(user):
    settings = _smtp_settings()
    if not settings:
        logger.warning("SMTP not configured; skipped invite email for %s", user.email or user.username)
        return False

    _apply_mail_config(settings)

    invite_link = url_for('auth.set_password', token=user.invite_token, _external=True)
    subject = "You're invited to Orchard UI"
    body = (
        "You have been invited to Orchard UI.\n\n"
        f"Open this link to set your password:\n{invite_link}\n\n"
        "This invite link expires in 72 hours."
    )
    html = render_template('email/invite.html', invite_link=invite_link)
    msg = Message(subject=subject, recipients=[user.email], body=body, html=html)
    try:
        mail.send(msg)
        logger.info("Invite email sent to %s", user.email)
        return True
    except Exception as e:
        logger.warning("Failed to send invite email to %s: %s", user.email, e)
        return False


def send_test_email(to_email):
    settings = _smtp_settings()
    if not settings:
        logger.warning("SMTP not configured; skipped test email to %s", to_email)
        return False

    _apply_mail_config(settings)
    msg = Message(
        subject='Orchard UI SMTP test',
        recipients=[to_email],
        body='SMTP configuration test email from Orchard UI.',
        html='<p>SMTP configuration test email from <strong>Orchard UI</strong>.</p>',
    )
    try:
        mail.send(msg)
        logger.info("SMTP test email sent to %s", to_email)
        return True
    except Exception as e:
        logger.warning("Failed to send SMTP test email to %s: %s", to_email, e)
        return False
