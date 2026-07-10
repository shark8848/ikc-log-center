#!/usr/bin/env bash
# ============================================================================
# Start log center server (HTTP + optional gRPC + optional UI)
# ============================================================================
#
# Usage:
#   ./start_log_center.sh [OPTIONS]
#
# Options:
#   --ui                   Enable Gradio search UI (port 9317)
#   --grpc                 Enable gRPC ingestion server (port 9316)
#   --reload               Enable auto-reload (development mode)
#   --gen-token [DESC]     Generate a new API token (then exit)
#   --list-tokens          List all API tokens (then exit)
#   --revoke-token PREFIX  Revoke a token by prefix (then exit)
#   -h, --help             Show this help message
#
# Examples:
#
#   # 1. 基础启动（仅 HTTP API，SQLite 存储）
#   ./start_log_center.sh
#
#   # 2. 启动 HTTP API + Gradio 搜索 UI
#   ./start_log_center.sh --ui
#
#   # 3. 全功能启动（HTTP + gRPC + UI）
#   ./start_log_center.sh --ui --grpc
#
#   # 4. 开发模式（自动重载 + UI）
#   ./start_log_center.sh --ui --reload
#
#   # 5. 自定义端口
#   LOG_CENTER_PORT=8080 ./start_log_center.sh --ui
#
#   # 6. 使用 PostgreSQL 存储
#   LOG_CENTER_STORE=pg \
#   LOG_CENTER_PG_HOST=localhost \
#   LOG_CENTER_PG_PORT=5432 \
#   LOG_CENTER_PG_USER=postgres \
#   LOG_CENTER_PG_PASSWORD=secret \
#   LOG_CENTER_PG_DB=log_center \
#   ./start_log_center.sh --ui
#
#   # 7. 使用 MySQL 存储
#   LOG_CENTER_STORE=mysql \
#   LOG_CENTER_MYSQL_HOST=localhost \
#   LOG_CENTER_MYSQL_USER=root \
#   LOG_CENTER_MYSQL_PASSWORD=secret \
#   LOG_CENTER_MYSQL_DB=log_center \
#   ./start_log_center.sh --ui
#
#   # 8. 使用 Elasticsearch 存储
#   LOG_CENTER_STORE=es \
#   LOG_CENTER_ES_ENDPOINT=http://localhost:9200 \
#   ./start_log_center.sh --ui
#
#   # 9. 转发日志到另一个 log-center 实例
#   LOG_CENTER_FORWARD_URLS=http://remote-host:9315 \
#   ./start_log_center.sh
#
#   # 10. 组合：PG 存储 + 转发 + gRPC + UI
#   LOG_CENTER_STORE=pg \
#   LOG_CENTER_PG_HOST=localhost \
#   LOG_CENTER_PG_USER=postgres \
#   LOG_CENTER_PG_DB=log_center \
#   LOG_CENTER_FORWARD_URLS=http://backup-server:9315 \
#   ./start_log_center.sh --ui --grpc
#
#   # 11. 生成 API Token（存储到当前后端）
#   LOG_CENTER_STORE=pg \
#   LOG_CENTER_PG_HOST=localhost LOG_CENTER_PG_USER=postgres LOG_CENTER_PG_DB=log_center \
#   .venv/bin/python -m log_center_server --gen-token "production server"
#
#   # 12. 启用 Token 鉴权启动服务器
#   LOG_CENTER_AUTH_ENABLED=true \
#   ./start_log_center.sh --ui
#
#   # 13. Client SDK 使用 Token 上发日志
#   LOG_CENTER_ENABLE=true \
#   LOG_CENTER_URL=http://server:9315 \
#   LOG_CENTER_TOKEN=sk-lc-xxxxx \
#   python my_app.py
#
# Environment Variables:
#   LOG_CENTER_PORT            HTTP API port (default: 9315)
#   LOG_CENTER_STORE           Storage backend: local|sqlite|mysql|pg|es (default: local)
#   LOG_CENTER_FILE            Local file path (default: logs/log_center.log)
#   LOG_CENTER_DB_PATH         SQLite DB path (default: data/log_center/log_center.db)
#   LOG_CENTER_MAX_LOCAL_MB    Max local file size in MB (default: 500)
#   LOG_CENTER_FORWARD_URLS    Comma-separated forward URLs
#   LOG_CENTER_UI_ENABLE       Set true/1 to enable UI (alt to --ui flag)
#   LOG_CENTER_GRPC_ENABLE     Set true/1 to enable gRPC (alt to --grpc flag)
#   LOG_CENTER_UI_PORT         Gradio UI port (default: 9317)
#   LOG_CENTER_GRPC_PORT       gRPC port (default: 9316)
#   LOG_CENTER_PG_*            PostgreSQL connection params
#   LOG_CENTER_MYSQL_*         MySQL connection params
#   LOG_CENTER_ES_ENDPOINT     Elasticsearch endpoint URL
#   LOG_CENTER_ES_INDEX        Elasticsearch index name (default: log-center)
#   LOG_CENTER_AUTH_ENABLED    Enable Bearer Token auth: true|false (default: false)
#   LOG_CENTER_TOKEN           Client SDK token (set on client side)
#
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$SCRIPT_DIR/.run/log_center.pid"
LOGFILE="$SCRIPT_DIR/logs/log_center_stdout.log"

