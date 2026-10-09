"""
Precise candle count at signal time for each pivot trade.
5m candles: 09:15, 09:20, 09:25, 09:30, 09:35 ...
A candle at 09:25 CLOSES at 09:25, meaning it is the 3rd completed candle.
find_pivot_setup is called after each completed candle close.

sustain_candles=2: window = last 2 completed candles.
At signal time the LAST candle (today[-1]) is the entry candle.

Signal: PE_PIVOT fired at 09:25:01 → entry candle is 09:25 (3rd candle of day)
  today = [09:15, 09:20, 09:25]  → len(today) = 3
  window = [09:20, 09:25]        → sustain window
  before = today[-3] = 09:15     → before_close = 09:15.close
  min_today_candles check: 3 < 6 → BLOCK

Signal: CE_PIVOT fired at 09:35 → entry candle is 09:35 (5th candle of day)
  today = [09:15, 09:20, 09:25, 09:30, 09:35]  → len(today) = 5
  window = [09:30, 09:35]        → sustain window
  before = today[-3] = 09:25     → before_close = 09:25.close
  min_today_candles check: 5 < 6 → BLOCK

BUT: the actual code default is 6. The .env.example has NO entry for PIVOT_MIN_TODAY_CANDLES.
When absent from .env, _getint("PIVOT_MIN_TODAY_CANDLES", 6) returns 6.
So the guard IS active at 6.

THEREFORE: both trades SHOULD have been blocked. Yet they fired.

Possible explanations:
1. .env had PIVOT_MIN_TODAY_CANDLES=0 explicitly set
2. A different version of the code ran these trades (before min_today_candles was added)
3. The candle count was computed differently (warm-up candles mis-counted as today)
"""

# Simulate the _today() logic with seeded candles
# The agg_5m._completed contains: many prior-day candles PLUS today's candles
# _today() does: d = candles[-1].timestamp.date(); return [c for c in candles if c.timestamp.date() == d]
# candles[-1] = last completed candle = the signal candle
# All prior-day candles are filtered OUT correctly by date comparison
# So at 09:25: len(today) = 3. At 09:35: len(today) = 5. Both < 6.

print("Candle count at each signal time:")
print()
print("PE_PIVOT (09:25):")
print("  today = [09:15c, 09:20c, 09:25c]  len=3")
print("  sustain window (n=2): [09:20c, 09:25c]")
print("  before: 09:15c")
print("  min_today_candles check: 3 < 6 → BLOCK")
print()
print("CE_PIVOT (09:35):")
print("  today = [09:15c, 09:20c, 09:25c, 09:30c, 09:35c]  len=5")
print("  sustain window (n=2): [09:30c, 09:35c]")
print("  before: 09:25c")
print("  min_today_candles check: 5 < 6 → BLOCK")
print()
print("Conclusion: PIVOT_MIN_TODAY_CANDLES=6 (code default, not in .env.example)")
print("The trades fired ONLY if this setting was NOT 6 at run time.")
print()
print("Since .env.example has no PIVOT_MIN_TODAY_CANDLES entry, the actual .env")
print("determines the value. If .env also has no entry → code default = 6 → BLOCKS.")
print("The trades fired → .env must have had PIVOT_MIN_TODAY_CANDLES=0 (or missing key")
print("in an older version of settings.py that defaulted to 0).")
print()

# Check: what IS the default in the CURRENT code?
import sys
sys.path.insert(0, ".")
try:
    from config import settings
    print(f"Current settings.PIVOT_MIN_TODAY_CANDLES = {settings.PIVOT_MIN_TODAY_CANDLES}")
    print(f"Current settings.PIVOT_SUSTAIN_CANDLES    = {settings.PIVOT_SUSTAIN_CANDLES}")
    print(f"Current settings.ENABLE_PIVOT_STRATEGY    = {settings.ENABLE_PIVOT_STRATEGY}")
    print(f"Current settings.PIVOT_SL_MODE            = {settings.PIVOT_SL_MODE}")
except Exception as e:
    print(f"Could not load settings: {e}")
