"""
Smart Entry Filter — quality gate applied AFTER a raw signal fires.

Prevents entering on weak or poorly-timed setups even when the core
strategy conditions (EMA crossover / ORB breakout) are satisfied.

Seven independent filters (all opt-in, all default OFF):

  Filter 1 — Candle body / ATR ratio  (SMART_ENTRY_MIN_BODY_ATR_RATIO > 0)
  ───────────────────────────────────────────────────────────────────────────
  The signal candle's body must be >= SMART_ENTRY_MIN_BODY_ATR_RATIO × ATR(14).
  body = abs(close - open)
  Rejects doji / wick-spike candles that barely satisfy the crossover but
  carry no real momentum.  When ATR is unavailable the filter is skipped
  (fail-open) so it never prevents a valid trade on cold data.

  When SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES is set (default "VWAP,NATR"),
  Filter 1 is skipped entirely for those strategy types.  Rationale: on VWAP
  bounce entries the signal candle is often a narrow reclaim candle — the
  momentum is already confirmed by the VWAP retest structure, not by body size.

  Filter 2 — EMA9 slope  (SMART_ENTRY_REQUIRE_EMA_SLOPE = true)
  ───────────────────────────────────────────────────────────────────────────
  CE: EMA9[0] > EMA9[-1]  (EMA9 is rising on this candle)
  PE: EMA9[0] < EMA9[-1]  (EMA9 is falling on this candle)
  Prevents entering when the short EMA is flat or decelerating — a strong
  warning that the move has already stalled.  Needs at least 2 EMA9 values,
  so it is automatically skipped if fewer than 10 candles are available.

  Filter 3 — Post-loss cooldown  (SMART_ENTRY_COOLDOWN_CANDLES > 0)
  ───────────────────────────────────────────────────────────────────────────
  After an SL exit (realised loss on the last closed trade), block new entries
  for SMART_ENTRY_COOLDOWN_CANDLES completed 5m candles.
  Prevents immediately re-entering a choppy, reversing market.
  The cooldown counter is reset when a trade closes at breakeven or profit.

  Filter 4 — Minimum EMA gap  (SMART_ENTRY_MIN_EMA_GAP_PTS > 0)
  ───────────────────────────────────────────────────────────────────────────
  The absolute gap between EMA9 and EMA21 must be >= this many points.
  CE: EMA9[0] - EMA21[0] >= min_ema_gap_pts
  PE: EMA21[0] - EMA9[0] >= min_ema_gap_pts
  Rejects signals where the two EMAs are nearly equal — a compressed, flat
  structure that produces false crossovers in both directions (noise zone).
  Today's data showed the 14:25 CE signal fired with an EMA gap of +0.57 pts —
  that is not a trend, it is oscillation.  Recommended: 10–15 pts on SENSEX 5m.
  Skipped when EMA values are unavailable (fail-open).

  When SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES is set (default "VWAP,NATR"),
  Filters 4 & 5 (EMA gap magnitude + widening) are also skipped for those
  strategy types.  Rationale: VWAP/NATR bounce signals occur exactly at the
  moment EMAs are flat/compressed — the signal's own retest structure provides
  the confirmation that makes the EMA gap check redundant and harmful.
  Example: 2026-10-05 13:20 CE_VWAP — EMA gap was −4.63 (flat/noise), VWAP was
  the actual structural level; price moved +237 pts after the block.

  Filter 5 — EMA gap widening  (SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING = true)
  ───────────────────────────────────────────────────────────────────────────
  The EMA gap must be larger (in the signal direction) than it was on the
  previous candle:
  CE: (EMA9[0] - EMA21[0]) > (EMA9[-1] - EMA21[-1])   ← gap growing
  PE: (EMA21[0] - EMA9[0]) > (EMA21[-1] - EMA9[-1])   ← gap growing
  Prevents entering a decelerating trend where the gap is shrinking even if
  it is still positive.  Today: the gap shrank from +29.6 → +24.5 → +24.5 →
  +20.9 over 4 candles before the 13:00 CE entry — a clear deceleration signal.
  Needs at least 2 completed candles with valid EMA21; skipped otherwise.

  Filter 6 — 15-minute trend alignment  (SMART_ENTRY_REQUIRE_15M_TREND = true)
  ───────────────────────────────────────────────────────────────────────────
  CE: the latest completed 15m candle must close ABOVE its 15m EMA21.
  PE: the latest completed 15m candle must close BELOW its 15m EMA21.
  Higher-timeframe structure filter — prevents buying in a 15m downtrend or
  selling in a 15m uptrend.  Needs >= 21 completed 15m candles (≈ 5h of data);
  skipped (fail-open) when candles_15m is empty or too short.
  Pass candles_15m via the allow() call; when omitted the filter is skipped.

  Filter 7 — Option premium extension  (SMART_ENTRY_MAX_PREMIUM_EXTENSION_PCT > 0)
  ───────────────────────────────────────────────────────────────────────────────────
  Blocks entry when the current option LTP has already risen more than
  MAX_PREMIUM_EXTENSION_PCT above the first-seen LTP of the same option
  on today's session.

  Problem it solves: the EMA signal fires at ₹331 on an option that opened
  at ₹140 — the entire move has already happened; the bot is entering at the
  peak.  Setting max_premium_extension_pct=1.5 (150%) would reject any entry
  where current_ltp > first_seen_ltp × 1.5, i.e. a 50% rally is the ceiling.

  How the first-seen LTP is tracked:
    Call notify_option_ltp(symbol, ltp) whenever the option LTP is first
    observed (before or at signal time).  The filter stores the first value
    seen per symbol per day and resets the registry at midnight automatically.

  Behaviour when first-seen LTP is unknown (no prior call):
    Fail-open — the filter is skipped so it never blocks a trade on
    incomplete data.

  Recommended value: 1.5 (block when option has already doubled + 50%).
  Set to 0 to disable (default).

All filters are applied in signal_engine.evaluate_signals() after the raw
signal check passes.  A blocked signal is logged at DEBUG level.

Usage
─────
    from strategies.smart_entry import SmartEntryFilter
    flt = SmartEntryFilter(
        min_body_atr_ratio          = settings.SMART_ENTRY_MIN_BODY_ATR_RATIO,
        require_ema_slope           = settings.SMART_ENTRY_REQUIRE_EMA_SLOPE,
        cooldown_candles            = settings.SMART_ENTRY_COOLDOWN_CANDLES,
        min_ema_gap_pts             = settings.SMART_ENTRY_MIN_EMA_GAP_PTS,
        require_ema_gap_widening    = settings.SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING,
        require_15m_trend           = settings.SMART_ENTRY_REQUIRE_15M_TREND,
        max_premium_extension_pct   = settings.SMART_ENTRY_MAX_PREMIUM_EXTENSION_PCT,
    )

    # whenever the option LTP is first observed (once per option per day):
    flt.notify_option_ltp(tradingsymbol, current_ltp)

    # on every trade close:
    flt.on_trade_closed(realised_pnl_pts)   # negative = loss

    # on every candle close (even when no position):
    flt.on_candle()

    # inside signal evaluation, after the raw signal passes:
    if not flt.allow(direction, candles_5m, candles_15m=ctx.candles_15m,
                     option_ltp=current_ltp, tradingsymbol=ctx.tradingsymbol):
        return None   # blocked
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle
from market.indicators import atr_at, ema
from utils.logging_config import log_event

logger = logging.getLogger(__name__)


class SmartEntryFilter:
    """
    Stateful quality gate for entry signals.

    Parameters
    ----------
    min_body_atr_ratio         : float  — body >= ATR*ratio. 0 = disabled.
    require_ema_slope          : bool   — EMA9 must be rising/falling.
    cooldown_candles           : int    — candles blocked after a loss. 0 = disabled.
    min_ema_gap_pts            : float  — |EMA9-EMA21| must be >= this. 0 = disabled.
    require_ema_gap_widening   : bool   — EMA gap must be growing. False = disabled.
    require_15m_trend          : bool   — 15m close must align with EMA21. False = disabled.
    max_15m_gap_pts            : float  — only block 15m trend when gap exceeds this.
                                          0 = binary block (original behaviour).
                                          >0 = allow entry when gap < this many pts.
                                          Recommended: 150 for SENSEX.
    squeeze_bypass             : bool   — skip 15m/slope filters on consecutive
                                          same-direction 5m candles (squeeze move).
    squeeze_candles            : int    — consecutive candles needed for bypass. 0 = off.
    max_premium_extension_pct  : float  — block entry when current option LTP >
                                          first_seen_ltp × (1 + this value).
                                          0 = disabled.  1.5 = block after 150% rise.
                                          Recommended: 1.5 for SENSEX weekly options.
    bounce_exempt_strategies   : set[str] — strategy suffixes that bypass Filters 1,
                                          4 & 5 (body/ATR, EMA gap magnitude, EMA gap
                                          widening).  Default {"VWAP", "NATR"}.
                                          Rationale: bounce setups (VWAP retest, NATR
                                          crossover) confirm momentum via their own
                                          structural level — a flat EMA gap is expected
                                          and the body filter is irrelevant.
                                          Set to empty set to disable.
    """

    def __init__(
        self,
        min_body_atr_ratio: float = 0.0,
        require_ema_slope: bool = False,
        cooldown_candles: int = 0,
        min_ema_gap_pts: float = 0.0,
        require_ema_gap_widening: bool = False,
        require_15m_trend: bool = False,
        max_15m_gap_pts: float = 0.0,
        squeeze_bypass: bool = False,
        squeeze_candles: int = 3,
        max_premium_extension_pct: float = 0.0,
        squeeze_body_atr_ratio: float = 0.0,
        structure_bypass_candles: int = 0,
        structure_bypass_ema_confirm: bool = True,
        bounce_exempt_strategies: set[str] | None = None,
    ) -> None:
        self._min_body_atr       = min_body_atr_ratio
        self._require_slope      = require_ema_slope
        self._cooldown_max       = max(0, cooldown_candles)
        self._cooldown_left: int = 0
        self._min_ema_gap        = min_ema_gap_pts
        self._require_gap_wide   = require_ema_gap_widening
        self._require_15m_trend  = require_15m_trend
        self._max_15m_gap        = max_15m_gap_pts   # 0 = original binary block
        self._squeeze_bypass     = squeeze_bypass
        self._squeeze_n          = max(0, squeeze_candles)
        self._squeeze_body_atr   = squeeze_body_atr_ratio  # 0 = same as normal ratio
        self._max_ext_pct        = max_premium_extension_pct  # 0 = disabled
        self._structure_bypass_n = max(0, structure_bypass_candles)
        self._structure_bypass_ema = structure_bypass_ema_confirm
        # Strategies that bypass body/ATR and EMA-gap filters (bounce setups)
        if bounce_exempt_strategies is None:
            self._bounce_exempt: frozenset[str] = frozenset({"VWAP", "NATR"})
        else:
            self._bounce_exempt = frozenset(s.upper() for s in bounce_exempt_strategies)
        # {tradingsymbol: (date, first_ltp)} — resets automatically per day
        self._first_ltp: dict[str, tuple[date, float]] = {}
        # {tradingsymbol: (date, highest_ltp)} — rolling intraday high per symbol
        self._highest_ltp: dict[str, tuple[date, float]] = {}

    # ── Lifecycle callbacks ────────────────────────────────────────────────────

    def notify_option_ltp(self, tradingsymbol: str, ltp: float) -> None:
        """
        Record the first-seen (day low proxy) and rolling highest LTP for an
        option symbol on today's session.

        First-seen is immutable once recorded for today.  Highest is updated
        on every call so it tracks the intraday peak premium.

        Call this whenever you learn the option's current price (e.g. at
        signal time, before calling allow()).  Stale entries from previous
        days are discarded automatically so no manual reset is needed.
        """
        if ltp <= 0:
            return
        today = date.today()

        # ── First-seen (day low proxy) ─────────────────────────────────────
        existing = self._first_ltp.get(tradingsymbol)
        if existing is None or existing[0] != today:
            self._first_ltp[tradingsymbol] = (today, ltp)
            log_event(
                logger, "SMART_ENTRY_FIRST_LTP_RECORDED",
                symbol=tradingsymbol,
                first_ltp=round(ltp, 2),
            )

        # ── Rolling highest ────────────────────────────────────────────────
        existing_high = self._highest_ltp.get(tradingsymbol)
        if existing_high is None or existing_high[0] != today or ltp > existing_high[1]:
            self._highest_ltp[tradingsymbol] = (today, ltp)

    def get_premium_context(self, tradingsymbol: str) -> tuple[float | None, float | None]:
        """
        Return (day_low, day_high) for *tradingsymbol* on today's session.

        day_low  — first-seen LTP (proxy for intraday premium low).
        day_high — highest LTP seen today (proxy for intraday premium high).

        Returns (None, None) if no data has been recorded yet.
        Both values are for today only; stale data from previous days is
        treated as absent.
        """
        today = date.today()
        day_low: float | None = None
        day_high: float | None = None
        first = self._first_ltp.get(tradingsymbol)
        if first and first[0] == today:
            day_low = first[1]
        high = self._highest_ltp.get(tradingsymbol)
        if high and high[0] == today:
            day_high = high[1]
        return day_low, day_high

    def on_trade_closed(self, realised_pnl_pts: float) -> None:
        """
        Call when a trade closes.  A negative P&L (loss) starts the cooldown;
        breakeven or profit resets it immediately.
        """
        if realised_pnl_pts < 0 and self._cooldown_max > 0:
            self._cooldown_left = self._cooldown_max
            log_event(
                logger, "SMART_ENTRY_COOLDOWN_STARTED",
                pnl_pts=round(realised_pnl_pts, 2),
                cooldown_candles=self._cooldown_max,
            )
        else:
            self._cooldown_left = 0

    def on_candle(self) -> None:
        """
        Call on every completed 5m candle (even when flat / not in a trade).
        Counts down the post-loss cooldown.
        """
        if self._cooldown_left > 0:
            self._cooldown_left -= 1
            if self._cooldown_left == 0:
                log_event(logger, "SMART_ENTRY_COOLDOWN_EXPIRED")

    # ── Gate ──────────────────────────────────────────────────────────────────

    # ── Squeeze detection helper ───────────────────────────────────────────────

    def _is_squeeze(self, side: str, candles_5m: Sequence[Candle]) -> bool:
        """
        Return True if the last N completed candles are all bullish (CE) or
        all bearish (PE) — indicating a momentum squeeze move.
        """
        if not self._squeeze_bypass or self._squeeze_n <= 0:
            return False
        if len(candles_5m) < self._squeeze_n:
            return False
        recent = candles_5m[-self._squeeze_n:]
        if side == "CE":
            return all(c.close > c.open for c in recent)
        else:
            return all(c.close < c.open for c in recent)

    def _is_structure_breakdown(self, side: str, candles_5m: Sequence[Candle]) -> bool:
        """
        Return True when N consecutive lower highs (PE) or higher lows (CE)
        are visible in the recent candles, optionally confirmed by close
        crossing EMA9.

        This identifies a *trend already in motion* rather than a chop
        reversal — the exact scenario where cooldown should step aside.

        PE: last N candles each have a lower HIGH than the one before.
        CE: last N candles each have a higher LOW than the one before.
        EMA confirm: for PE, close[-1] < EMA9[-1]; for CE, close[-1] > EMA9[-1].
        """
        n = self._structure_bypass_n
        if n <= 0 or len(candles_5m) < n + 1:
            return False

        recent = candles_5m[-(n + 1):]   # n+1 candles so we get n gaps

        if side == "PE":
            # N consecutive lower highs
            if not all(recent[i].high > recent[i + 1].high for i in range(n)):
                return False
        else:
            # N consecutive higher lows
            if not all(recent[i].low < recent[i + 1].low for i in range(n)):
                return False

        # Optional EMA9 confirmation — close must be on correct side of EMA9
        if self._structure_bypass_ema and len(candles_5m) >= 9:
            from market.indicators import ema as _ema
            ema9_series = _ema(candles_5m, 9)
            e9 = ema9_series[-1]
            if e9 is not None:
                close = candles_5m[-1].close
                if side == "PE" and close >= e9:
                    return False
                if side == "CE" and close <= e9:
                    return False

        return True

    def allow(
        self,
        direction: str,           # "CE" or "PE"  (prefix match — "CE_ORB" → CE)
        candles_5m: Sequence[Candle],
        candles_15m: Sequence[Candle] | None = None,
        option_ltp: float | None = None,
        tradingsymbol: str | None = None,
    ) -> bool:
        """
        Return True if all enabled filters pass for this signal candle.
        direction is the raw signal string; only the CE/PE prefix matters.

        All filters default to pass-through (return True) when their inputs
        are insufficient (e.g. not enough candles for ATR/EMA).

        candles_15m   : optional list of completed 15m candles for Filter 6.
                        When None or too short the filter is skipped (fail-open).
        option_ltp    : current option LTP at signal time — used by Filter 7.
                        When None the filter is skipped (fail-open).
        tradingsymbol : option symbol string — used by Filter 7 to look up the
                        first-seen LTP.  When None the filter is skipped.
        """
        side = "CE" if direction.startswith("CE") else "PE"

        # When called with no candles (e.g. Filter 7 late gate in execute_entry
        # where candle-based filters already ran), skip straight to Filter 7.
        if not candles_5m:
            # Jump to Filter 7 only — all other filters need candle data.
            if self._max_ext_pct > 0 and option_ltp is not None and tradingsymbol is not None:
                today = date.today()
                existing = self._first_ltp.get(tradingsymbol)
                if existing is not None:
                    stored_date, first_ltp = existing
                    if stored_date == today and first_ltp > 0:
                        extension = (option_ltp - first_ltp) / first_ltp
                        if extension > self._max_ext_pct:
                            log_event(
                                logger, "SMART_ENTRY_BLOCKED_PREMIUM_EXTENSION",
                                direction=direction,
                                symbol=tradingsymbol,
                                current_ltp=round(option_ltp, 2),
                                first_ltp=round(first_ltp, 2),
                                extension_pct=round(extension * 100, 1),
                                max_pct=round(self._max_ext_pct * 100, 1),
                                reason=(
                                    f"option already up {extension * 100:.1f}% "
                                    f"from first-seen {first_ltp:.2f} — "
                                    f"limit is {self._max_ext_pct * 100:.0f}%"
                                ),
                            )
                            return False
            return True

        c0 = candles_5m[-1]

        # ── Bounce-exempt strategy check ──────────────────────────────────────
        # VWAP/NATR bounce signals bypass Filters 1, 4 & 5 (body/ATR ratio and
        # EMA gap filters).  These strategies confirm entry via their own
        # structural level (VWAP retest / ATR trailing-stop crossover) — the EMA
        # gap is expected to be flat at the moment of a bounce, and the body
        # filter penalises the narrow reclaim candles that are normal on bounces.
        # The exemption is keyed on the strategy suffix in the direction string
        # (e.g. "CE_VWAP" matches "VWAP", "PE_NATR" matches "NATR").
        _bounce_exempt = bool(self._bounce_exempt) and any(s in direction for s in self._bounce_exempt)
        if _bounce_exempt:
            log_event(
                logger, "SMART_ENTRY_BOUNCE_EXEMPT",
                direction=direction,
                exempt_strategies=sorted(self._bounce_exempt),
                reason="bounce strategy — body/ATR and EMA-gap filters skipped",
            )

        # ── Squeeze bypass pre-check ──────────────────────────────────────────
        # If N consecutive 5m candles are all in the signal direction, the 15m
        # trend filter and EMA slope filter are skipped (squeeze move detected).
        _squeeze_active = self._is_squeeze(side, candles_5m)
        if _squeeze_active:
            log_event(
                logger, "SMART_ENTRY_SQUEEZE_BYPASS",
                direction=direction,
                candles=self._squeeze_n,
                reason="consecutive same-direction 5m candles — bypassing 15m/slope filters",
            )

        # ── Filter 1: body / ATR ratio ────────────────────────────────────────
        # During a squeeze move, use the relaxed ratio (squeeze_body_atr_ratio)
        # if it is configured — captures valid continuation candles on trend days
        # whose bodies are smaller because momentum is already priced in.
        # Bounce-exempt strategies (VWAP/NATR) always skip this filter.
        if self._min_body_atr > 0 and not _bounce_exempt:
            atr_val = atr_at(candles_5m, period=14)
            if atr_val:
                body = abs(c0.close - c0.open)
                _ratio = (
                    self._squeeze_body_atr
                    if _squeeze_active and self._squeeze_body_atr > 0
                    else self._min_body_atr
                )
                if body < atr_val * _ratio:
                    log_event(
                        logger, "SMART_ENTRY_BLOCKED_BODY",
                        direction=direction,
                        body=round(body, 2),
                        atr=round(atr_val, 2),
                        min_ratio=_ratio,
                        required=round(atr_val * _ratio, 2),
                        squeeze_relaxed=(_squeeze_active and self._squeeze_body_atr > 0),
                    )
                    return False

        # ── Filter 2: EMA9 slope ───────────────────────────────────────────────
        if self._require_slope and not _squeeze_active and len(candles_5m) >= 10:
            ema9_series = ema(candles_5m, 9)
            e9_now  = ema9_series[-1]
            e9_prev = ema9_series[-2]
            if e9_now is not None and e9_prev is not None:
                rising = e9_now > e9_prev
                if side == "CE" and not rising:
                    log_event(
                        logger, "SMART_ENTRY_BLOCKED_SLOPE",
                        direction=direction,
                        ema9_now=round(e9_now, 2),
                        ema9_prev=round(e9_prev, 2),
                        reason="EMA9 not rising for CE",
                    )
                    return False
                if side == "PE" and rising:
                    log_event(
                        logger, "SMART_ENTRY_BLOCKED_SLOPE",
                        direction=direction,
                        ema9_now=round(e9_now, 2),
                        ema9_prev=round(e9_prev, 2),
                        reason="EMA9 not falling for PE",
                    )
                    return False

        # ── Filter 3: post-loss cooldown ──────────────────────────────────────
        if self._cooldown_left > 0:
            # Structure breakdown bypass: when N consecutive lower highs (PE)
            # or higher lows (CE) are visible AND close is already below/above
            # EMA9, the market is trending — not choppy.  Reduce cooldown to 1
            # so the very next candle can trade.  This prevents the exact
            # scenario seen on 2026-10-05 where PE_NATR at 10:20 was blocked by
            # cooldown=1 while 3 consecutive lower highs + close < EMA9 were
            # plainly visible.
            if self._structure_bypass_n > 0 and self._cooldown_left > 1:
                if self._is_structure_breakdown(side, candles_5m):
                    log_event(
                        logger, "SMART_ENTRY_STRUCTURE_BYPASS_COOLDOWN",
                        direction=direction,
                        cooldown_was=self._cooldown_left,
                        reduced_to=1,
                        reason="N consecutive lower-highs/higher-lows with EMA9 confirm",
                    )
                    self._cooldown_left = 1   # allow entry on the very next candle
            log_event(
                logger, "SMART_ENTRY_BLOCKED_COOLDOWN",
                direction=direction,
                candles_remaining=self._cooldown_left,
            )
            return False

        # ── Filters 4 & 5: EMA gap — need both EMA9 and EMA21 ────────────────
        # Bounce-exempt strategies (VWAP/NATR) skip these filters: the EMA is
        # expected to be flat at a VWAP retest — that is not a noise crossover.
        if (self._min_ema_gap > 0 or self._require_gap_wide) and len(candles_5m) >= 21 and not _bounce_exempt:
            ema9_series  = ema(candles_5m, 9)
            ema21_series = ema(candles_5m, 21)
            e9_now   = ema9_series[-1]
            e21_now  = ema21_series[-1]
            e9_prev  = ema9_series[-2]
            e21_prev = ema21_series[-2]

            if e9_now is not None and e21_now is not None:
                gap_now = e9_now - e21_now   # positive = CE territory

                # ── Filter 4: minimum gap magnitude ───────────────────────────
                if self._min_ema_gap > 0:
                    # CE needs gap >= +min; PE needs gap <= -min
                    directed_gap = gap_now if side == "CE" else -gap_now
                    if directed_gap < self._min_ema_gap:
                        log_event(
                            logger, "SMART_ENTRY_BLOCKED_EMA_GAP",
                            direction=direction,
                            ema9=round(e9_now, 2),
                            ema21=round(e21_now, 2),
                            gap=round(gap_now, 2),
                            required=self._min_ema_gap,
                        )
                        return False

                # ── Filter 5: gap must be widening ────────────────────────────
                if self._require_gap_wide and e9_prev is not None and e21_prev is not None:
                    gap_prev = e9_prev - e21_prev
                    # CE: gap_now > gap_prev (gap growing positive)
                    # PE: gap_now < gap_prev (gap growing negative)
                    widening = gap_now > gap_prev if side == "CE" else gap_now < gap_prev
                    if not widening:
                        log_event(
                            logger, "SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING",
                            direction=direction,
                            gap_now=round(gap_now, 2),
                            gap_prev=round(gap_prev, 2),
                            reason="EMA gap not widening",
                        )
                        return False

        # ── Filter 6: 15m trend alignment ─────────────────────────────────────
        # Squeeze bypass skips this filter entirely.
        if self._require_15m_trend and not _squeeze_active and candles_15m and len(candles_15m) >= 21:
            ema21_15m_series = ema(candles_15m, 21)
            e21_15m = ema21_15m_series[-1]
            c15_last = candles_15m[-1]
            if e21_15m is not None:
                gap = c15_last.close - e21_15m   # positive = close above EMA21
                bullish_15m = gap > 0

                # Gap-threshold softening (Filter 6b):
                # When max_15m_gap_pts > 0, allow the entry even if technically
                # on the wrong side of EMA21, as long as the gap is small.
                # This catches recoveries where EMA21 is lagging a rally.
                if self._max_15m_gap > 0:
                    # CE: block only when close is MORE than max_15m_gap below EMA21
                    if side == "CE" and gap < -self._max_15m_gap:
                        log_event(
                            logger, "SMART_ENTRY_BLOCKED_15M_TREND",
                            direction=direction,
                            close_15m=round(c15_last.close, 2),
                            ema21_15m=round(e21_15m, 2),
                            gap=round(gap, 1),
                            threshold=-self._max_15m_gap,
                            reason="15m close too far below EMA21 for CE",
                        )
                        return False
                    # PE: block only when close is MORE than max_15m_gap above EMA21
                    if side == "PE" and gap > self._max_15m_gap:
                        log_event(
                            logger, "SMART_ENTRY_BLOCKED_15M_TREND",
                            direction=direction,
                            close_15m=round(c15_last.close, 2),
                            ema21_15m=round(e21_15m, 2),
                            gap=round(gap, 1),
                            threshold=self._max_15m_gap,
                            reason="15m close too far above EMA21 for PE",
                        )
                        return False
                else:
                    # Original binary behaviour: any gap in wrong direction blocks
                    if side == "CE" and not bullish_15m:
                        log_event(
                            logger, "SMART_ENTRY_BLOCKED_15M_TREND",
                            direction=direction,
                            close_15m=round(c15_last.close, 2),
                            ema21_15m=round(e21_15m, 2),
                            reason="15m close below 15m EMA21 for CE",
                        )
                        return False
                    if side == "PE" and bullish_15m:
                        log_event(
                            logger, "SMART_ENTRY_BLOCKED_15M_TREND",
                            direction=direction,
                            close_15m=round(c15_last.close, 2),
                            ema21_15m=round(e21_15m, 2),
                            reason="15m close above 15m EMA21 for PE",
                        )
                        return False

        # ── Filter 7: option premium extension ───────────────────────────────
        if self._max_ext_pct > 0 and option_ltp is not None and tradingsymbol is not None:
            today = date.today()
            existing = self._first_ltp.get(tradingsymbol)
            if existing is not None:
                stored_date, first_ltp = existing
                if stored_date == today and first_ltp > 0:
                    extension = (option_ltp - first_ltp) / first_ltp
                    if extension > self._max_ext_pct:
                        log_event(
                            logger, "SMART_ENTRY_BLOCKED_PREMIUM_EXTENSION",
                            direction=direction,
                            symbol=tradingsymbol,
                            current_ltp=round(option_ltp, 2),
                            first_ltp=round(first_ltp, 2),
                            extension_pct=round(extension * 100, 1),
                            max_pct=round(self._max_ext_pct * 100, 1),
                            reason=(
                                f"option already up {extension * 100:.1f}% "
                                f"from first-seen {first_ltp:.2f} — "
                                f"limit is {self._max_ext_pct * 100:.0f}%"
                            ),
                        )
                        return False

        return True

    # ── Inspection ────────────────────────────────────────────────────────────

    @property
    def cooldown_active(self) -> bool:
        return self._cooldown_left > 0

    @property
    def cooldown_remaining(self) -> int:
        return self._cooldown_left
