"""
PAPER mode prices the option as the SENSEX index (delta 1).  A PE gains when
the index falls, so its stand-in price must move opposite to the index —
otherwise its stop sits on the wrong side and P&L has the wrong sign.

Also covers two places that used the SENSEX level as an option price in every
mode: the SHADOW exit-quote fallback and the candle-close smart/AI exits.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from execution.position_manager import State, StateMachine
from utils.time_utils import IST


def _sm(state: State) -> StateMachine:
    sm = StateMachine()
    sm._state = state  # noqa: SLF001
    return sm


def _ctx(strategy: str, state: State = State.POSITION_OPEN, entry: float = 75000.0, **kw):
    from strategies.smart_entry import SmartEntryFilter
    base = dict(
        sm=_sm(state), strategy_type=strategy, entry_price=entry, sensex_ltp=entry,
        broker=MagicMock(), trade_id="T1", tradingsymbol="SENSEX_TEST", instrument_token=7,
        quantity=20, stop_order_id=None, trailing=MagicMock(highest_ltp=entry),
        target=None, pivot_mgr=None, smart_exit=None, last_option_ltp=0.0,
        smart_entry=SmartEntryFilter(),
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ── the price model ───────────────────────────────────────────────────────────

class TestPaperOptionPrice:
    def test_ce_is_the_index(self) -> None:
        from main import _paper_option_price
        assert _paper_option_price(_ctx("CE_PIVOT"), 75100.0) == 75100.0

    @pytest.mark.parametrize("index, expected", [(75100.0, 74900.0), (74900.0, 75100.0),
                                                 (75000.0, 75000.0)])
    def test_pe_mirrors_around_entry(self, index, expected) -> None:
        from main import _paper_option_price
        assert _paper_option_price(_ctx("PE_PIVOT"), index) == expected

    def test_pe_mirrored_during_exit_too(self) -> None:
        from main import _paper_option_price
        ctx = _ctx("PE", state=State.EXIT_PENDING)
        assert _paper_option_price(ctx, 74950.0) == 75050.0

    def test_no_mirror_without_an_open_pe(self) -> None:
        from main import _paper_option_price
        # flat: a stale PE strategy_type / entry price from the last trade must not leak
        assert _paper_option_price(_ctx("PE", state=State.IDLE), 75100.0) == 75100.0
        assert _paper_option_price(_ctx("PE", entry=0.0), 75100.0) == 75100.0


# ── tick handler feeds the mirrored price ─────────────────────────────────────

def test_paper_tick_handler_feeds_pe_option_price(monkeypatch) -> None:
    import main
    from config import settings
    monkeypatch.setattr(settings, "TRADING_MODE", "PAPER")
    monkeypatch.setattr(main, "now_ist", lambda: IST.localize(datetime(2026, 10, 20, 10, 0)))
    monkeypatch.setattr(main, "_write_state", lambda ctx: None)
    monkeypatch.setattr(main, "_write_ltp", lambda ctx: None)
    seen = []
    monkeypatch.setattr(main, "on_option_ltp", lambda ctx, ltp: seen.append(ltp))
    ctx = _ctx("PE_PIVOT", agg_5m=MagicMock(), agg_15m=MagicMock(), vwap=MagicMock())
    handler = main._make_tick_handler(ctx)
    handler(main.SENSEX_TOKEN, 75120.0)          # index up 120 → PE option down 120
    assert seen == [74880.0]


# ── execute_exit: PAPER and SHADOW price hints ────────────────────────────────

def _run_exit(monkeypatch, mode: str, ctx, quote=None):
    import main
    from config import settings
    monkeypatch.setattr(settings, "TRADING_MODE", mode)
    for name in ("mark_trade_closed_with_reason", "notify", "note_ema_result", "_live_event"):
        monkeypatch.setattr(main, name, MagicMock())
    if quote is not None:
        import broker.kite_client as kc
        monkeypatch.setattr(kc, "get_kite", lambda: quote)
    ctx.broker.cancel_order.return_value = True
    ctx.broker.place_sell_order.side_effect = lambda sym, qty, tag="", ltp_hint=None: {
        "order_id": "S1", "status": "COMPLETE", "filled_qty": qty, "average_price": ltp_hint}
    main.execute_exit(ctx, reason="PIVOT_TSL_HIT")
    return ctx.broker.place_sell_order.call_args.kwargs["ltp_hint"]


def test_paper_pe_exit_books_a_profit_when_index_fell(monkeypatch) -> None:
    import main
    ctx = _ctx("PE_PIVOT", sensex_ltp=74800.0)     # index fell 200 from entry
    hint = _run_exit(monkeypatch, "PAPER", ctx)
    assert hint == 75200.0                          # option +200
    pnl = main.mark_trade_closed_with_reason.call_args.args[3]
    assert pnl == pytest.approx(200 * 20)


def test_paper_ce_exit_unchanged(monkeypatch) -> None:
    ctx = _ctx("CE_PIVOT", sensex_ltp=74800.0)
    assert _run_exit(monkeypatch, "PAPER", ctx) == 74800.0


def test_shadow_exit_quote_failure_never_uses_the_index(monkeypatch) -> None:
    kite = MagicMock()
    kite.quote.side_effect = RuntimeError("quote down")
    ctx = _ctx("CE_ORB", entry=250.0, sensex_ltp=74800.0, last_option_ltp=262.5)
    assert _run_exit(monkeypatch, "SHADOW", ctx, quote=kite) == 262.5
