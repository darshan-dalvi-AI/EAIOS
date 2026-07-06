#!/usr/bin/env bash
# EAIOS one-click launcher — macOS / Linux
# First run: chmod +x start-eaios.sh && ./start-eaios.sh
set -e
cd "$(dirname "$0")"

echo "============================================"
echo " EAIOS - Enterprise AI Operating System"
echo " One-click launcher (macOS/Linux)"
echo "============================================"

echo "[1/4] Backend dependencies (first run takes 1-2 min)..."
cd backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

echo "[2/4] Starting backend on http://localhost:8000 ..."
python -m app.seed || true
nohup python -m uvicorn app.main:app --port 8000 > ../backend.log 2>&1 &
echo $! > ../.backend.pid
cd ..

echo "[3/4] Frontend dependencies (first run takes 1-3 min)..."
cd frontend
if [ ! -d node_modules ]; then
  npm install --no-audit --no-fund
fi

echo "[4/4] Starting frontend on http://localhost:5173 ..."
# --host makes it reachable from your phone (iPhone/Android) on the same Wi-Fi:
# open http://<this-computer's-IP>:5173 in the phone's browser.
nohup npm run dev -- --host > ../frontend.log 2>&1 &
echo $! > ../.frontend.pid
cd ..

sleep 6
if command -v open > /dev/null; then open http://localhost:5173; \
elif command -v xdg-open > /dev/null; then xdg-open http://localhost:5173; fi

echo ""
echo " EAIOS is up.  Logs: backend.log / frontend.log · Stop with ./stop-eaios.sh"
echo " Login: admin@eaios.dev / admin12345  (or maya@eaios.dev / demo12345)"
echo " If Ollama is running, the AI answers with your local model automatically."
