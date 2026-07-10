# Log Center — 架构设计文档

## 1. 系统概览

Log Center 是一套完整的日志采集、存储、搜索解决方案，分为 **Client SDK** 和 **Server** 两个组件：

```
┌─────────────────────────────────────────────────────────────┐
│                      应用层 (Applications)                    │
│                                                             │
│   FastAPI / Flask / Celery Worker / 任意 Python 应用          │
│                                                             │
│   ┌──────────────────────────────────────────────────────┐  │
│   │            log_center_sdk (Client)                   │  │
│   │                                                      │  │
│   │  configure() → JsonFormatter + TraceContextFilter    │  │
│   │  @instrumented → 结构化日志 (event/duration/status)   │  │
│   │                                                      │  │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────────┐       │  │
│   │  │ HTTP     │  │ gRPC     │  │ Celery       │       │  │
│   │  │ Handler  │  │ Handler  │  │ Handler      │       │  │
│   │  │ (异步批量)│  │ (异步批量)│  │ (异步批量)    │       │  │
│   │  └────┬─────┘  └────┬─────┘  └──────┬───────┘       │  │
│   └───────┼──────────────┼───────────────┼───────────────┘  │
└───────────┼──────────────┼───────────────┼──────────────────┘
            │ POST /ingest │ unary RPC     │ send_task
            ▼              ▼               ▼
┌───────────────────────────────────────────────────────────────┐
│                  log_center_server (Server)                    │
│                                                               │
│   ┌─────────────────────────────────────────────────────────┐ │
│   │              process_entries() 共享管道                   │ │
│   │                                                         │ │
│   │  normalize → write_file → init_sqlite → write_backend   │ │
│   │                                        → forward_entries│ │
│   └─────────────────────────────────────────────────────────┘ │
│                                                               │
│   ┌──────────┐  ┌─────────┐  ┌────────┐  ┌───────────────┐  │
│   │ Local    │  │ SQLite  │  │ MySQL  │  │ PostgreSQL/ES │  │
│   │ File     │  │ (默认)   │  │        │  │               │  │
│   │ (始终启用)│  │         │  │        │  │               │  │
│   └──────────┘  └─────────┘  └────────┘  └───────────────┘  │
│                                                               │
│   ┌──────────────┐  ┌──────────────┐                          │
│   │ Gradio UI    │  │ Log Forward  │                          │
│   │ (搜索界面)    │  │ (转发到其他   │                          │
│   │ :9317        │  │  log center) │                          │
│   └──────────────┘  └──────────────┘                          │
└───────────────────────────────────────────────────────────────┘
```

## 2. 包结构

