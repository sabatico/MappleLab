import os
import logging

logger = logging.getLogger(__name__)

def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    """Base configuration. All values can be overridden by env vars."""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///orchard_ui.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Local Docker/OCI registry (LAN-only, no TLS needed)
    REGISTRY_URL = os.environ.get('REGISTRY_URL', 'localhost:5001')

    # Shared secret for TART agent authentication
    AGENT_TOKEN = os.environ.get('AGENT_TOKEN', '')

    # Mail defaults. Runtime SMTP settings are loaded from DB AppSettings.
    MAIL_SERVER = os.environ.get('MAIL_SERVER', '')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = _env_bool('MAIL_USE_TLS', True)
    MAIL_USE_SSL = _env_bool('MAIL_USE_SSL', False)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')

    # SSH tunnel port range (each active VNC console uses one local port)
    # Reuses the same env vars for backwards compatibility
    WEBSOCKIFY_PORT_MIN = int(os.environ.get('WEBSOCKIFY_PORT_MIN', 6900))
    WEBSOCKIFY_PORT_MAX = int(os.environ.get('WEBSOCKIFY_PORT_MAX', 6999))

    # VNC defaults (TART / Cirrus Labs base image default credentials)
    VNC_PORT = 5900
    VNC_DEFAULT_USERNAME = os.environ.get('VNC_DEFAULT_USERNAME', 'admin')
    VNC_DEFAULT_PASSWORD = os.environ.get('VNC_DEFAULT_PASSWORD', 'admin')
    VNC_USE_SSH_TUNNEL = _env_bool('VNC_USE_SSH_TUNNEL', False)
    # Optional browser-direct mode: no Flask WS relay (browser connects to node websockify).
    VNC_BROWSER_DIRECT_NODE_WS = _env_bool('VNC_BROWSER_DIRECT_NODE_WS', False)
    # Leave empty for auto (wss if page is https, otherwise ws).
    VNC_BROWSER_DIRECT_NODE_WS_SCHEME = os.environ.get('VNC_BROWSER_DIRECT_NODE_WS_SCHEME', '')

    # TLS / HTTPS (self-signed cert for dev; leave blank to use plain HTTP)
    SSL_CERT = os.environ.get('SSL_CERT', '')   # path to certificate file (PEM)
    SSL_KEY  = os.environ.get('SSL_KEY',  '')   # path to private key file (PEM)
    TRUST_PROXY = _env_bool('TRUST_PROXY', False)  # set true behind nginx/caddy
    FORCE_HTTPS = _env_bool('FORCE_HTTPS', False)
    PREFERRED_URL_SCHEME = 'https' if FORCE_HTTPS else 'http'
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', FORCE_HTTPS)
    SESSION_COOKIE_HTTPONLY = _env_bool('SESSION_COOKIE_HTTPONLY', True)
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')

    # UI behavior
    VM_POLL_INTERVAL_MS = int(os.environ.get('VM_POLL_INTERVAL_MS', 5000))

    # Known TART images for the "Create VM" dropdown
    TART_IMAGES = os.environ.get('TART_IMAGES', ','.join([
        'ghcr.io/cirruslabs/macos-sonoma-base:latest',
        'ghcr.io/cirruslabs/macos-tahoe-base:latest',
    ])).split(',')


class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = logging.DEBUG


class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = logging.INFO
    # In production, SECRET_KEY MUST be set via env var
