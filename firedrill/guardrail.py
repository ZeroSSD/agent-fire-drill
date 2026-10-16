"""Deterministic safety wrappers for the Fire Drill tools."""

import hashlib
import json
import threading
from decimal import Decimal, InvalidOperation

from . import tools as fire_tools


def _stable_key(order_id, amount):
    """Build the same key for equivalent order and amount values."""
    try:
        value = Decimal(str(amount))
        amount_text = format(value.normalize(), "f") if value.is_finite() else str(amount)
    except (InvalidOperation, ValueError):
        amount_text = str(amount)
    payload = json.dumps(
        [str(order_id), amount_text], ensure_ascii=False, separators=(",", ":")
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"refund-{digest}"


def wrap_tools(tools: dict) -> dict:
    """Return a tool mapping whose refund operation is timeout-safe.

    A wrapper instance remembers the first key selected for each order, so a
    later call for that order cannot silently switch to a different key.
    """
    wrapped = dict(tools)
    refund_tool = tools["refund"]
    status_tool = tools["get_refund_status"]
    key_by_order = {}
    key_lock = threading.Lock()

    def refund(order_id, amount, idempotency_key=None):
        order = str(order_id)
        with key_lock:
            key = key_by_order.get(order)
            if key is None:
                key = (
                    str(idempotency_key)
                    if idempotency_key not in (None, "")
                    else _stable_key(order, amount)
                )
                key_by_order[order] = key

        args = {"order_id": order, "amount": amount}
        fire_tools.trace(
            "guardrail_check", args, "ok", "stable idempotency key selected"
        )

        def existing_refund():
            try:
                status = status_tool(order)
            except fire_tools.ToolError as error:
                fire_tools.trace(
                    "guardrail_check", args, "error", "refund status lookup failed"
                )
                return None, error

            refunds = status.get("refunds", []) if isinstance(status, dict) else []
            for item in refunds:
                if str(item.get("order_id", order)) == order:
                    fire_tools.trace(
                        "guardrail_check", args, "ok", "existing refund found"
                    )
                    recovered = dict(item)
                    recovered.setdefault("status", "processed")
                    recovered["recovered_after_timeout"] = True
                    return recovered, None
            fire_tools.trace(
                "guardrail_check", args, "ok", "no existing refund found"
            )
            return None, None

        try:
            return refund_tool(order, amount, idempotency_key=key)
        except fire_tools.ToolTimeout:
            recovered, _status_error = existing_refund()
            if recovered is not None:
                return recovered

            retry_args = {"order_id": order, "amount": amount, "attempt": 2}
            fire_tools.trace(
                "guardrail_retry", retry_args, "ok", "retrying once with the same key"
            )
            try:
                return refund_tool(order, amount, idempotency_key=key)
            except fire_tools.ToolTimeout:
                recovered, _status_error = existing_refund()
                if recovered is not None:
                    return recovered
                raise

    wrapped["refund"] = refund
    return wrapped
