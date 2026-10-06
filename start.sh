#!/usr/bin/env bash
# ==============================================================================
# BillDesk Native - Application Startup Script (Bash)
#
# Checks and starts dependencies before launching: python main.py
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "         BillDesk Native Mandi POS & ERP Launcher           "
echo "============================================================"

# 1. Determine Python executable
if command -v python.exe &> /dev/null; then
    PY_CMD="python.exe"
elif command -v python &> /dev/null; then
    PY_CMD="python"
elif command -v python3 &> /dev/null; then
    PY_CMD="python3"
else
    echo "[ERR] Python was not found in PATH! Please install Python 3.10+."
    exit 1
fi

PY_VER=$($PY_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null || echo "Unknown")
echo "[OK] Found Python $PY_VER ($PY_CMD)"

# 2. Check Python packages
echo "[INFO] Checking Python dependencies..."
if ! $PY_CMD -c "import pymongo, pydantic, dotenv, bcrypt, reportlab, pymupdf, certifi" 2>/dev/null; then
    echo "[WARN] Missing Python packages. Installing requirements..."
    $PY_CMD -m pip install -r requirements.txt
    echo "[OK] Python dependencies installed."
else
    echo "[OK] Python dependencies verified."
fi

# 3. Check MongoDB Dependency (Port 27018)
MONGO_PORT=27018
MONGO_HOST="127.0.0.1"

# Read .env if present
if [ -f .env ]; then
    ENV_URL=$(grep -E '^MONGODB_URL=' .env | cut -d '=' -f2- | tr -d ' "\r')
    if [[ "$ENV_URL" =~ ://([^:/]+):([0-9]+) ]]; then
        MONGO_HOST="${BASH_REMATCH[1]}"
        MONGO_PORT="${BASH_REMATCH[2]}"
    fi
fi

echo "[INFO] Checking MongoDB on $MONGO_HOST:$MONGO_PORT..."

is_port_open() {
    $PY_CMD -c "import socket, sys; s = socket.socket(); s.settimeout(1); res = s.connect_ex(('$MONGO_HOST', int('$MONGO_PORT'))); sys.exit(0 if res == 0 else 1)" 2>/dev/null
}

if is_port_open; then
    echo "[OK] MongoDB is already running on $MONGO_HOST:$MONGO_PORT."
else
    echo "[WARN] MongoDB is not running on $MONGO_HOST:$MONGO_PORT. Starting MongoDB dependency..."

    DATA_DIR="$APPDATA/BillDesk/db"
    LOG_DIR="$APPDATA/BillDesk/logs"
    if [ -z "$APPDATA" ]; then
        DATA_DIR="$HOME/.billdesk/db"
        LOG_DIR="$HOME/.billdesk/logs"
    fi
    mkdir -p "$DATA_DIR" "$LOG_DIR"

    MONGOD_EXE=""
    if [ -f "resources/mongo/win32-x64/mongod.exe" ]; then
        MONGOD_EXE="resources/mongo/win32-x64/mongod.exe"
    elif command -v mongod &> /dev/null; then
        MONGOD_EXE="mongod"
    fi

    if [ -z "$MONGOD_EXE" ]; then
        echo "[ERR] mongod binary not found! Please ensure resources/mongo/win32-x64/mongod.exe exists."
        exit 1
    fi

    echo "[INFO] Launching MongoDB ($MONGOD_EXE)..."
    "$MONGOD_EXE" --dbpath "$DATA_DIR" --bind_ip "$MONGO_HOST" --port "$MONGO_PORT" --logpath "$LOG_DIR/mongod.log" --logappend --wiredTigerCacheSizeGB 0.5 &
    
    echo "[INFO] Waiting for MongoDB to become ready..."
    READY=0
    for i in {1..30}; do
        sleep 0.5
        if is_port_open; then
            READY=1
            break
        fi
    done

    if [ $READY -eq 0 ]; then
        echo "[ERR] MongoDB failed to start on $MONGO_HOST:$MONGO_PORT within 15 seconds."
        exit 1
    fi
    echo "[OK] MongoDB is running."
fi

# 4. Start Application
if [ "$1" = "--check-only" ] || [ "$1" = "-CheckOnly" ]; then
    echo "[OK] All dependencies verified and ready! (CheckOnly mode)"
    exit 0
fi

echo "------------------------------------------------------------"
echo "[INFO] Starting application: $PY_CMD main.py"
echo "------------------------------------------------------------"
exec $PY_CMD main.py "$@"
