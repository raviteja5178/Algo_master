"""Exchange segment resolution for index option tradingsymbols."""

from __future__ import annotations

# Longest names first: BANKNIFTY / FINNIFTY / MIDCPNIFTY all contain "NIFTY".
_OPTION_EXCHANGE = (
    ("BANKNIFTY", "NFO"),
    ("FINNIFTY", "NFO"),
    ("MIDCPNIFTY", "NFO"),
    ("NIFTY", "NFO"),
    ("SENSEX", "BFO"),
    ("BANKEX", "BFO"),
)


def option_exchange(tradingsymbol: str | None, default: str = "BFO") -> str:
    """Exchange for an option tradingsymbol (SENSEX* -> BFO, NIFTY family -> NFO)."""
    s = (tradingsymbol or "").split(":")[-1].upper()
    for prefix, exchange in _OPTION_EXCHANGE:
        if s.startswith(prefix):
            return exchange
    return default


def option_quote_key(tradingsymbol: str) -> str:
    """`EXCHANGE:SYMBOL` key for kite.quote()/ltp()."""
    return f"{option_exchange(tradingsymbol)}:{tradingsymbol}"
