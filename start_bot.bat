@echo off
cd /d "C:\Users\todam\valorant-store-bot"

:loop
if exist "logs\bot.crash.log" (
    for %%A in ("logs\bot.crash.log") do if %%~zA GTR 5242880 del /q "logs\bot.crash.log"
)
".venv\Scripts\python.exe" -u bot.py >> "logs\bot.crash.log" 2>&1
echo [%date% %time%] bot.py exited (exit code %errorlevel%). Restarting in 15s... >> "logs\bot.crash.log"
timeout /t 15 /nobreak >nul
goto loop