```
ikc-log-center/
├── src/
│   ├── log_center_sdk/              # Client SDK
│   │   ├── __init__.py              # 公共 API 导出 (lazy import)
│   │   ├── core.py                  # Trace context (contextvars)
│   │   │                            #   JsonFormatter — JSON 结构化输出
│   │   │                            #   TraceContextFilter — 注入 trace_id/span_id/request_id
│   │   │                            #   configure() — 一键初始化 logging
│   │   │                            #   get_logger() — 获取 logger
│   │   ├── handlers.py              # _BaseAsyncBatchHandler — 异步批量基类
│   │   │                            #   HttpLogHandler — POST JSON batches
│   │   │                            #   GrpcLogHandler — gRPC unary JSON bytes
│   │   │                            #   CeleryLogHandler — send_task
│   │   │                            #   build_handlers_from_env() — 工厂函数
│   │   ├── instrumentation.py       # @instrumented — 装饰器 (sync/async)
│   │   │                            #   event, duration_ms, status, call_args
│   │   │                            #   log_args, redact_args, slow_threshold_ms
│   │   ├── celery_hooks.py          # patch_celery_app() — fork-safe reinit
│   │   └── integrations/
│   │       ├── fastapi.py           # TraceMiddleware — 提取/回传 trace headers
│   │       └── flask.py             # init_trace_hooks() — before/after_request
│   │
│   └── log_center_server/           # Server
│       ├── __init__.py              # 包声明 + __version__
│       ├── __main__.py              # CLI: python -m log_center_server
│       │                            #   --port, --host, --grpc, --ui, --reload
│       ├── app.py                   # FastAPI app + CORS
│       │                            #   POST /ingest — 接收日志
│       │                            #   GET  /health — 健康检查
│       │                            #   GET  /search — SQLite 查询
│       │                            #   process_entries() — 共享管道
│       ├── storage.py               # normalize_entries() — 规范化
│       │                            # write_file() — JSON-lines (500MB cap)
│       │                            # init_sqlite() / write_sqlite()
│       │                            # write_mysql() / write_pg() / write_es()
│       │                            # write_backend() — 分发
│       │                            # forward_entries() — 转发
│       ├── grpc_server.py           # serve_grpc() — generic JSON handler
│       │                            #   logcenter.LogService/Ingest
│       │                            #   logcenter.LogService/Health
│       ├── celery_task.py           # celery_app + log_center.ingest task
│       ├── query.py                 # LogEntry ORM model + query_logs()
│       └── ui.py                    # Gradio Blocks 搜索 UI
│
├── tests/                           # 测试套件
│   ├── test_core.py                 # SDK core 测试
│   ├── test_handlers.py             # SDK handlers 测试
│   ├── test_instrumentation.py      # SDK decorator 测试
│   ├── test_celery_hooks.py         # SDK celery hooks 测试
│   └── test_server/
│       ├── test_app.py              # Server endpoint 测试
│       ├── test_storage.py          # Storage backend 测试
│       └── test_query.py            # ORM query 测试
│
├── scripts/
│   └── publish-pypi.sh              # PyPI 发布脚本
├── config/
│   ├── pypi.env                     # PyPI 凭证 (gitignored)
│   └── pypi.env.example             # 凭证模板
├── start_log_center.sh              # Server 启动脚本
├── stop_log_center.sh               # Server 停止脚本
├── show_log_center.sh               # Server 状态脚本
├── pyproject.toml                   # 构建配置 (hatchling)
└── docs/
    └── design.md                    # 本文档
```

## 3. 环境变量配置参考

### 3.1 Client SDK 环境变量

Client SDK 的环境变量分为三类：**远程投递**、**本地日志**、**按模块覆盖**。

#### 3.1.1 远程投递

控制 SDK 如何将日志发送到 Log Center Server。

```bash
# ===== 必需 =====
LOG_CENTER_ENABLE=true              # 启用远程推送 (默认 false)

# ===== 投递模式 =====
LOG_CENTER_DELIVERY=api             # api | grpc | celery | 逗号组合 | both

# ===== HTTP 投递 (LOG_CENTER_DELIVERY=api) =====
LOG_CENTER_URL=http://log-center:9315   # Server HTTP 地址

# ===== gRPC 投递 (LOG_CENTER_DELIVERY=grpc) =====
LOG_CENTER_GRPC_ADDR=log-center:9316    # 完整 gRPC 地址
# 或者分别设置:
LOG_CENTER_GRPC_HOST=localhost          # gRPC host
LOG_CENTER_GRPC_PORT=9316               # gRPC port
LOG_CENTER_GRPC_INSECURE=true           # 使用 insecure channel

# ===== Celery 投递 (LOG_CENTER_DELIVERY=celery) =====
LOG_CENTER_CELERY_BROKER=redis://localhost:6379/0   # Broker URL
LOG_CENTER_CELERY_BACKEND=                          # Result backend (可选)
LOG_CENTER_CELERY_TASK=log_center.ingest             # Task name

# ===== 调优 =====
LOG_CENTER_TIMEOUT=2                  # 投递超时 (秒)
LOG_CENTER_QUEUE=1000                 # 内存队列大小
LOG_CENTER_BATCH=50                   # 批次大小
```

