# Log Center SDK

Lightweight, decorator-based instrumentation SDK for [log_center](https://github.com/your-org/log-center).

Zero heavy dependencies. Supports **HTTP**, **gRPC**, and **Celery** delivery.

## Install

```bash
pip install log-center-sdk              # HTTP delivery (default)
pip install log-center-sdk[grpc]        # + gRPC delivery
pip install log-center-sdk[celery]      # + Celery delivery
pip install log-center-sdk[all]         # all delivery modes + framework integrations
```

## Quick Start

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

Set environment variables:

```bash
export LOG_CENTER_ENABLE=true
export LOG_CENTER_URL=http://log-center:9315      # HTTP delivery
# or
export LOG_CENTER_DELIVERY=grpc
export LOG_CENTER_GRPC_ADDR=log-center:9316        # gRPC delivery
# or
export LOG_CENTER_DELIVERY=celery
export LOG_CENTER_CELERY_BROKER=redis://localhost:6379/0  # Celery delivery
```

## Delivery Modes

| Mode | Protocol | Port | Best For |
|------|----------|------|----------|
| `api` | HTTP POST JSON | 9315 | Cross-network, external apps |
| `grpc` | gRPC unary JSON bytes | 9316 | Low-latency internal network |
| `celery` | Redis queue + send_task | 6379 | Apps with existing Celery |

Combine modes: `LOG_CENTER_DELIVERY=grpc,api`

## Framework Integrations

### FastAPI

```python
from fastapi import FastAPI
from log_center_sdk import configure
from log_center_sdk.integrations.fastapi import TraceMiddleware

app = FastAPI()
app.add_middleware(TraceMiddleware)
configure(module_name="my_api")
```

### Flask

```python
from flask import Flask
from log_center_sdk import configure
from log_center_sdk.integrations.flask import init_trace_hooks

app = Flask(__name__)
init_trace_hooks(app)
configure(module_name="my_flask")
```

### Celery Workers

```python
from celery import Celery
from log_center_sdk import configure, patch_celery_app

app = Celery("my_worker")
configure(module_name="my_worker")
patch_celery_app(app)  # auto-reinit handlers after fork
```

## Environment Variables

```bash
# Required
LOG_CENTER_ENABLE=true

# Delivery mode (api | grpc | celery | comma-separated combo | both)
LOG_CENTER_DELIVERY=api

# HTTP delivery
LOG_CENTER_URL=http://log-center:9315

# gRPC delivery
LOG_CENTER_GRPC_ADDR=log-center:9316
LOG_CENTER_GRPC_INSECURE=true

# Celery delivery
LOG_CENTER_CELERY_BROKER=redis://localhost:6379/0
LOG_CENTER_CELERY_TASK=log_center.ingest

# Tuning
LOG_CENTER_TIMEOUT=2
LOG_CENTER_QUEUE=1000
LOG_CENTER_BATCH=50

# Local logging
LOG_LEVEL=INFO
LOG_JSON=true
LOG_FILE_PATH=logs/app.log
LOG_FILE_ENABLE=true
LOG_FILE_MAX_MB=500
LOG_FILE_BACKUP=3
LOG_FILE_COMPRESS=true
LOG_FILE_RETENTION_DAYS=14

# Per-module overrides (replace {MODULE} with uppercased module_name)
LOG_CENTER_ENABLE_{MODULE}=true          # override remote push per module
LOG_FILE_PATH_{MODULE}=logs/myapp.log    # override log file path per module
LOG_FILE_MAX_MB_{MODULE}=200             # override max file size per module
LOG_FILE_BACKUP_{MODULE}=5               # override backup count per module
LOG_FILE_COMPRESS_{MODULE}=false         # override gzip compression per module
LOG_FILE_RETENTION_DAYS_{MODULE}=30      # override retention period per module
LOG_FILE_ENABLE_{MODULE}=false           # override file logging per module
```

## License

MIT
