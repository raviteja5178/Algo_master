"""
Structured logging configuration using Python's standard logging library.
Every log record includes: timestamp, level, module, and structured fields.
API secrets must never appear in log output.
"""

import logging
import sys
from typing import Any

from config import settings


class _SanitiserFilter(logging.Filter):
    """Strip any accidental secret leakage from log records.

    Only redacts when a message looks like it contains an actual credential
    value (key=value or key: value pattern with a long alphanumeric string),
    not merely when it mentions the word 'token' or 'secret' in context.
    This prevents legitimate Kite exception messages from being silently swallowed.
    """

    import re as _re
    # Match patterns like: access_token=abc123xyz, api_key: abc123, "api_secret": "xyz"
    _CRED_RE = _re.compile(
        r'(api_key|api_secret|access_token|password)\s*[=:]\s*["\']?[A-Za-z0-9+/=_\-]{8,}',
        _re.IGNORECASE,
    )

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        msg = record.getMessage()
        if self._CRED_RE.search(msg):
            record.msg = "[REDACTED — credential value in log message]"
            record.args = ()
        return True


def configure_logging() -> None:
    """Configure logging for the bot subprocess.

    IMPORTANT: no StreamHandler(sys.stdout) is added here.
    When the bot is launched as a subprocess by the UI (ui/app.py), its stdout
    is a pipe.  If the UI's reader thread ever falls behind, the pipe buffer
    fills and any write to stdout BLOCKS — freezing PaperFeed, the tick
    callbacks, and the state-file writer.  File-only logging avoids this.
    """
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if configure_logging() is called more than once.
    if root.handlers:
        return

    # File handler — always present; never blocks the trading loop.
    try:
        fh = logging.FileHandler("bot.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
        fh.addFilter(_SanitiserFilter())
        fh.setLevel(level)
        root.addHandler(fh)
    except OSError:
        # Last-resort fallback: stderr is unbuffered and not owned by the UI pipe.
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
        sh.addFilter(_SanitiserFilter())
        root.addHandler(sh)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """
    Emit a structured log line.

    Example:
        log_event(logger, "ENTRY_FILLED", symbol="SENSEX26JAN220CE", fill=220, qty=20)
    """
    body = " | ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("[%s] %s", event, body)