#### 3.1.2 本地日志

控制 SDK 的本地文件日志行为。

```bash
LOG_LEVEL=INFO                        # 日志级别
LOG_JSON=true                         # JSON 格式输出 (false=plain text)
LOG_FILE_PATH=logs/app.log            # 日志文件路径
LOG_FILE_ENABLE=true                  # 启用文件日志
LOG_FILE_MAX_MB=500                   # 单文件最大 MB
LOG_FILE_BACKUP=3                     # 轮转备份数
LOG_FILE_COMPRESS=true                # gzip 压缩轮转文件
LOG_FILE_RETENTION_DAYS=14            # 过期清理天数
```

#### 3.1.3 按模块覆盖

当多个服务共享同一 SDK 时，可通过 `{MODULE}` (大写 module_name) 实现细粒度控制：

```bash
# 示例: module_name="my_app" → MODULE="MY_APP"
LOG_CENTER_ENABLE_MY_APP=true         # 仅此模块推送
LOG_FILE_PATH_MY_APP=logs/my_app.log  # 独立日志文件
LOG_FILE_MAX_MB_MY_APP=200            # 独立大小限制
LOG_FILE_COMPRESS_MY_APP=false        # 此模块不压缩
LOG_FILE_RETENTION_DAYS_MY_APP=30     # 此模块保留 30 天
```

### 3.2 Server 环境变量

#### 3.2.1 核心配置

```bash
# ===== 端口 =====
LOG_CENTER_PORT=9315                  # HTTP API 端口
LOG_CENTER_HOST=0.0.0.0              # 绑定地址
LOG_CENTER_GRPC_PORT=9316             # gRPC 端口
LOG_CENTER_UI_PORT=9317               # Gradio UI 端口
LOG_CENTER_UI_HOST=0.0.0.0           # UI 绑定地址

# ===== 存储 =====
LOG_CENTER_FILE=logs/log_center.log   # 本地文件路径 (始终写入)
LOG_CENTER_DB_PATH=data/log_center/log_center.db  # SQLite 数据库
LOG_CENTER_STORE=local                # 主存储后端: local|sqlite|mysql|pg|es
LOG_CENTER_MAX_LOCAL_MB=500           # 本地文件上限 (MB)

# ===== 其他 =====
LOG_CENTER_CORS_ORIGINS=*             # CORS 来源 (逗号分隔)
LOG_CENTER_FORWARD_URLS=              # 转发目标 (逗号分隔 URL)
```

#### 3.2.2 MySQL 后端

```bash
LOG_CENTER_STORE=mysql
LOG_CENTER_MYSQL_HOST=10.0.0.1
LOG_CENTER_MYSQL_PORT=3306
LOG_CENTER_MYSQL_USER=logcenter
LOG_CENTER_MYSQL_PASSWORD=secret
LOG_CENTER_MYSQL_DB=log_center
```

#### 3.2.3 PostgreSQL 后端

```bash
LOG_CENTER_STORE=pg
LOG_CENTER_PG_HOST=10.0.0.1
LOG_CENTER_PG_PORT=5432
LOG_CENTER_PG_USER=logcenter
LOG_CENTER_PG_PASSWORD=secret
LOG_CENTER_PG_DB=log_center
```

#### 3.2.4 Elasticsearch 后端

```bash
LOG_CENTER_STORE=es
LOG_CENTER_ES_ENDPOINT=http://es-cluster:9200
LOG_CENTER_ES_INDEX=log-center
```

#### 3.2.5 Celery 异步接收

```bash
LOG_CENTER_CELERY_ENABLE=true         # 启用 Celery task
LOG_CENTER_CELERY_BROKER=redis://localhost:6379/0
LOG_CENTER_CELERY_BACKEND=redis://localhost:6379/1
# 或者通过 REDIS_URI_BASE 自动推导:
REDIS_URI_BASE=redis://10.0.0.1:6379
```

## 4. 典型部署场景

### 4.1 最小部署 (单机开发)

