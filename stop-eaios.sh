#!/usr/bin/env bash
# Stop EAIOS servers — macOS / Linux
cd "$(dirname "$0")"
for pidfile in .backend.pid .frontend.pid; do
  if [ -f "$pidfile" ]; then
    kill "$(cat "$pidfile")" 2>/dev/null || true
    rm -f "$pidfile"
  fi
done
pkill -f "uvicorn app.main:app" 2>/dev/null || true
echo "EAIOS servers stopped."
