"""
Diagnose why no signals fired today by replaying the candle data
from .bot_state.json through each strategy's conditions.
"""
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

state = json.loads(Path(".bot_state.json").read_text())
raw = state.get("candles_5m", [])

# Parse candles
class C:
    def __init__(self, d):
        self.timestamp = datetime.fromisoformat(d["t"])
        self.open = d["o"]; self.high = d["h"]
        self.low = d["l"];  self.close = d["c"]
        self.volume = d.get("v", 0)

candles = [C(d) for d in raw]
today = date.today()
today_candles = [c for c in candles if c.timestamp.date() == today]
all_candles   = candles  # full list for EMA computation

print(f"Total candles in state : {len(candles)}")
print(f"Today's candles        : {len(today_candles)}")
if today_candles:
    print(f"First today candle     : {today_candles[0].timestamp}  open={today_candles[0].open}  close={today_candles[0].close}")
    print(f"Last  today candle     : {today_candles[-1].timestamp}  open={today_candles[-1].open}  close={today_candles[-1].close}")
else:
    print("  *** NO TODAY CANDLES FOUND IN STATE FILE ***")
    print("  This means the bot has not yet received any 5m candle completions today.")
    print("  The state file still shows yesterday's data.")

print()
print("Last 5 candles in state (any date):")
for c in candles[-5:]:
    print(f"  {c.timestamp}  O={c.open}  H={c.high}  L={c.low}  C={c.close}  V={c.volume}")

# Check if bot started today
print()
print(f"Today date: {today}")
print(f"Last candle date: {candles[-1].timestamp.date() if candles else 'N/A'}")
if candles and candles[-1].timestamp.date() < today:
    print()
    print("==> ROOT CAUSE: The bot_state.json candles are from YESTERDAY.")
    print("    This means the bot was started but has NOT received any completed")
    print("    5m candles for today yet, OR the WebSocket is not delivering ticks.")
    print()
    print("    Check:")
    print("    1. Is the market open today? (check for holiday)")
    print("    2. Is the WebSocket connected and receiving SENSEX ticks?")
    print("    3. What time did the bot start today vs market open (09:15)?")
