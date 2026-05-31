#!/bin/bash
# CEML Lab Orchestrator — Startup Script
# Usage: ./start.sh [start|stop|status]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$SCRIPT_DIR/.orchestrator.pid"
LOG_FILE="$LOG_DIR/orchestrator.log"

mkdir -p "$LOG_DIR"

# Conda activation
eval "$(conda shell.bash hook 2>/dev/null)"
conda activate lab-research-agents 2>/dev/null

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Orchestrator already running (PID $(cat "$PID_FILE"))"
        return 1
    fi

    echo "Starting CEML Orchestrator..."
    cd "$SCRIPT_DIR"
    nohup python3 -m api.server >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2

    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "✅ Orchestrator started (PID $(cat "$PID_FILE"))"
        echo "   API: http://localhost:8000"
        echo "   Log: $LOG_FILE"
    else
        echo "❌ Failed to start. Check $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            sleep 1
            kill -9 "$PID" 2>/dev/null
            echo "✅ Orchestrator stopped (PID $PID)"
        else
            echo "Process not running"
        fi
        rm -f "$PID_FILE"
    else
        # Fallback: kill by port
        lsof -ti :8000 2>/dev/null | xargs kill -9 2>/dev/null
        echo "✅ Port 8000 cleared"
    fi
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "✅ Running (PID $(cat "$PID_FILE"))"
        curl -s http://localhost:8000/health 2>/dev/null && echo ""
    else
        echo "❌ Not running"
    fi
}

case "${1:-start}" in
    start)  start ;;
    stop)   stop ;;
    status) status ;;
    restart) stop; sleep 1; start ;;
    *)      echo "Usage: $0 {start|stop|status|restart}" ;;
esac
