@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Create it with:
  echo   py -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
.venv\Scripts\python.exe scheduler.py