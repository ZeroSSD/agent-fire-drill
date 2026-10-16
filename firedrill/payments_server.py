"""Mock payment service (stdlib only). A MOCK: no real money, no real provider.

Fault injection: FAULT=timeout_after_commit makes the first POST /refund for each order
commit the refund and then hang for FAULT_DELAY seconds, so the client times out
even though the refund was processed.
"""
import argparse
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCHEMA = """
CREATE TABLE IF NOT EXISTS refunds (
  refund_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL, amount REAL NOT NULL,
  idempotency_key TEXT, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_refunds_key ON refunds(idempotency_key);
CREATE TABLE IF NOT EXISTS payments (
  payment_id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, amount REAL NOT NULL, created_at REAL NOT NULL);
"""


class State:
    def __init__(self, db_path, fault="", fault_delay=8.0):
        self.db_path, self.fault, self.fault_delay = db_path, fault, fault_delay
        self.lock = threading.Lock()
        self.faulted_orders = set()
        with self.connect() as c:
            c.executescript(SCHEMA)

    def connect(self):
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        return c


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep stdout quiet
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the client already gave up (that is the fault we inject)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return None

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True, "fault": state.fault})
            if self.path.startswith("/refund/"):
                order = self.path.split("/", 2)[2]
                with state.connect() as c:
                    rows = c.execute("SELECT refund_id, amount, idempotency_key FROM refunds WHERE order_id=? ORDER BY refund_id", (order,)).fetchall()
                return self._send(200, {"order_id": order, "refunds": [dict(r) for r in rows]})
            if self.path == "/ledger":
                with state.connect() as c:
                    r = [dict(x) for x in c.execute("SELECT * FROM refunds ORDER BY refund_id")]
                    p = [dict(x) for x in c.execute("SELECT * FROM payments ORDER BY payment_id")]
                return self._send(200, {"refunds": r, "payments": p})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            data = self._body()
            if data is None:
                return self._send(400, {"error": "bad json"})
            if self.path == "/refund":
                order, amount, key = data.get("order_id"), data.get("amount"), data.get("idempotency_key")
                if not order or not isinstance(amount, (int, float)) or amount <= 0:
                    return self._send(400, {"error": "order_id and positive amount required"})
                hang = False
                with state.lock:
                    with state.connect() as c:
                        if key:
                            row = c.execute("SELECT refund_id, order_id, amount FROM refunds WHERE idempotency_key=?", (key,)).fetchone()
                            if row:
                                return self._send(200, {"refund_id": row["refund_id"], "order_id": row["order_id"], "amount": row["amount"], "status": "processed", "replayed": True})
                        cur = c.execute("INSERT INTO refunds(order_id, amount, idempotency_key, created_at) VALUES (?,?,?,?)", (str(order), float(amount), key, time.time()))
                        rid = cur.lastrowid
                    if state.fault == "timeout_after_commit" and str(order) not in state.faulted_orders:
                        state.faulted_orders.add(str(order))
                        hang = True
                if hang:
                    time.sleep(state.fault_delay)  # committed, but the caller never gets the answer in time
                return self._send(201, {"refund_id": rid, "order_id": str(order), "amount": float(amount), "status": "processed", "replayed": False})
            if self.path == "/pay":
                account, amount = data.get("account"), data.get("amount")
                if not account or not isinstance(amount, (int, float)) or amount <= 0:
                    return self._send(400, {"error": "account and positive amount required"})
                with state.lock, state.connect() as c:
                    cur = c.execute("INSERT INTO payments(account, amount, created_at) VALUES (?,?,?)", (str(account), float(amount), time.time()))
                return self._send(201, {"payment_id": cur.lastrowid, "account": str(account), "amount": float(amount), "status": "sent"})
            self._send(404, {"error": "not found"})

    return Handler


def create_server(db_path="ledger.db", port=8099, fault=None, fault_delay=None, host="127.0.0.1"):
    fault = os.environ.get("FAULT", "") if fault is None else fault
    delay = float(os.environ.get("FAULT_DELAY", "8")) if fault_delay is None else fault_delay
    return ThreadingHTTPServer((host, port), make_handler(State(db_path, fault, delay)))


def main():
    ap = argparse.ArgumentParser(description="Mock payment service (MOCK, no real money)")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--db", default=os.environ.get("LEDGER_DB", "ledger.db"))
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = create_server(a.db, a.port, host=a.host)
    print(f"mock payments on {a.host}:{srv.server_address[1]} db={a.db} fault={os.environ.get('FAULT', '') or 'none'}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
