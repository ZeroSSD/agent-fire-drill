"""Run one tool call and print JSON. Meant to be executed INSIDE the sandbox, so the agent can
live on the host while the payment service and ledger stay in the sandbox (no public URL needed).

    python -m firedrill.cli refund 1001 100 [--key K] [--guardrail]
    python -m firedrill.cli status 1001
    python -m firedrill.cli pay ACCOUNT 50

Always exits 0 and prints {"ok": true, "result": ...} or {"ok": false, "error": "..."}, so the
caller can hand the text straight back to the LLM as the tool result.
"""
import argparse
import json

from . import tools


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardrail", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refund"); r.add_argument("order_id"); r.add_argument("amount", type=float); r.add_argument("--key")
    s = sub.add_parser("status"); s.add_argument("order_id")
    p = sub.add_parser("pay"); p.add_argument("account"); p.add_argument("amount", type=float)
    a = ap.parse_args(argv)
    t = tools.get_tools(guardrail=a.guardrail)
    try:
        if a.cmd == "refund":
            out = t["refund"](a.order_id, a.amount, a.key)
        elif a.cmd == "status":
            out = t["get_refund_status"](a.order_id)
        else:
            out = t["pay"](a.account, a.amount)
        print(json.dumps({"ok": True, "result": out}))
    except tools.ToolError as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))


if __name__ == "__main__":
    main()
