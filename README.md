# Surya Arjun — SENSEX CE/PE Automated Trading Bot

A production-quality Python bot for **Zerodha Kite Connect** that automates order execution and trade management for two pre-tested SENSEX options strategies.

> **Warning:** This bot automates leveraged options trading and can incur rapid losses.  
> Complete paper/shadow testing before enabling LIVE mode.

---

## 1. Project Overview

The bot:
- Reads live SENSEX market data via WebSocket.
- Builds 5-minute and 15-minute completed candles.
- Evaluates the exact CE and PE entry conditions.
- Dynamically selects the nearest ATM SENSEX option.
- Places BUY orders and confirms actual broker fill.
- Places and manages protective stop-loss orders.
- Moves the stop-loss to break-even after +30 points of profit.
- Trails the stop-loss upward in +10 point steps.
- Maintains a moving target reference.
- Forces square-off at 3:15 PM IST.
- Recovers safely after restart.

---

## 2. Exact Strategy Conditions

### CE (Bullish — Buy Call)

All four conditions must be true on **completed** candles:

```
5m close[0] > 5m EMA21[0]
5m EMA9[0]  > 5m EMA21[0]
5m close[0] > 5m high[1]
15m close[0] > 15m EMA21[0]
```

### PE (Bearish — Buy Put)

All four conditions must be true on **completed** candles:

```
5m close[0] < 5m EMA21[0]
5m EMA9[0]  < 5m EMA21[0]
5m close[0] < 5m low[1]
15m close[0] < 15m EMA21[0]
```

---

## 3. Architecture

```
sensex-auto-trader/
├── main.py                   # Entry point + orchestration loop
├── config/settings.py        # All parameters from .env
├── broker/
│   ├── authentication.py     # Zerodha login + access token
│   ├── kite_client.py        # Singleton KiteConnect
│   ├── instrument_repository.py  # Load + query instrument master
│   ├── order_repository.py   # Live order queries
│   └── position_repository.py    # Live position queries
├── market/
│   ├── candle_builder.py     # Candle dataclass
│   ├── candle_aggregator.py  # Live 5m/15m aggregation
│   ├── historical_data.py    # Bootstrap from Zerodha history
│   ├── indicators.py         # EMA calculation
│   └── websocket_client.py   # KiteTicker wrapper
├── strategies/
│   ├── ce_strategy.py        # Exact CE rules
│   ├── pe_strategy.py        # Exact PE rules
│   └── signal_engine.py      # De-duplication + dispatch
├── execution/
│   ├── option_selector.py    # ATM strike selection
│   ├── order_manager.py      # Live Zerodha orders
│   ├── paper_broker.py       # Paper trade simulator
│   ├── position_manager.py   # State machine
│   ├── protective_stop.py    # Initial SL placement + modification
│   ├── trailing_stop.py      # Deterministic trailing logic
│   ├── target_manager.py     # Moving target reference
│   └── eod_manager.py        # 3:15 PM forced square-off
├── risk/safety_manager.py    # Reconciliation + mismatch halt
├── persistence/
│   ├── models.py             # SQLite schema + CRUD
│   └── trade_store.py        # Facade
├── notifications/notifier.py # Structured events
└── utils/
    ├── time_utils.py
    ├── price_utils.py
    └── logging_config.py
```

---

## 4. Zerodha API Setup

