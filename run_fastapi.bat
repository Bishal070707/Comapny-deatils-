@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Create it with:
  echo   py -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
echo Starting FastAPI Email Scheduler on http://localhost:8000
echo API Documentation: http://localhost:8000/docs
echo.
.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
