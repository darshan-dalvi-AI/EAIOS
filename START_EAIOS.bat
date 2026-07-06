@echo off
title EAIOS Launcher
echo ============================================
echo   EAIOS - Enterprise AI Operating System
echo ============================================
echo Starting backend (FastAPI + Ollama auto-detect)...
start "EAIOS Backend" /d "%~dp0backend" cmd /k "python -m pip install -r requirements.txt && python -m app.seed && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo Starting frontend (Vite dev server)...
start "EAIOS Frontend" /d "%~dp0frontend" cmd /k "npm install && npm run dev"
echo.
echo Two windows are booting. When the frontend window shows
echo "Local: http://localhost:5173" open that address in Chrome.
echo Login: admin@eaios.dev / admin12345
timeout /t 8 >nul
exit
