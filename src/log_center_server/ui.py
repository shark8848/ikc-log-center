"""Gradio UI for log_center search/browse.

Runs on LOG_CENTER_UI_PORT (default 9317).
"""
from __future__ import annotations

import os


def search_handler(trace_id: str, level: str, message_substr: str, limit: int) -> dict:
    """Query handler for the Gradio search form."""
    from .query import query_logs

    rows = query_logs(trace_id=trace_id, level=level, message_substr=message_substr, limit=limit)
    return {"count": len(rows), "items": rows}


def build_ui():
    """Build and return the Gradio Blocks UI."""
    try:
        import gradio as gr
    except ImportError:
        raise RuntimeError("gradio not installed — pip install log-center-sdk[ui]")

    with gr.Blocks(title="Log Center Search") as demo:
        gr.Markdown("# Log Center 查询\n输入 trace_id / level / 关键词 进行检索，默认 limit=100。")
        with gr.Row():
            trace_id = gr.Textbox(label="trace_id", placeholder="可选")
            level = gr.Textbox(label="level", placeholder="INFO/WARN/ERROR")
            message_substr = gr.Textbox(label="message contains", placeholder="关键词，可选")
            limit = gr.Number(value=100, precision=0, label="limit (<=500)")
        output = gr.JSON(label="结果", value={})
        btn = gr.Button("查询")
        btn.click(fn=search_handler, inputs=[trace_id, level, message_substr, limit], outputs=output)
    return demo


def main() -> None:
    """Entry point for standalone UI launch."""
    demo = build_ui()
    demo.launch(
        server_name=os.getenv("LOG_CENTER_UI_HOST", "0.0.0.0"),
        server_port=int(os.getenv("LOG_CENTER_UI_PORT", "9317")),
    )


if __name__ == "__main__":
    main()
