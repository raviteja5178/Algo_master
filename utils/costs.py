"""
Zerodha/BSE index-option transaction costs, shared by the backtests and the
expiry-fly SHADOW runner so both charge identically.

    brokerage   Rs 20 per order (a buy and a sell = Rs 40)
    STT         0.1% of sell premium (0.0625% before 2024-10-01)
    exchange    0.0325% of premium turnover (BSE options)
    SEBI        Rs 10 per crore of turnover
    stamp duty  0.003% of buy premium
    GST         18% on brokerage + exchange + SEBI
"""

from __future__ import annotations

from datetime import date


def charges(buy_px: float, sell_px: float, qty: int, day: date) -> float:
    """Total charges (Rs) for buying at *buy_px* and selling at *sell_px*, *qty* units."""
    buy, sell = buy_px * qty, sell_px * qty
    turnover = buy + sell
    brokerage = 40.0
    stt = sell * (0.001 if day >= date(2024, 10, 1) else 0.000625)
    exch = turnover * 0.000325
    sebi = turnover * 10 / 1e7
    stamp = buy * 0.00003
    gst = 0.18 * (brokerage + exch + sebi)
    return round(brokerage + stt + exch + sebi + stamp + gst, 2)
