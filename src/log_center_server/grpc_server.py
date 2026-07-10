"""gRPC ingestion server — generic JSON bytes, no protobuf required.

Service: logcenter.LogService
Methods: Ingest, Health
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("log_center.grpc")


def serve_grpc() -> None:
    """Start gRPC server on LOG_CENTER_GRPC_PORT (default 9316).

    Blocks on ``server.wait_for_termination()``.
    """
    try:
        import grpc
        from concurrent import futures
    except ImportError:
        raise RuntimeError("grpcio not installed — pip install log-center-sdk[grpc]")

    from .app import process_entries
    from .auth import AUTH_ENABLED, verify_token

    def _deserialize(req: bytes) -> dict[str, Any]:
        if not req:
            return {}
        return json.loads(req.decode("utf-8"))

    def _serialize(resp: dict[str, Any]) -> bytes:
        return json.dumps(resp, ensure_ascii=False).encode("utf-8")

    def _unary(handler, request, context):
        data = _deserialize(request)
        result = handler(data, context)
        return _serialize(result)

    def _ingest_handler(payload: Any, context=None) -> dict[str, Any]:
        # Auth check
        if AUTH_ENABLED and context is not None:
            metadata = dict(context.invocation_metadata())
            auth_val = metadata.get("authorization", "")
            token = auth_val[7:].strip() if auth_val.startswith("Bearer ") else ""
            if not verify_token(token):
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "unauthorized")
                return {"status": "error", "reason": "unauthorized"}
        if isinstance(payload, list):
            entries = [e for e in payload if isinstance(e, dict)]
        elif isinstance(payload, dict):
            entries = [payload]
        else:
            return {"status": "error", "reason": "payload must be object or list"}
        if not entries:
            return {"status": "ok", "stored": 0}
        return process_entries(entries)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    server.add_generic_rpc_handlers(
        [
            grpc.method_handlers_generic_handler(
                "logcenter.LogService",
                {
                    "Ingest": grpc.unary_unary_rpc_method_handler(
                        lambda req, ctx: _unary(_ingest_handler, req, ctx)
                    ),
                    "Health": grpc.unary_unary_rpc_method_handler(
                        lambda req, ctx: _unary(lambda _d, _c: {"status": "ok"}, req, ctx)
                    ),
                },
            )
        ]
    )
    listen_addr = f"0.0.0.0:{os.getenv('LOG_CENTER_GRPC_PORT', '9316')}"
    server.add_insecure_port(listen_addr)
    logger.info("Starting log-center gRPC on %s", listen_addr)
    server.start()
    server.wait_for_termination()
