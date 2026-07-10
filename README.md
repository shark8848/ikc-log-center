# Log Center SDK + Server

轻量级日志 SDK 与中心化日志服务。SDK 通过装饰器自动采集结构化日志，支持 HTTP/gRPC/Celery 三种投递方式；Server 接收、存储、搜索日志，支持 SQLite/MySQL/PostgreSQL/Elasticsearch 多种存储后端。

```
应用 (SDK) ──HTTP/gRPC/Celery──▶ Log Center Server ──▶ SQLite / MySQL / PG / ES
```

## Install

```bash
# Client SDK only
pip install ikc-log-center                        # HTTP delivery (default)
pip install ikc-log-center[grpc]                  # + gRPC delivery
pip install ikc-log-center[celery]                # + Celery delivery
pip install ikc-log-center[fastapi]               # + FastAPI middleware
pip install ikc-log-center[flask]                 # + Flask hooks

# Server
pip install ikc-log-center[server]                # HTTP server + SQLite
pip install ikc-log-center[server,ui]             # + Gradio search UI
pip install ikc-log-center[server,mysql]          # + MySQL backend
pip install ikc-log-center[server,pg]             # + PostgreSQL backend

# Everything
pip install ikc-log-center[all]
```

---

## Client SDK

### Quick Start

```python
from log_center_sdk import configure, instrumented

configure(module_name="my_app")

@instrumented("process_order", slow_threshold_ms=500)
def process_order(order_id: str, amount: float):
    ...

@instrumented("llm_call", log_args={"model"}, redact_args={"api_key"})
async def call_llm(prompt: str, model: str, api_key: str):
    ...
```

### Delivery Modes

| Mode | Protocol | Port | Best For |
|------|----------|------|----------|
| `api` | HTTP POST JSON | 9315 | Cross-network, external apps |
| `grpc` | gRPC unary JSON bytes | 9316 | Low-latency internal network |
| `celery` | Redis queue + send_task | 6379 | Apps with existing Celery |

Combine: `LOG_CENTER_DELIVERY=grpc,api`

### Framework Integrations

**FastAPI:**
```python
from log_center_sdk.integrations.fastapi import TraceMiddleware
app.add_middleware(TraceMiddleware)
```

**Flask:**
```python
from log_center_sdk.integrations.flask import init_trace_hooks
init_trace_hooks(app)
```

**Celery Workers:**
```python
from log_center_sdk import patch_celery_app
patch_celery_app(app)  # auto-reinit handlers after fork
```

### Client Environment Variables

#### Remote Delivery (推送到 Log Center Server)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_CENTER_ENABLE` | `false` | 启用远程日志推送 |
| `LOG_CENTER_DELIVERY` | `api` | 投递模式: `api` / `grpc` / `celery` / 逗号组合 / `both` |
| `LOG_CENTER_URL` | — | HTTP 投递地址 (e.g. `http://log-center:9315`) |
| `LOG_CENTER_GRPC_ADDR` | — | gRPC 地址 (e.g. `log-center:9316`) |
| `LOG_CENTER_GRPC_HOST` | `localhost` | gRPC host (当 `LOG_CENTER_GRPC_ADDR` 未设时使用) |
| `LOG_CENTER_GRPC_PORT` | `9316` | gRPC port |
| `LOG_CENTER_GRPC_INSECURE` | `true` | gRPC 使用 insecure channel |
| `LOG_CENTER_CELERY_BROKER` | `redis://localhost:6379/0` | Celery broker URL |
| `LOG_CENTER_CELERY_BACKEND` | — | Celery result backend |
| `LOG_CENTER_CELERY_TASK` | `log_center.ingest` | Celery task name |
| `LOG_CENTER_TIMEOUT` | `2` | 投递超时 (秒) |
| `LOG_CENTER_QUEUE` | `1000` | 内存队列大小 |
| `LOG_CENTER_BATCH` | `50` | 批次大小 |
| `LOG_CENTER_TOKEN` | — | Bearer Token（服务端启用鉴权时必填） |

#### Local Logging (本地日志)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_JSON` | `true` | JSON 格式输出 |
| `LOG_FILE_PATH` | `logs/{module_name}.log` | 日志文件路径 |
| `LOG_FILE_ENABLE` | `true` | 启用文件日志 |
| `LOG_FILE_MAX_MB` | `500` | 单文件最大 MB |
| `LOG_FILE_BACKUP` | `3` | 轮转备份数 |
| `LOG_FILE_COMPRESS` | `true` | gzip 压缩轮转文件 |
| `LOG_FILE_RETENTION_DAYS` | `14` | 过期清理天数 |

#### Per-Module Overrides (按模块覆盖)

