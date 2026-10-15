@echo off
:: ============================================================
::  SENSEX Auto-Trader — Single Launcher
::  Starts BOTH the trading bot and the UI dashboard.
::
::  Bot   : python run_bot.py   (auto-restarts on crash)
::  UI    : python ui\app.py    (dashboard at http://127.0.0.1:5000)
::
::  To stop everything: close this window
:: ============================================================

title SENSEX Auto-Trader [Bot + UI]
cd /d "%~dp0"

echo.
echo  ============================================================
echo   SENSEX Auto-Trader — Starting Bot and Dashboard
echo  ============================================================
echo.
echo   Bot    : python run_bot.py  (auto-restart enabled)
echo   UI     : http://127.0.0.1:5000
echo.
echo   To stop everything: close this window
echo  ============================================================
echo.

:: ── Start the UI dashboard in a separate background window ───────────────────
echo [%date% %time%] Starting UI dashboard...
start "SENSEX UI [Dashboard]" /min cmd /c "cd /d "%~dp0" && python ui\app.py"
timeout /t 2 /nobreak >nul

:: ── Start the trading bot (persistent, auto-restart) in this window ───────────
echo [%date% %time%] Starting trading bot (auto-restart active)...
echo.
python run_bot.py

:: ── If run_bot.py exits (should not happen), pause so the window stays open ──
echo.
echo [%date% %time%] Launcher exited. Press any key to close.
pause
