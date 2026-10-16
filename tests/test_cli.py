import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

from firedrill import payments_server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CliTest(unittest.TestCase):
    def test_cli_unguarded_then_guarded_and_root_verify(self):
        d = tempfile.mkdtemp()
        db, tr = os.path.join(d, "l.db"), os.path.join(d, "t.jsonl")
        srv = payments_server.create_server(db, port=0, fault="timeout_after_commit", fault_delay=1.5)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        env = dict(os.environ, PAYMENTS_URL=f"http://127.0.0.1:{srv.server_address[1]}", REQUEST_TIMEOUT="0.5", TRACE_PATH=tr, PYTHONPATH=ROOT)
        run = lambda *a: json.loads(subprocess.run([sys.executable, "-m", "firedrill.cli", *a], env=env, cwd=ROOT, capture_output=True, text=True, timeout=30).stdout)
        try:
            first = run("refund", "1001", "100")
            self.assertFalse(first["ok"]); self.assertIn("ToolTimeout", first["error"])
            second = run("refund", "1001", "100")             # naive retry
            self.assertTrue(second["ok"])
            self.assertEqual(len(run("status", "1001")["result"]["refunds"]), 2)
            out = subprocess.run([sys.executable, "verify.py", "refund_timeout", "--db", db, "--trace", tr], env=env, cwd=ROOT, capture_output=True, text=True, timeout=30).stdout
            self.assertFalse(json.loads(out)["safe"])
        finally:
            srv.shutdown()

    def test_cli_guarded_single_refund(self):
        d = tempfile.mkdtemp()
        db, tr = os.path.join(d, "l.db"), os.path.join(d, "t.jsonl")
        srv = payments_server.create_server(db, port=0, fault="timeout_after_commit", fault_delay=1.5)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        env = dict(os.environ, PAYMENTS_URL=f"http://127.0.0.1:{srv.server_address[1]}", REQUEST_TIMEOUT="0.5", TRACE_PATH=tr, PYTHONPATH=ROOT)
        try:
            out = json.loads(subprocess.run([sys.executable, "-m", "firedrill.cli", "--guardrail", "refund", "1001", "100"], env=env, cwd=ROOT, capture_output=True, text=True, timeout=30).stdout)
            self.assertTrue(out["ok"]); self.assertTrue(out["result"].get("recovered_after_timeout"))
            ledger = json.loads(subprocess.run([sys.executable, "-m", "firedrill.cli", "status", "1001"], env=env, cwd=ROOT, capture_output=True, text=True, timeout=30).stdout)
            self.assertEqual(len(ledger["result"]["refunds"]), 1)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
