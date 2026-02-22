import os
import logging

logger = logging.getLogger(__name__)


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

    # SSH tunnel port range (each active VNC console uses one local port)
    # Reuses the same env vars for backwards compatibility
    WEBSOCKIFY_PORT_MIN = int(os.environ.get('WEBSOCKIFY_PORT_MIN', 6900))
    WEBSOCKIFY_PORT_MAX = int(os.environ.get('WEBSOCKIFY_PORT_MAX', 6999))

    # VNC defaults (TART default credentials)
    VNC_PORT = 5900
    VNC_DEFAULT_PASSWORD = os.environ.get('VNC_DEFAULT_PASSWORD', 'admin')

    # TLS / HTTPS (self-signed cert for dev; leave blank to use plain HTTP)
    SSL_CERT = os.environ.get('SSL_CERT', '')   # path to certificate file (PEM)
    SSL_KEY  = os.environ.get('SSL_KEY',  '')   # path to private key file (PEM)

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