将 `{MODULE}` 替换为 `module_name` 的大写形式 (e.g. `my_app` → `MY_APP`)：

| Variable | Overrides |
|----------|-----------|
| `LOG_CENTER_ENABLE_{MODULE}` | `LOG_CENTER_ENABLE` |
| `LOG_FILE_PATH_{MODULE}` | `LOG_FILE_PATH` |
| `LOG_FILE_ENABLE_{MODULE}` | `LOG_FILE_ENABLE` |
| `LOG_FILE_MAX_MB_{MODULE}` | `LOG_FILE_MAX_MB` |
| `LOG_FILE_BACKUP_{MODULE}` | `LOG_FILE_BACKUP` |
| `LOG_FILE_COMPRESS_{MODULE}` | `LOG_FILE_COMPRESS` |
| `LOG_FILE_RETENTION_DAYS_{MODULE}` | `LOG_FILE_RETENTION_DAYS` |

---

## Server

### Quick Start

```bash
# Start HTTP API server (port 9315, SQLite storage)
python -m log_center_server

# With gRPC (9316) and Gradio UI (9317)
python -m log_center_server --grpc --ui

# Or use shell scripts
./start_log_center.sh
./show_log_center.sh
./stop_log_center.sh
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ingest` | POST | 接收单条或数组 JSON 日志 |
| `/health` | GET | 健康检查（免鉴权） |
| `/search` | GET | 按 `trace_id` / `level` / `message_substr` / `limit` 查询 |
| `/docs` | GET | OpenAPI 文档（免鉴权） |

### Authentication (Token 鉴权)

类似 OpenAI 的 Bearer Token 鉴权模式。Token 格式为 `sk-lc-<48 hex chars>`，存储为 SHA-256 哈希，明文仅在生成时显示一次。

Token 存储跟随 `LOG_CENTER_STORE` 后端：
- SQLite / PostgreSQL / MySQL → `api_tokens` 表
- Elasticsearch → 专用索引 `log_center_tokens`（写入时 `refresh=true` 确保即时可见）

#### 启用鉴权

```bash
# 1. 生成 Token（存储到当前后端）
LOG_CENTER_STORE=pg \
LOG_CENTER_PG_HOST=localhost LOG_CENTER_PG_USER=postgres LOG_CENTER_PG_DB=log_center \
python -m log_center_server --gen-token "production server"

# 2. 启动带鉴权的服务器
LOG_CENTER_AUTH_ENABLED=true \
python -m log_center_server --ui

# 3. Client SDK 携带 Token
LOG_CENTER_ENABLE=true \
LOG_CENTER_URL=http://server:9315 \
LOG_CENTER_TOKEN=sk-lc-xxxxx \
python my_app.py
```

#### Token 管理 CLI

```bash
# 生成新 Token
python -m log_center_server --gen-token "description"

# 列出所有 Token
python -m log_center_server --list-tokens

# 吊销 Token（按前缀匹配）
python -m log_center_server --revoke-token "sk-lc-a1b2"
```

#### 请求示例

```bash
# 带 Token 的请求
curl -H "Authorization: Bearer sk-lc-xxxxx" \
  http://localhost:9315/search?trace_id=abc123

# 无 Token 时返回 401
curl http://localhost:9315/ingest -X POST -d '{"level":"INFO"}'
# → {"status":"error","reason":"unauthorized"}
```

> `/health`、`/docs`、`/openapi.json` 始终免鉴权。

### Storage Backends

| Backend | `LOG_CENTER_STORE` | Extra |
|---------|-------------------|-------|
| Local file + SQLite | `local` (default) | — |
| MySQL | `mysql` | `[mysql]` |
| PostgreSQL | `pg` | `[pg]` |
| Elasticsearch | `es` | — |

> Local file logging is **always active** regardless of backend choice.

### Server Environment Variables

#### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_CENTER_PORT` | `9315` | HTTP API 端口 |
| `LOG_CENTER_HOST` | `0.0.0.0` | 绑定地址 |
| `LOG_CENTER_GRPC_PORT` | `9316` | gRPC 端口 |
| `LOG_CENTER_UI_PORT` | `9317` | Gradio UI 端口 |
| `LOG_CENTER_UI_HOST` | `0.0.0.0` | UI 绑定地址 |
| `LOG_CENTER_FILE` | `logs/log_center.log` | 本地文件日志路径 |
| `LOG_CENTER_DB_PATH` | `data/log_center/log_center.db` | SQLite 数据库路径 |
| `LOG_CENTER_STORE` | `local` | 存储后端: `local` / `sqlite` / `mysql` / `pg` / `es` |
| `LOG_CENTER_MAX_LOCAL_MB` | `500` | 本地文件上限 (MB)，超限自动截断 |
| `LOG_CENTER_CORS_ORIGINS` | `*` | CORS 允许的来源 (逗号分隔) |
| `LOG_CENTER_FORWARD_URLS` | — | 转发目标 URL (逗号分隔) |