```bash
# Server 端
LOG_CENTER_STORE=local
python -m log_center_server --grpc --ui

# Client 端
LOG_CENTER_ENABLE=true
LOG_CENTER_DELIVERY=api
LOG_CENTER_URL=http://localhost:9315
```

### 4.2 Celery 异步部署 (生产推荐)

```bash
# Server 端
LOG_CENTER_STORE=local
LOG_CENTER_CELERY_ENABLE=true
LOG_CENTER_CELERY_BROKER=redis://redis-host:6379/0
python -m log_center_server

# Client 端
LOG_CENTER_ENABLE=true
LOG_CENTER_DELIVERY=celery
LOG_CENTER_CELERY_BROKER=redis://redis-host:6379/0
```

### 4.3 PostgreSQL + gRPC 部署 (高性能)

```bash
# Server 端
LOG_CENTER_STORE=pg
LOG_CENTER_PG_HOST=db-host
LOG_CENTER_PG_PORT=5432
LOG_CENTER_PG_USER=logcenter
LOG_CENTER_PG_PASSWORD=secret
LOG_CENTER_PG_DB=log_center
python -m log_center_server --grpc --ui

# Client 端
LOG_CENTER_ENABLE=true
LOG_CENTER_DELIVERY=grpc
LOG_CENTER_GRPC_ADDR=server-host:9316
```

### 4.4 多服务 Per-Module 控制

```bash
# Service A: 推送日志
LOG_CENTER_ENABLE=true
LOG_CENTER_ENABLE_SERVICE_A=true

# Service B: 不推送 (仅本地)
LOG_CENTER_ENABLE_SERVICE_B=false

# Service C: 独立日志文件 + 30 天保留
LOG_FILE_PATH_SERVICE_C=logs/service_c.log
LOG_FILE_RETENTION_DAYS_SERVICE_C=30
```

## 5. 数据流

### 5.1 日志写入流

```
SDK configure()
  │
  ├── ConsoleHandler (stdout)
  ├── RotatingFileHandler (本地文件, gzip, 过期清理)
  └── RemoteHandler (HTTP/gRPC/Celery, 异步批量)
       │
       ▼
  Server /ingest (or gRPC Ingest, or Celery task)
       │
       ├── normalize_entries()     注入 trace_id_hint
       ├── write_file()            JSON-lines 追加 (500MB 截断)
       ├── init_sqlite()           确保表存在
       ├── write_backend()         分发到 sqlite|mysql|pg|es
       └── forward_entries()       转发到其他 log center
```

### 5.2 日志查询流

```
GET /search?trace_id=X&level=Y&limit=N
  │
  └── SQLite query → JSON response

Gradio UI (port 9317)
  │
  └── query_logs() → SQLAlchemy → SQLite → JSON
```

## 6. 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 构建后端 | hatchling | 现代、快速、支持多包 wheel |
| 异步批量 | daemon thread + Queue | 简单可靠，不引入额外依赖 |
| gRPC | generic JSON bytes | 无需 protobuf 编译，与 HTTP payload 兼容 |
| Server 框架 | FastAPI | 原生 async，自带 OpenAPI 文档 |
| DB 查询 ORM | SQLAlchemy | 支持 SQLite 查询 + 未来扩展 |
| UI | Gradio | 零前端代码，快速搭建搜索界面 |
| 可选依赖 | extras + lazy import | 基础安装轻量，按需安装 |
| 日志文件 | 500MB 截断 | 简单可靠，与源项目保持一致 |
| 发布 | twine + PyPI token | 标准 Python 包发布流程 |

## 7. 发布到 PyPI

参见 [README Publishing 章节](../README.md#publishing-发布到-pypi)。

```bash
# 1. 配置凭证
cp config/pypi.env.example config/pypi.env
# 编辑 config/pypi.env

# 2. 发布
./scripts/publish-pypi.sh

# 3. 安装
pip install log-center-sdk[server]
```
