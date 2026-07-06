@echo off
title EAIOS Launcher
cd /d "%~dp0"
echo.
echo  ============================================
echo   EAIOS - Enterprise AI Operating System
echo   One-click launcher (Windows)
echo  ============================================
echo.

echo [1/4] Backend dependencies (first run takes 1-2 min)...
cd /d "%~dp0backend"
if not exist .venv (
  py -m venv .venv
)
call ".venv\Scripts\activate.bat"
pip install -q -r requirements.txt

echo [2/4] Starting backend on http://localhost:8000 ...
start "EAIOS Backend" /d "%~dp0backend" cmd /k "call .venv\Scripts\activate.bat && python -m app.seed && python -m uvicorn app.main:app --port 8000"

echo [3/4] Frontend dependencies (first run takes 1-3 min)...
cd /d "%~dp0frontend"
if not exist node_modules (
  call npm install --no-audit --no-fund
)

echo [4/4] Starting frontend on http://localhost:5173 ...
start "EAIOS Frontend" /d "%~dp0frontend" cmd /k "npm run dev"

timeout /t 8 /nobreak >nul
start http://localhost:5173
echo.
echo  EAIOS is up. Keep the two server windows open.
echo  Login: admin@eaios.dev / admin12345  (or maya@eaios.dev / demo12345)
echo  If Ollama is running, the AI answers with your local llama3.1 automatically.
echo.
pause
