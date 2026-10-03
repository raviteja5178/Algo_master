@echo off
:: Auto-restarting launcher for sensex-auto-trader
:: The bot will restart automatically after any exit (crash, keyboard interrupt, etc.)
:: To STOP permanently: close this window, OR press Ctrl+C twice within 5 seconds

title SENSEX Bot [Auto-Restart]
echo ============================================================
echo  SENSEX Auto-Trader — Persistent Launcher
echo  Bot will auto-restart on any exit.
echo  To stop permanently: close this window.
echo ============================================================
echo.

:LOOP
echo [%date% %time%] Starting bot...
python main.py

set EXIT_CODE=%ERRORLEVEL%
echo.
echo [%date% %time%] Bot exited with code %EXIT_CODE%.

:: Check if it's past 15:30 IST — no point restarting after market close
:: (Windows time comparison is limited; just add a short wait and let EOD guard handle it)
echo Waiting 10 seconds before restart...
timeout /t 10 /nobreak >nul

echo.
goto LOOP
