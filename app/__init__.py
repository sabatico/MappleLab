import atexit
import logging
from flask import Flask, request, redirect
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def _ensure_sqlite_columns(app):
    """Lightweight schema compatibility for existing SQLite installs."""
    from app.extensions import db

    if not app.config.get('SQLALCHEMY_DATABASE_URI', '').startswith('sqlite'):
        return

    inspector = inspect(db.engine)
    users_cols = {col['name'] for col in inspector.get_columns('users')}
    vms_cols = {col['name'] for col in inspector.get_columns('vms')}
    app_settings_cols = {col['name'] for col in inspector.get_columns('app_settings')}

    user_additions = [
        ('email', 'VARCHAR(255)'),
        ('max_active_vms', 'INTEGER DEFAULT 1'),
        ('max_saved_vms', 'INTEGER DEFAULT 2'),
        ('disk_quota_gb', 'INTEGER DEFAULT 100'),
        ('must_set_password', 'BOOLEAN DEFAULT 0'),
        ('invite_token', 'VARCHAR(128)'),
        ('invited_at', 'DATETIME'),
        ('last_login_at', 'DATETIME'),
    ]
    vm_additions = [
        ('disk_size_gb', 'FLOAT'),
        ('cleanup_status', 'VARCHAR(32)'),
        ('cleanup_last_error', 'VARCHAR(256)'),
        ('cleanup_last_run_at', 'DATETIME'),
        ('cleanup_target_digest', 'VARCHAR(128)'),
    ]
    app_settings_additions = [('smtp_use_ssl', 'BOOLEAN DEFAULT 0')]

    with db.engine.begin() as conn:
        for name, ddl in user_additions:
            if name not in users_cols:
                conn.execute(text(f'ALTER TABLE users ADD COLUMN {name} {ddl}'))
                logger.info("SQLite compatibility: added users.%s", name)
        for name, ddl in vm_additions:
            if name not in vms_cols:
                conn.execute(text(f'ALTER TABLE vms ADD COLUMN {name} {ddl}'))
                logger.info("SQLite compatibility: added vms.%s", name)
        for name, ddl in app_settings_additions:
            if name not in app_settings_cols:
                conn.execute(text(f'ALTER TABLE app_settings ADD COLUMN {name} {ddl}'))
                logger.info("SQLite compatibility: added app_settings.%s", name)


def create_app(config_class=None):
    """
    Application factory.
    Creates and configures the Flask app, initializes extensions + services,
    registers blueprints, and sets up shutdown hooks.
    """
    if config_class is None:
        from config import DevelopmentConfig
        config_class = DevelopmentConfig

    logger.debug("create_app() called with config_class=%s", config_class.__name__)

    app = Flask(__name__)
    app.config.from_object(config_class)
    logger.info("Flask app created — config loaded from %s", config_class.__name__)

    if app.config.get('TRUST_PROXY'):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
        logger.info("ProxyFix enabled (trusting X-Forwarded-Proto/Host)")

    # --- Initialize extensions (db, login_manager, bcrypt) ---
    from app.extensions import init_extensions
    init_extensions(app)
    logger.debug("Extensions initialised")

    # --- Create DB tables (no-op if already exist) ---
    from app.extensions import db
    with app.app_context():
        from app.models import User, VM, Node, AppSettings  # noqa: F401
        db.create_all()
        _ensure_sqlite_columns(app)
    logger.debug("Database tables ensured")

    # --- Initialize services ---
    from app.tart_client import TartClient
    from app.node_manager import NodeManager
    from app.tunnel_manager import TunnelManager

    app.tart = TartClient(app)
    logger.info("TartClient initialised")

    app.node_manager = NodeManager(app)
    logger.info("NodeManager initialised")

    app.tunnel_manager = TunnelManager(app)
    logger.info(
        "TunnelManager initialised — port range %s-%s",
        app.config.get('WEBSOCKIFY_PORT_MIN'),
        app.config.get('WEBSOCKIFY_PORT_MAX'),
    )

    # --- Register blueprints ---
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    logger.debug("Blueprint registered: main (prefix=/)")

    from app.console import bp as console_bp
    app.register_blueprint(console_bp, url_prefix='/console')
    logger.debug("Blueprint registered: console (prefix=/console)")

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    logger.debug("Blueprint registered: api (prefix=/api)")

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    logger.debug("Blueprint registered: auth (prefix=/auth)")

    from app.nodes import bp as nodes_bp
    app.register_blueprint(nodes_bp, url_prefix='/nodes')
    logger.debug("Blueprint registered: nodes (prefix=/nodes)")

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    logger.debug("Blueprint registered: admin (prefix=/admin)")

    # --- Shutdown hook: close all SSH tunnels ---
    atexit.register(app.tunnel_manager.cleanup_all)
    logger.debug("Registered atexit cleanup hook for TunnelManager")

    # --- Template context processors ---
    @app.context_processor
    def inject_config():
        """Make certain config values available in all templates."""
        from flask_login import current_user
        return {
            'poll_interval_ms': app.config['VM_POLL_INTERVAL_MS'],
            'current_user': current_user,
        }

    @app.before_request
    def enforce_https():
        """Redirect HTTP requests to HTTPS when FORCE_HTTPS is enabled."""
        if not app.config.get('FORCE_HTTPS'):
            return None
        if request.is_secure:
            return None
        if request.host.startswith('localhost') or request.host.startswith('127.0.0.1'):
            return None
        return redirect(request.url.replace('http://', 'https://', 1), code=301)

    # --- Error handlers ---
    @app.errorhandler(404)
    def not_found(error):
        from flask import render_template, request
        logger.warning("404 Not Found: %s %s", request.method, request.path)
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template, request
        logger.error(
            "500 Internal Server Error: %s %s — %s",
            request.method, request.path, error,
            exc_info=True,
        )
        return render_template('errors/500.html'), 500

    logger.info("Application factory complete — app ready")
    return app
