import atexit
import logging
from flask import Flask

logger = logging.getLogger(__name__)


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

    # --- Initialize extensions (db, login_manager, bcrypt) ---
    from app.extensions import init_extensions
    init_extensions(app)
    logger.debug("Extensions initialised")

    # --- Create DB tables (no-op if already exist) ---
    from app.extensions import db
    with app.app_context():
        from app.models import User, VM, Node  # noqa: F401
        db.create_all()
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
