@echo off
:: ============================================================
::  SENSEX Auto-Trader — Full Launcher
::  Starts the UI dashboard + a separate bot launcher process.
::
::  The dashboard's built-in watchdog also monitors and restarts
::  the bot independently, so both layers of protection are active.
::
::  Dashboard : http://127.0.0.1:5000
::  Bot       : run_bot.py  (auto-restarts on crash)
::
::  Recommended alternative: use start_dashboard.bat (dashboard-only)
::  unless you specifically want the run_bot.py launcher loop too.
::
::  To stop everything: run stop_bot.bat
:: ============================================================

title SENSEX Auto-Trader [Bot + UI]
cd /d "%~dp0"

echo.
echo  ============================================================
echo   SENSEX Auto-Trader — Full Launcher (Bot + Dashboard)
echo   Dashboard:  http://127.0.0.1:5000
echo  ============================================================
echo.

:: ── Clear stale lock files from a previous crashed session ──────────────────
if exist ".bot.lock"      del /f /q ".bot.lock"      2>nul
if exist ".launcher.lock" del /f /q ".launcher.lock"  2>nul
if exist ".bot.pid"       del /f /q ".bot.pid"        2>nul
if exist ".bot_paused"    del /f /q ".bot_paused"     2>nul

echo [%date% %time%] Stale locks cleared.
echo.

:: ── Start the UI dashboard in a separate minimised window ────────────────────
echo [%date% %time%] Starting UI dashboard...
start "SENSEX UI [Dashboard]" /min cmd /c "cd /d "%~dp0" && py ui\app.py"
timeout /t 2 /nobreak >nul

:: ── Start the trading bot launcher (persistent auto-restart) ─────────────────
echo [%date% %time%] Starting trading bot launcher (auto-restart active)...
echo.
py run_bot.py

:: ── run_bot.py only exits on manual stop or double Ctrl+C ─────────────────
echo.
echo [%date% %time%] Launcher exited. Press any key to close.
pause
