"""CLI entry point: ``python -m log_center_server``.

Starts the HTTP API server (uvicorn) on the main thread.
Optionally starts gRPC as a daemon thread.

The web UI (Vite + React) is served as static files from web/dist/
when available, or run separately via ``cd web && npm run dev``.

Token management commands (exit after execution):
  --gen-token DESC       Generate a new API token
  --list-tokens          List all tokens
  --revoke-token PREFIX  Revoke a token by prefix
"""
from __future__ import annotations

import argparse
import os
import sys
import threading


def main() -> None:
    parser = argparse.ArgumentParser(description="Log Center Server")
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("LOG_CENTER_PORT", "9315")),
        help="HTTP API port (default: 9315)",
    )
    parser.add_argument(
        "--host", default=os.getenv("LOG_CENTER_HOST", "0.0.0.0"),
        help="Bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--grpc", action="store_true",
        help="Also start gRPC server on LOG_CENTER_GRPC_PORT (default: 9316)",
    )
    parser.add_argument(
        "--ui", action="store_true",
        help="Print web UI URL (UI is served from web/dist/ by FastAPI)",
    )
    parser.add_argument(
        "--ui-port", type=int, default=int(os.getenv("LOG_CENTER_UI_PORT", "9317")),
        help="(Deprecated) UI port — no longer used with Vite frontend",
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload (development mode)",
    )
    # Token management
    parser.add_argument(
        "--gen-token", nargs="?", const="", default=None, metavar="DESC",
        help="Generate a new API token (optional description)",
    )
    parser.add_argument(
        "--list-tokens", action="store_true",
        help="List all API tokens",
    )
    parser.add_argument(
        "--revoke-token", metavar="PREFIX",
        help="Revoke a token by its prefix",
    )
    args = parser.parse_args()

    # ── Token management commands (run and exit) ───────────────
    if args.gen_token is not None or args.list_tokens or args.revoke_token:
        _handle_token_command(args)
        return

    # Optionally start gRPC in a daemon thread
    if args.grpc:
        from .grpc_server import serve_grpc

        grpc_thread = threading.Thread(target=serve_grpc, daemon=True)
        grpc_thread.start()

    # Print UI info
    if args.ui:
        print(f"  Web UI:  http://localhost:{args.port}  (served by FastAPI from web/dist/)")
        print(f"  Dev UI:  cd web && npm run dev  (http://localhost:5173 with HMR)")

    # Start FastAPI via uvicorn (main thread)
    import uvicorn

    uvicorn.run(
        "log_center_server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def _handle_token_command(args) -> None:
    """Handle --gen-token / --list-tokens / --revoke-token and exit."""
    from .auth import (
        add_token,
        backend_description,
        generate_token,
        init_token_store,
        list_tokens,
        revoke_token,
    )

    init_token_store()

    if args.gen_token is not None:
        plain, info = generate_token(description=args.gen_token or "")
        add_token(info)
        print()
        print("Token generated successfully:")
        print()
        print(f"  {plain}")
        print()
        print(f"  Prefix:      {info['prefix']}")
        if info['description']:
            print(f"  Description: {info['description']}")
        print(f"  Backend:     {backend_description()}")
        print()
        print("  IMPORTANT: Save this token now. It cannot be retrieved later.")
        print()
        return

    if args.list_tokens:
        tokens = list_tokens()
        if not tokens:
            print("No tokens found.")
            return
        print(f"\n{'Prefix':<14} {'Active':<8} {'Created':<22} Description")
        print("-" * 72)
        for t in tokens:
            status = "active" if t.get("active", True) else "revoked"
            desc = t.get("description", "") or ""
            print(f"{t['prefix']:<14} {status:<8} {t.get('created_at', ''):<22} {desc}")
        print(f"\nTotal: {len(tokens)} token(s)")
        return

    if args.revoke_token:
        prefix = args.revoke_token
        ok = revoke_token(prefix)
        if ok:
            print(f"Token '{prefix}' revoked successfully.")
        else:
            print(f"No active token found with prefix '{prefix}'.")
            sys.exit(1)


if __name__ == "__main__":
    main()
