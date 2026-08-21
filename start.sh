#!/usr/bin/env bash
# ==========================================================
#  🇳🇵 NEPSE AI Trading Bot & Dashboard — Local Launcher
# ==========================================================

# Resolve project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR" || exit 1

echo "=========================================================="
echo " 🇳🇵 Starting NEPSE AI Trading Bot (Kronos AI + Real TMS)"
echo "=========================================================="

# 1. Locate Python 3.11 or Python 3
PYTHON_BIN=""
if [ -x "/opt/homebrew/bin/python3.11" ]; then
    PYTHON_BIN="/opt/homebrew/bin/python3.11"
elif [ -x "/usr/local/bin/python3.11" ]; then
    PYTHON_BIN="/usr/local/bin/python3.11"
elif command -v python3.11 &>/dev/null; then
    PYTHON_BIN="$(command -v python3.11)"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "❌ Error: Python 3 could not be found. Please install Python 3.11."
    exit 1
fi

echo "✅ Using Python: $PYTHON_BIN ($($PYTHON_BIN --version))"

# 2. Check and start MySQL service if brew is installed
if command -v brew &>/dev/null; then
    if brew services list 2>/dev/null | grep -q "mysql"; then
        MYSQL_STATUS=$(brew services list 2>/dev/null | grep mysql | awk '{print $2}')
        if [ "$MYSQL_STATUS" != "started" ]; then
            echo "⚡ Starting MySQL database service..."
            brew services start mysql >/dev/null 2>&1
        else
            echo "✅ MySQL Service is running"
        fi
    fi
fi

# 3. Kill any existing process on port 8888 to prevent port conflict
OLD_PID=$(lsof -ti:8888 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    echo "🔄 Freeing port 8888 (killing PID $OLD_PID)..."
    kill -9 $OLD_PID 2>/dev/null
    sleep 1
fi

# 4. Open dashboard in default browser in background after 2 seconds
(
    sleep 2
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open "http://localhost:8888"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        xdg-open "http://localhost:8888" 2>/dev/null || sensible-browser "http://localhost:8888" 2>/dev/null
    fi
) &

echo "🚀 Starting Flask Server on http://localhost:8888 ..."
echo "🌐 Press Ctrl+C anytime to stop the server."
echo "=========================================================="

# 5. Launch the application
exec "$PYTHON_BIN" nepse_bot/run.py
