@echo off
cd /d "C:\Users\todam\valorant-store-bot"
".venv\Scripts\python.exe" -u bot.py >> "logs\bot.out.log" 2>> "logs\bot.err.log"
