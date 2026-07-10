#!/usr/bin/env bash
# Show log center status
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$SCRIPT_DIR/.run/log_center.pid"
PORT="${LOG_CENTER_PORT:-9315}"

echo "=== Log Center Status ==="
echo ""

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Status: RUNNING (PID $(cat "$PIDFILE"))"
else
    echo "Status: STOPPED"
fi

echo ""
echo "HTTP API:  http://localhost:${PORT}"
echo "gRPC:      localhost:${LOG_CENTER_GRPC_PORT:-9316}"
echo "UI:        http://localhost:${LOG_CENTER_UI_PORT:-9317}"
echo ""

# Health check
echo "--- Health Check ---"
curl -s "http://localhost:${PORT}/health" 2>/dev/null || echo "(unreachable)"
echo ""

# Recent logs
echo ""
echo "--- Recent Logs ---"
tail -20 "$SCRIPT_DIR/logs/log_center_stdout.log" 2>/dev/null || echo "(no log file)"