#### MySQL (`LOG_CENTER_STORE=mysql`)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_CENTER_MYSQL_HOST` | — | MySQL 主机 |
| `LOG_CENTER_MYSQL_PORT` | `3306` | MySQL 端口 |
| `LOG_CENTER_MYSQL_USER` | — | 用户名 |
| `LOG_CENTER_MYSQL_PASSWORD` | — | 密码 |
| `LOG_CENTER_MYSQL_DB` | — | 数据库名 |

#### PostgreSQL (`LOG_CENTER_STORE=pg`)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_CENTER_PG_HOST` | — | PostgreSQL 主机 |
| `LOG_CENTER_PG_PORT` | `5432` | 端口 |
| `LOG_CENTER_PG_USER` | — | 用户名 |
| `LOG_CENTER_PG_PASSWORD` | — | 密码 |
| `LOG_CENTER_PG_DB` | — | 数据库名 |

#### Elasticsearch (`LOG_CENTER_STORE=es`)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_CENTER_ES_ENDPOINT` | — | ES endpoint URL |
| `LOG_CENTER_ES_INDEX` | `log-center` | ES index 名称 |
| `LOG_CENTER_ES_USER` | — | ES 用户名 |
| `LOG_CENTER_ES_PASSWORD` | — | ES 密码 |
| `LOG_CENTER_ES_VERIFY_SSL` | `true` | 是否验证 SSL 证书 |

#### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_CENTER_AUTH_ENABLED` | `false` | 启用 Bearer Token 鉴权 |
| `LOG_CENTER_TOKEN` | — | Client SDK 携带的 Token（客户端设置） |

#### Celery (Server 端异步接收)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_CENTER_CELERY_ENABLE` | `false` | 启用 Celery 异步接收 |
| `LOG_CENTER_CELERY_BROKER` | `redis://localhost:6379/0` | Broker URL |
| `LOG_CENTER_CELERY_BACKEND` | `redis://localhost:6379/1` | Result backend |
| `REDIS_URI_BASE` | — | Redis 基础 URL (自动推导 broker/backend) |

---

## Publishing (发布到 PyPI)

### 前置准备

1. 复制凭证模板并填入 PyPI token：
```bash
cp config/pypi.env.example config/pypi.env
# 编辑 config/pypi.env，填入你的 PyPI API token
```

2. 确保 `.gitignore` 已排除 `config/pypi.env`（已配置）。

### 发布流程

```bash
# 完整发布：build + upload
./scripts/publish-pypi.sh

# 指定版本号
LOG_CENTER_VERSION=0.2.0 ./scripts/publish-pypi.sh

# 发布到 TestPyPI (测试)
./scripts/publish-pypi.sh --test

# 跳过构建 (复用已有 dist/)
./scripts/publish-pypi.sh --skip-build
```

### 版本管理

版本号通过以下方式控制（优先级从高到低）：
1. 环境变量 `LOG_CENTER_VERSION`
2. `pyproject.toml` 中的 `version` 字段

---

## Project Structure

```
ikc-log-center/
├── src/
│   ├── log_center_sdk/           # Client SDK
│   │   ├── __init__.py           # Public API exports
│   │   ├── core.py               # Trace context, JSON formatter, configure()
│   │   ├── handlers.py           # HTTP/gRPC/Celery batch handlers
│   │   ├── instrumentation.py    # @instrumented decorator
│   │   ├── celery_hooks.py       # Fork-safety hooks
│   │   └── integrations/
│   │       ├── fastapi.py        # Trace middleware
│   │       └── flask.py          # Trace hooks
│   └── log_center_server/        # Server
│       ├── __init__.py
│       ├── __main__.py           # CLI entry point + token management
│       ├── app.py                # FastAPI endpoints + auth middleware
│       ├── auth.py               # Token generation / verification / storage
│       ├── storage.py            # Storage backends
│       ├── grpc_server.py        # gRPC service
│       ├── celery_task.py        # Celery task
│       ├── query.py              # SQLAlchemy ORM + multi-backend query
│       └── ui.py                 # Gradio search UI
├── tests/                        # Test suite
├── scripts/
│   └── publish-pypi.sh           # PyPI publish script
├── config/
│   ├── pypi.env                  # PyPI credentials (gitignored)
│   └── pypi.env.example          # Template
├── docs/
│   └── design.md                 # Architecture design document
├── start_log_center.sh           # Server start script
├── stop_log_center.sh            # Server stop script
├── show_log_center.sh            # Server status script
└── pyproject.toml                # Build configuration
```

## License

MIT
