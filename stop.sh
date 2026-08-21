#!/usr/bin/env bash
# ==========================================================
#  🛑 Stop NEPSE AI Trading Bot & Free Port 8888
# ==========================================================

PID=$(lsof -ti:8888 2>/dev/null)
if [ -n "$PID" ]; then
    kill -9 $PID 2>/dev/null
    echo "✅ NEPSE Bot stopped successfully (freed port 8888, PID: $PID)."
else
    echo "ℹ️  No process found running on port 8888."
fi