1. Sign up for [Kite Connect](https://kite.trade/).
2. Create an app and note your **API Key** and **API Secret**.
3. Add `http://127.0.0.1` as redirect URL.
4. Fill `KITE_API_KEY` and `KITE_API_SECRET` in `.env`.

---

## 5. Environment Configuration

```bash
cp .env.example .env
# Edit .env with your keys and preferences
```

All trading parameters are configurable via `.env` — no source code changes required.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `TRADING_MODE` | `PAPER` | `PAPER`, `SHADOW`, or `LIVE` |
| `ENABLE_LIVE_TRADING` | `false` | Safety switch for live orders |
| `QUANTITY` | `20` | Option lots per trade |
| `INITIAL_SL_POINTS` | `30` | Distance from fill to initial SL |
| `BREAK_EVEN_TRIGGER_POINTS` | `30` | Profit required to move SL to entry |
| `TRAIL_STEP_POINTS` | `10` | SL step size after break-even |
| `CONFIGURED_EXPIRY` | _(required)_ | SENSEX expiry date `YYYY-MM-DD` |
| `FORCE_EXIT_TIME` | `15:15` | EOD square-off time |

---

## 6. Authentication Process

```python
# One-time (run in Python shell):
from broker.authentication import generate_login_url, complete_login

url = generate_login_url()
print(url)  # Visit in browser, complete login

request_token = input("Paste request_token: ")
access_token = complete_login(request_token)
# Paste the printed KITE_ACCESS_TOKEN into your .env
```

---

## 7. Paper Mode

```env
TRADING_MODE=PAPER
```

- Uses real market data.
- Simulates fills at the current LTP.
- Simulates stop-loss triggers.
- **Never sends any order to Zerodha.**

---

## 8. Shadow Mode

```env
TRADING_MODE=SHADOW
```

- Connects to live WebSocket.
- Generates and logs real signals.
- Selects exact ATM options.
- **Never sends any order to Zerodha.**

---

## 9. Live Mode

```env
TRADING_MODE=LIVE
ENABLE_LIVE_TRADING=true
```

Both flags must be set. The bot refuses to start otherwise.

---

## 10. How the Trailing Stop Works

Starting from an entry at 220, with 30-point initial SL and 10-point trail:

| LTP | Stop | Notes |
|-----|------|-------|
| 220 | 190 | Initial protective stop |
| 249 | 190 | Below break-even trigger |
| 250 | 220 | **Break-even activated** |
| 260 | 230 | Trail step 1 |
| 270 | 240 | Trail step 2 |
| 300 | 270 | Trail step 5 |
| ↓ price falls | 270 | **Stop never moves backward** |

---

## 11. 3:15 PM Forced Exit

At or after `FORCE_EXIT_TIME` (default 15:15 IST):
1. No new entries allowed.
2. Open position is market-sold.
3. Pending stop orders are cancelled.
4. Broker position qty is verified zero.
5. Trade is marked CLOSED in DB.

---

## 12. Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Test coverage includes:
- CE/PE strategy exact rules
- Trailing stop full lifecycle
- Paper order execution
- EOD exit with retry
- Broker reconciliation mismatch

---

## 13. Recovery After Crash/Restart

On startup the bot:
1. Reads the active trade from SQLite.
2. Fetches current positions from Zerodha.
3. Reconciles expected vs actual quantity.
4. Resumes trailing management if reconciliation passes.
5. **Never creates a duplicate entry from the same signal.**

---

## 14. Known Limitations

- Historical data for SENSEX requires a valid Kite Connect subscription.
- BSE option segment code varies (`BFO`, `BFO-OPT`) — verify with the instrument master.
- WebSocket reconnection is handled by `kiteconnect`'s built-in retry; extreme network outages may require manual restart.
- Partial fills are handled: only the confirmed filled quantity is managed.
- Live target order placement (`USE_LIVE_TARGET_ORDER`) is disabled by default to prevent the target from running away.

---

## 15. Operational Checklist Before Live Use

- [ ] Completed at least 5 days of paper trading
- [ ] Verified strategy signals match manual chart analysis
- [ ] Confirmed `CONFIGURED_EXPIRY` is a valid active expiry
- [ ] Confirmed `QUANTITY` matches your risk budget
- [ ] Tested restart recovery procedure
- [ ] Verified broker reconciliation works correctly
- [ ] Set `TRADING_MODE=LIVE` AND `ENABLE_LIVE_TRADING=true`
- [ ] Ensured `KITE_ACCESS_TOKEN` is fresh (expires daily)
- [ ] Reviewed `FORCE_EXIT_TIME` for the current session
- [ ] Confirmed you have sufficient margin in the Zerodha account

---

## 16. Web Dashboard UI

A browser-based dashboard lets you monitor the bot, view trades, charts and orders, and tweak settings — without touching the terminal.

### Start the dashboard

```bash
pip install -r requirements.txt   # first time only
python -m ui.app
```

Open **http://localhost:5000** in your browser.

### Features

| Panel | What it shows |
|---|---|
| **KPI cards** | Bot state, open P&L, realised P&L, total trades + win rate |
| **Active position** | Entry, SL, target, highest LTP, trailing stop progress bar |
| **Cumulative P&L chart** | Running total of realised P&L across all closed trades |
| **Win/Loss chart** | Bar chart of winners vs losers vs break-even |
| **Trade history table** | All trades with entry/exit, P&L, status |
| **Order actions table** | Every order sent to the broker with status |
| **Live bot log** | Streaming log output from the bot process |
| **Settings panel** | Edit `.env` config (mode, SL, expiry, etc.) and save without restarting the server |

### Start / Stop bot from the UI

Click **▶ Start Bot** to launch `main.py` as a subprocess — log output streams into the dashboard in real time.
Click **■ Stop Bot** to send SIGTERM. Any open position will remain at the broker until the bot is restarted.

> The dashboard polls every 3 seconds. No WebSocket or extra setup required.
