#!/usr/bin/env bash
# Stop log center server
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$SCRIPT_DIR/.run/log_center.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "No PID file found — is log center running?"
    exit 1
fi

PID=$(cat "$PIDFILE")
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    wait "$PID" 2>/dev/null || true
    echo "Log center stopped (PID $PID)"
else
    echo "Process $PID not running (stale PID file)"
fi
rm -f "$PIDFILE"
