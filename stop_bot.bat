@echo off
:: Stops the dashboard, the auto-restart launcher and the trading bot,
:: and pauses auto-start until you press Start or run launch.bat again.
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" stop_bot.py
) else (
    python stop_bot.py
)
pause
