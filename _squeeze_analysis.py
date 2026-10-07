from market.historical_data import fetch_historical_candles, SENSEX_TOKEN
from market.indicators import ema

candles = fetch_historical_candles(SENSEX_TOKEN, interval="5minute", days_back=2)
today = [c for c in candles if c.timestamp.date().isoformat() == "2026-10-07"]

print("=== Consecutive same-direction runs at CE signal times ===")
key_times = ["10:05", "10:15", "10:20", "10:25"]
for kt in key_times:
    idx = next((i for i, c in enumerate(today) if c.timestamp.strftime("%H:%M") == kt), None)
    if idx is None:
        continue
    c = today[idx]
    direction = "UP" if c.close > c.open else "DN"
    run = 0
    for i in range(idx, -1, -1):
        ci = today[i]
        d = "UP" if ci.close > ci.open else "DN"
        if d == direction:
            run += 1
        else:
            break
    print(f"  {kt}: close={c.close:.2f} [{direction}]  consecutive same-dir run={run} candles")

print()
print("=== EMA9 / EMA21 gap per candle (today) ===")
# Use 60 recent candles for a warm EMA seed
closes_all = [c.close for c in candles[-60:]]
e9_all = ema(closes_all, 9)
e21_all = ema(closes_all, 21)
n_today = len(today)
offset = len(closes_all) - n_today

print(f"  {'Time':<6}  {'Close':>8}  {'EMA9':>8}  {'EMA21':>8}  {'Gap':>8}  Dir")
for i, c in enumerate(today):
    ai = offset + i
    if e9_all[ai] is not None and e21_all[ai] is not None:
        gap = e9_all[ai] - e21_all[ai]
        d = "UP" if c.close > c.open else "DN"
        marker = " <-- SIGNAL" if c.timestamp.strftime("%H:%M") in ["09:15","09:45","09:55","10:05","10:15","10:20","10:25"] else ""
        print(f"  {c.timestamp.strftime('%H:%M'):<6}  {c.close:>8.2f}  {e9_all[ai]:>8.2f}  {e21_all[ai]:>8.2f}  {gap:>+8.2f}  [{d}]{marker}")
