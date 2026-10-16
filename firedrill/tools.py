"""Tools the agent calls. Plain HTTP to the mock payment service, with a trace file."""
import json
import os
import socket
import time
import urllib.error
import urllib.request


class ToolError(Exception):
    pass


class ToolTimeout(ToolError):
    pass


def _url():
    return os.environ.get("PAYMENTS_URL", "http://127.0.0.1:8099")


def _timeout():
    return float(os.environ.get("REQUEST_TIMEOUT", "3"))


def trace(tool, args, outcome, detail=""):
    path = os.environ.get("TRACE_PATH", "trace.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps({"ts": time.time(), "tool": tool, "args": args, "outcome": outcome, "detail": detail}) + "\n")


def _call(tool, method, path, args, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(_url() + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_timeout()) as r:
            out = json.loads(r.read() or b"{}")
        trace(tool, args, "ok", json.dumps(out)[:200])
        return out
    except (socket.timeout, TimeoutError):
        trace(tool, args, "timeout", "request timed out")
        raise ToolTimeout("request timed out")
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            trace(tool, args, "timeout", "request timed out")
            raise ToolTimeout("request timed out")
        trace(tool, args, "error", str(e)[:200])
        raise ToolError(f"request failed: {e}")


def refund(order_id, amount, idempotency_key=None):
    body = {"order_id": str(order_id), "amount": amount}
    if idempotency_key:
        body["idempotency_key"] = idempotency_key
    return _call("refund", "POST", "/refund", {"order_id": str(order_id), "amount": amount, "idempotency_key": idempotency_key}, body)


def get_refund_status(order_id):
    return _call("get_refund_status", "GET", f"/refund/{order_id}", {"order_id": str(order_id)})


def pay(account, amount):
    return _call("pay", "POST", "/pay", {"account": account, "amount": amount}, {"account": account, "amount": amount})


def get_tools(guardrail=False):
    tools = {"refund": refund, "get_refund_status": get_refund_status, "pay": pay}
    if guardrail:
        from . import guardrail as g
        return g.wrap_tools(tools)
    return tools


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "refund", "description": "Issue a refund for an order. May fail with an error; the call is retryable.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}, "idempotency_key": {"type": "string", "description": "optional"}}, "required": ["order_id", "amount"]}}},
    {"type": "function", "function": {"name": "get_refund_status", "description": "List the refunds recorded for an order.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {"name": "pay", "description": "Send a payment to an account.",
        "parameters": {"type": "object", "properties": {"account": {"type": "string"}, "amount": {"type": "number"}}, "required": ["account", "amount"]}}},
]
