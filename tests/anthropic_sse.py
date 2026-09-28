"""Serve a canned Anthropic Message as the Messages API's server-sent-event STREAM (test helper).

`AnthropicClient` streams every request (DECISIONS 2026-09-28), so an HTTP-level mock must answer with the
real event sequence — message_start, per-block content_block_start / *_delta / content_block_stop,
message_delta, message_stop — and the REAL SDK accumulates it. That exercises exactly the path that must keep
thinking blocks and their signatures intact: thinking text and signature arrive as separate deltas.

Usage is split as the API splits it: input and cache counts in message_start, the final output count in
message_delta (message_start carries a provisional output count of 1, which the final message must replace).
"""
from __future__ import annotations

import json

import httpx


def _events(msg: dict) -> list[tuple[str, dict]]:
    usage = dict(msg.get("usage") or {})
    final_out = usage.get("output_tokens", 0)
    start_usage = {**usage, "output_tokens": 1}
    ev = [("message_start", {"type": "message_start", "message": {
        **{k: v for k, v in msg.items() if k not in ("content", "usage", "stop_reason", "stop_sequence")},
        "content": [], "stop_reason": None, "stop_sequence": None, "usage": start_usage}})]
    for i, block in enumerate(msg.get("content") or []):
        t = block["type"]
        if t == "text":
            ev.append(("content_block_start", {"type": "content_block_start", "index": i,
                                               "content_block": {"type": "text", "text": ""}}))
            text = block["text"]
            for part in (text[: len(text) // 2], text[len(text) // 2:]):
                ev.append(("content_block_delta", {"type": "content_block_delta", "index": i,
                                                   "delta": {"type": "text_delta", "text": part}}))
        elif t == "thinking":
            ev.append(("content_block_start", {"type": "content_block_start", "index": i,
                                               "content_block": {"type": "thinking", "thinking": "", "signature": ""}}))
            th = block["thinking"]
            for part in (th[: len(th) // 2], th[len(th) // 2:]):
                ev.append(("content_block_delta", {"type": "content_block_delta", "index": i,
                                                   "delta": {"type": "thinking_delta", "thinking": part}}))
            ev.append(("content_block_delta", {"type": "content_block_delta", "index": i,
                                               "delta": {"type": "signature_delta", "signature": block["signature"]}}))
        elif t == "redacted_thinking":
            ev.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": block}))
        elif t == "tool_use":
            ev.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                "type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}))
            raw = json.dumps(block["input"])
            for part in (raw[: len(raw) // 2], raw[len(raw) // 2:]):
                ev.append(("content_block_delta", {"type": "content_block_delta", "index": i,
                                                   "delta": {"type": "input_json_delta", "partial_json": part}}))
        else:
            raise ValueError(f"unsupported block type {t!r}")
        ev.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    ev.append(("message_delta", {"type": "message_delta",
                                 "delta": {"stop_reason": msg.get("stop_reason"), "stop_sequence": None},
                                 "usage": {"output_tokens": final_out}}))
    ev.append(("message_stop", {"type": "message_stop"}))
    return ev


def sse_body(msg: dict) -> bytes:
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in _events(msg)).encode()


def sse_response(msg: dict) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse_body(msg))
