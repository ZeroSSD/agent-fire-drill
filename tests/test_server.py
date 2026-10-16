import os
import tempfile
import threading
import unittest

from firedrill import payments_server, tools


class ServerFaultTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = os.path.join(self.d, "ledger.db")
        os.environ["TRACE_PATH"] = os.path.join(self.d, "trace.jsonl")
        os.environ["REQUEST_TIMEOUT"] = "0.5"
        self.srv = payments_server.create_server(self.db, port=0, fault="timeout_after_commit", fault_delay=1.5)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        os.environ["PAYMENTS_URL"] = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()

    def test_timeout_after_commit_then_naive_retry_double_refunds(self):
        with self.assertRaises(tools.ToolTimeout):
            tools.refund("1001", 100)
        r = tools.refund("1001", 100)          # naive retry, no idempotency key
        self.assertFalse(r["replayed"])
        self.assertEqual(len(tools.get_refund_status("1001")["refunds"]), 2)

    def test_idempotency_key_replays_instead_of_duplicating(self):
        with self.assertRaises(tools.ToolTimeout):
            tools.refund("1001", 100, idempotency_key="k1")
        r = tools.refund("1001", 100, idempotency_key="k1")
        self.assertTrue(r["replayed"])
        self.assertEqual(len(tools.get_refund_status("1001")["refunds"]), 1)


class NoFaultTest(unittest.TestCase):
    def test_without_fault_one_call_one_refund(self):
        d = tempfile.mkdtemp()
        os.environ["TRACE_PATH"] = os.path.join(d, "trace.jsonl")
        os.environ["REQUEST_TIMEOUT"] = "2"
        srv = payments_server.create_server(os.path.join(d, "l.db"), port=0, fault="")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        os.environ["PAYMENTS_URL"] = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            r = tools.refund("3003", 25)
            self.assertEqual(r["status"], "processed")
            self.assertEqual(len(tools.get_refund_status("3003")["refunds"]), 1)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
