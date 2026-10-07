# SENSEX Auto-Trader — System Setup Guide

This guide provides step-by-step instructions for setting up and running **SENSEX Auto-Trader** (Surya Arjun) on a fresh system (Windows, macOS, or Linux).

---

## 1. Prerequisites & System Requirements

### Hardware / OS
- **Operating System:** Windows 10/11, macOS, or Linux (Ubuntu 20.04+ recommended)
- **Memory (RAM):** 4 GB minimum (8 GB+ recommended, especially if running local Ollama models)
- **Disk Space:** ~1 GB free disk space
- **Stable Internet Connection:** Required for low-latency WebSocket live market feeds

### Software Dependencies
- **Python:** Python `3.10` to `3.12` installed
- **Git:** Git CLI installed
- **Web Browser:** Chrome, Edge, Brave, or Firefox (for the Web Dashboard)

---

## 2. Zerodha Kite Connect Prerequisites

To trade or stream market data, you will need active Zerodha Kite Connect API credentials:
1. **Zerodha Kite Account:** Active trading account with Zerodha.
2. **Kite Connect Developer App:**
   - Register/login at [Kite Connect Developer Portal](https://kite.trade/).
   - Create an app (under SENSEX/BSE segment permissions).
   - Set the Redirect URL to: `http://127.0.0.1`
   - Copy your **API Key** (`KITE_API_KEY`) and **API Secret** (`KITE_API_SECRET`).
3. **Automated Daily Login (Recommended):**
   - Enable 2FA TOTP in your Zerodha profile (Settings > Password & Security > External 2FA Authenticator).
   - Copy and save the **TOTP Secret Key** (`KITE_TOTP_SECRET`).

---

## 3. Clone and Setup Environment

### Step 3.1: Clone the Repository
```bash
git clone <repository_url> sensex-auto-trader
cd sensex-auto-trader
```

### Step 3.2: Create and Activate Python Virtual Environment

**On Windows (PowerShell / Command Prompt):**
```powershell
python -m venv venv
.\venv\Scripts\activate
```

**On Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3.3: Upgrade `pip` and Install Dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Configuration (`.env` Setup)

Create your local `.env` configuration file from the template:

```bash
# Windows Command Prompt / PowerShell / Linux / macOS:
cp .env.example .env
```
*(On Windows Command Prompt if `cp` is unavailable: `copy .env.example .env`)*

Open `.env` in any text editor and fill in the required parameters:

### A. Broker Authentication
```env
# Zerodha Kite Connect Credentials
KITE_API_KEY=your_kite_api_key_here
KITE_API_SECRET=your_kite_api_secret_here

# Automated Login (Optional but highly recommended)
KITE_USER_ID=your_zerodha_user_id
KITE_PASSWORD=your_zerodha_password
KITE_TOTP_SECRET=your_totp_secret_key

# Manual token (Only needed if NOT using automated login)
KITE_ACCESS_TOKEN=
```

### B. Trading Mode & Safety Switch
```env
# Options: PAPER (Simulated) | SHADOW (Signals only) | LIVE (Real orders)
TRADING_MODE=PAPER

# Must be explicitly set to 'true' to execute LIVE orders at the broker
ENABLE_LIVE_TRADING=false
```

### C. Instrument & Contract Expiry
```env
UNDERLYING=SENSEX
QUANTITY=20

# Active SENSEX weekly or monthly expiry date (YYYY-MM-DD)
EXPIRY_MODE=CONFIGURED
CONFIGURED_EXPIRY=2026-10-08
```

### D. Core Risk & Stop-Loss Parameters
```env
INITIAL_SL_POINTS=30
BREAK_EVEN_TRIGGER_POINTS=30
TRAIL_STEP_POINTS=10
FORCE_EXIT_TIME=15:15
NO_NEW_ENTRY_AFTER=15:00
```

---

## 5. Verifying the Setup

Run the automated test suite to ensure all dependencies, risk modules, and strategy rules are functional:

```bash
python -m pytest tests/ -v
```

All unit and integration tests should pass without errors.

---

## 6. How to Run

### Method A: Web Dashboard (Recommended)

The Web Dashboard gives you complete control over starting/stopping the bot, viewing open positions, trailing SL status, P&L charts, and modifying parameters without editing files manually.

1. **Launch the Dashboard:**
   - **Windows:** Double-click [`start.bat`](start.bat) or run:
     ```bash
     python -m ui.app
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m ui.app
     ```
2. **Access the Dashboard:**
   - Open your browser to: **`http://localhost:5000`** (or `http://127.0.0.1:5000`)
3. **Start the Engine:**
   - Click the **▶ Start Bot** button on the dashboard.

---

### Method B: Headless Terminal / Persistent Runner

If running on a VPS or cloud instance:

1. **Direct execution:**
   ```bash
   python main.py
   ```
2. **Auto-restarting runner (Windows):**
   - Run [`start_persistent.bat`](start_persistent.bat) to automatically restart the bot in case of transient exceptions during market hours.

---

## 7. Daily Operations & Routine

1. **Check Expiry Date (`CONFIGURED_EXPIRY`):**
   - Ensure `.env` or the Dashboard UI has the correct upcoming weekly SENSEX expiry date set before market open (09:15 IST).
2. **Authentication:**
   - If `KITE_USER_ID`, `KITE_PASSWORD`, and `KITE_TOTP_SECRET` are configured, the bot will log in and renew `KITE_ACCESS_TOKEN` automatically upon launch.
   - If logging in manually, run `python -c "from broker.authentication import generate_login_url; print(generate_login_url())"` in the terminal, complete authentication in your browser, and save the generated token.
3. **Session Timing:**
   - **09:15 IST:** Market open (Bot initializes indicators and market stream).
   - **15:00 IST:** `NO_NEW_ENTRY_AFTER` cut-off (no new trades taken).
   - **15:15 IST:** `FORCE_EXIT_TIME` forced square-off (open positions closed at market price).

---

## 8. Directory Structure Overview

```
sensex-auto-trader/
├── main.py                   # Main orchestrator loop
├── config/settings.py        # Central configuration loaded from .env
├── broker/                   # Zerodha API integration & auto-authentication
├── market/                   # WebSocket client, indicators (EMA/ATR/VWAP), candle builder
├── strategies/               # EMA, ORB, VWAP, TRB, and OB signal engines
├── execution/                # Order placement, trailing stop, target, and position management
├── risk/                     # Safety manager and broker reconciliation
├── persistence/              # SQLite database (trades.db) for trade history
├── ui/                       # Flask Web Dashboard application
├── tests/                    # Comprehensive test suite
├── .env.example              # Environment variables template
├── requirements.txt          # Python packages list
└── start.bat                 # One-click Windows starter
```

---

## 9. Troubleshooting & Common Issues

| Issue | Cause | Solution |
|---|---|---|
| `TokenException` / Invalid Token | Zerodha access tokens expire daily at ~06:00 AM IST. | Provide `KITE_USER_ID`, `KITE_PASSWORD`, and `KITE_TOTP_SECRET` in `.env` for automatic daily login, or re-authenticate manually. |
| `InstrumentNotFound` | `CONFIGURED_EXPIRY` is expired or format is wrong. | Update `CONFIGURED_EXPIRY=YYYY-MM-DD` in `.env` to the next active SENSEX expiry. |
| Port 5000 Already in Use | Another process is using port 5000. | Kill the existing process or run Flask on another port: `python -m ui.app --port 5001`. |
| Orders not firing in LIVE mode | Safety switch disabled. | Verify both `TRADING_MODE=LIVE` and `ENABLE_LIVE_TRADING=true` are set in `.env`. |
| Missing Python packages | Dependencies not installed in the active venv. | Run `pip install -r requirements.txt` inside your virtual environment. |
