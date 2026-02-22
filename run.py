import os
import ssl
import logging
from dotenv import load_dotenv
load_dotenv()  # must run before config classes are imported (they read os.environ at class-definition time)

from app.logging_config import configure_logging
configure_logging()  # must run before any other app imports so all loggers inherit root config

from app import create_app
from config import DevelopmentConfig, ProductionConfig

logger = logging.getLogger(__name__)

env = os.environ.get('FLASK_ENV', 'development')
config = ProductionConfig if env == 'production' else DevelopmentConfig
logger.info("Starting Orchard UI (env=%s, config=%s)", env, config.__name__)

app = create_app(config)

if __name__ == '__main__':
    ssl_context = None
    cert = app.config.get('SSL_CERT', '')
    key  = app.config.get('SSL_KEY', '')
    port = int(os.environ.get('PORT', 5000))

    if cert and key:
        logger.info("TLS enabled — cert=%s, key=%s", cert, key)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(cert, key)
        scheme = "https"
    else:
        logger.warning("TLS disabled — running plain HTTP (set SSL_CERT and SSL_KEY to enable HTTPS)")
        scheme = "http"

    logger.info("Serving on %s://0.0.0.0:%d", scheme, port)
    app.run(
        host='0.0.0.0',
        port=port,
        ssl_context=ssl_context,
    )
