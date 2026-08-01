#!/usr/bin/env bash
# Stop K-OS servers — macOS / Linux
cd "$(dirname "$0")"
for pidfile in .backend.pid .frontend.pid; do
  if [ -f "$pidfile" ]; then
    kill "$(cat "$pidfile")" 2>/dev/null || true
    rm -f "$pidfile"
  fi
done
pkill -f "uvicorn app.main:app" 2>/dev/null || true
echo "K-OS servers stopped."
