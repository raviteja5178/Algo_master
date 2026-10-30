@echo off
:: ============================================================
::  SENSEX Auto-Trader — Dashboard Launcher
::
::  Starts ONLY the UI dashboard (Flask).  The built-in self-
::  healing watchdog inside the dashboard will:
::    • Auto-login at 09:00–09:20 IST if credentials are in .env
::    • Auto-start the bot once the token is valid
::    • Kill zombie bots (log silent >5 min) and restart them
::    • Stop the bot after 15:35 IST automatically
::
::  Dashboard:  http://127.0.0.1:5000
::
::  To stop everything: run stop_bot.bat
::  To also run a separate launcher:  use launch.bat instead
:: ============================================================

title SENSEX Dashboard [Self-Healing]
cd /d "%~dp0"

echo.
echo  ============================================================
echo   SENSEX Auto-Trader — Self-Healing Dashboard
echo   Dashboard:  http://127.0.0.1:5000
echo  ============================================================
echo.

:: ── Clear stale lock files from a previous crashed session ──────────────────
if exist ".bot.lock"      del /f /q ".bot.lock"      2>nul
if exist ".bot.pid"       del /f /q ".bot.pid"        2>nul
if exist ".bot_paused"    del /f /q ".bot_paused"     2>nul

echo [%date% %time%] Stale locks cleared.
echo [%date% %time%] Starting dashboard...
echo.

py ui\app.py

:: If we get here Flask exited — keep the window open for diagnostics
echo.
echo [%date% %time%] Dashboard exited.
pause