# ---------------------------------------------------------------------------
# Handle --help
# ---------------------------------------------------------------------------
for arg in "$@"; do
    if [ "$arg" = "-h" ] || [ "$arg" = "--help" ]; then
        awk '/^# =/{n++; next} n==2' "$0" | sed 's/^# \?//'
        exit 0
    fi
done

mkdir -p "$SCRIPT_DIR/.run" "$SCRIPT_DIR/logs"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Log center already running (PID $(cat "$PIDFILE"))"
    exit 1
fi

# ---------------------------------------------------------------------------
# Resolve Python interpreter
# Priority: .venv/bin/python > $VIRTUAL_ENV/bin/python > system python
# ---------------------------------------------------------------------------
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
    PYTHON="$VIRTUAL_ENV/bin/python"
else
    PYTHON="python"
fi

# Verify the package is importable
if ! "$PYTHON" -c "import log_center_server" 2>/dev/null; then
    echo "ERROR: log_center_server not found in $PYTHON"
    echo "Install it first:"
    echo "  $PYTHON -m pip install -e \"$SCRIPT_DIR[server]\""
    exit 1
fi

# ---------------------------------------------------------------------------
# Build CLI args
# ---------------------------------------------------------------------------
ARGS=""

# Support both env vars and CLI flags: --ui, --grpc, --reload
for arg in "$@"; do
    case "$arg" in
        --ui|--grpc|--reload) ARGS="$ARGS $arg" ;;
        --gen-token|--list-tokens) 
            # Token management: run directly and exit
            "$PYTHON" -m log_center_server "$@"
            exit $?
            ;;
        --revoke-token)
            "$PYTHON" -m log_center_server "$@"
            exit $?
            ;;
        *) echo "WARNING: Unknown argument '$arg' (ignored)" ;;
    esac
done

if [ "${LOG_CENTER_GRPC_ENABLE}" = "true" ] || [ "${LOG_CENTER_GRPC_ENABLE}" = "1" ]; then
    ARGS="$ARGS --grpc"
fi
if [ "${LOG_CENTER_UI_ENABLE}" = "true" ] || [ "${LOG_CENTER_UI_ENABLE}" = "1" ]; then
    ARGS="$ARGS --ui"
fi

PORT="${LOG_CENTER_PORT:-9315}"

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
nohup "$PYTHON" -m log_center_server --port "$PORT" $ARGS \
    >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

sleep 0.5
if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "ERROR: Server failed to start. Check logs:"
    echo "  tail -20 $LOGFILE"
    rm -f "$PIDFILE"
    exit 1
fi

echo "Log center started (PID $(cat "$PIDFILE"))"
echo "  HTTP:  http://localhost:${PORT}"
echo "  gRPC:  localhost:${LOG_CENTER_GRPC_PORT:-9316}"
echo "  UI:    http://localhost:${LOG_CENTER_UI_PORT:-9317}"
