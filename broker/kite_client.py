"""
Shared KiteConnect singleton.
Initialised once at startup; shared across broker modules.
Import of kiteconnect is deferred so unit tests can run without it installed.
"""

from __future__ import annotations

from config import settings

_kite = None  # KiteConnect instance (type erased to avoid import at module load)


def get_kite():
    """Return an authenticated KiteConnect instance."""
    global _kite
    if _kite is None:
        from broker.authentication import get_kite as authenticate_kite
        _kite = authenticate_kite()
    return _kite


def set_kite(kite) -> None:
    """Inject a pre-configured instance (useful for testing)."""
    global _kite
    _kite = kite
