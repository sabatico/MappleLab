"""
Logging configuration for Orchard UI.

Call configure_logging() once at startup (in run.py) before importing
any application modules.

Levels
------
INFO  (default) — app lifecycle events, connections established, errors
DEBUG           — every function entry/exit, request params, response data

Handlers
--------
- RotatingFileHandler : logs/orchard_ui.log, 5 MB max, 3 backups kept
- StreamHandler       : stderr (console), same level as root logger

Format
------
INFO  : 2026-02-21 12:00:00,000 [INFO ] app.module        : message
DEBUG : 2026-02-21 12:00:00,000 [DEBUG] app.module:fn:42  : message
"""

import logging
import logging.handlers
import os


# ── formats ──────────────────────────────────────────────────────────────────

_FMT_INFO = (
    "%(asctime)s [%(levelname)-5s] %(name)-30s: %(message)s"
)

_FMT_DEBUG = (
    "%(asctime)s [%(levelname)-5s] %(name)-30s %(funcName)s:%(lineno)d: %(message)s"
)

_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# Max log file size and number of rotating backups
_MAX_BYTES   = 5 * 1024 * 1024   # 5 MB
_BACKUP_COUNT = 3
_LOG_DIR  = "logs"
_LOG_FILE = os.path.join(_LOG_DIR, "orchard_ui.log")

# Third-party libraries that are too noisy at DEBUG — keep them at WARNING
_QUIET_LOGGERS = [
    "werkzeug",
    "urllib3",
    "requests",
    "charset_normalizer",
]


def configure_logging(level: int = logging.INFO) -> None:
    """
    Set up root logger with rotating file + stderr handlers.

    Args:
        level: logging level (logging.INFO or logging.DEBUG).
               Reads LOG_LEVEL env var if not overridden by caller.
    """
    # Allow env-var override: LOG_LEVEL=DEBUG python run.py
    env_level = os.environ.get("LOG_LEVEL", "").upper()
    if env_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = getattr(logging, env_level)

    fmt = _FMT_DEBUG if level == logging.DEBUG else _FMT_INFO
    formatter = logging.Formatter(fmt, datefmt=_DATE_FMT)

    # ── rotating file handler ─────────────────────────────────────────────
    os.makedirs(_LOG_DIR, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # ── stderr / console handler ──────────────────────────────────────────
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)

    # ── root logger ───────────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(level)
    # Avoid adding duplicate handlers if called twice (e.g. Flask reloader)
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(stream_handler)

    # ── quiet noisy third-party loggers ───────────────────────────────────
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised — level=%s, file=%s",
        logging.getLevelName(level),
        os.path.abspath(_LOG_FILE),
    )
