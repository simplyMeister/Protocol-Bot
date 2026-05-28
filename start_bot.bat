@echo off
echo ========================================
echo Protocol Bot Startup Helper v2
echo ========================================
echo.

echo Step 1: Killing ALL Python processes...
echo   (Using multiple methods to ensure cleanup)

REM Method 1: taskkill
taskkill /F /IM python.exe 2>nul
taskkill /F /IM python3.11.exe 2>nul

REM Method 2: wmic (more thorough)
wmic process where "name='python.exe' or name='python3.11.exe'" delete 2>nul

echo   - Cleanup complete
echo.

echo Step 2: Verifying no Python processes remain...
tasklist | findstr /I python >nul
if %errorlevel% equ 0 (
    echo   WARNING: Some Python processes may still be running!
    echo   Please close ALL terminal windows and try again.
    pause
    exit /b 1
) else (
    echo   - All clear!
)
echo.

echo Step 3: Waiting 10 seconds for Telegram API to reset...
echo   (This wait is CRITICAL - do not skip!)
timeout /t 10 /nobreak
echo   - Ready to start!
echo.

echo Step 4: Starting Protocol Bot...
echo ========================================
echo   If you see "Bot is running..." below, it's working!
echo   Press Ctrl+C to stop the bot when needed.
echo ========================================
echo.

python main.py

echo.
echo ========================================
echo Bot has stopped.
echo ========================================
pause
