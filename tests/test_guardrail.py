import tempfile
import unittest

from firedrill import tools
from firedrill.guardrail import wrap_tools
from firedrill.simulate import run_scenario


class GuardrailSimulationTest(unittest.TestCase):
    def test_guardrail_off_timeout_run_creates_two_refunds(self):
        with tempfile.TemporaryDirectory() as workdir:
            result = run_scenario(False, workdir)
        self.assertEqual(result["refund_count"], 2)
        self.assertEqual(result["report"]["refunds_total"], 2)

    def test_guardrail_on_timeout_run_creates_one_refund(self):
        with tempfile.TemporaryDirectory() as workdir:
            result = run_scenario(True, workdir)
        self.assertEqual(result["refund_count"], 1)
        self.assertEqual(result["report"]["refunds_total"], 1)
        self.assertTrue(result["result"]["recovered_after_timeout"])

    def test_refund_retries_and_later_calls_keep_one_key_per_order(self):
        calls = []

        def refund(order_id, amount, idempotency_key=None):
            calls.append((order_id, idempotency_key))
            if len(calls) == 1:
                raise tools.ToolTimeout("simulated timeout")
            return {"order_id": order_id, "amount": amount, "status": "processed"}

        raw_tools = {
            "refund": refund,
            "get_refund_status": lambda order_id: {"order_id": order_id, "refunds": []},
            "pay": lambda account, amount: {},
        }
        with tempfile.TemporaryDirectory() as workdir:
            import os

            old_trace = os.environ.get("TRACE_PATH")
            os.environ["TRACE_PATH"] = os.path.join(workdir, "trace.jsonl")
            try:
                wrapped = wrap_tools(raw_tools)
                wrapped["refund"]("1001", 100, idempotency_key="first-key")
                wrapped["refund"]("1001", 100, idempotency_key="different-key")
            finally:
                if old_trace is None:
                    os.environ.pop("TRACE_PATH", None)
                else:
                    os.environ["TRACE_PATH"] = old_trace

        self.assertEqual([key for _order, key in calls], ["first-key"] * 3)

    def test_no_fault_run_is_one_refund_in_both_modes(self):
        for guardrail in (False, True):
            with self.subTest(guardrail=guardrail):
                with tempfile.TemporaryDirectory() as workdir:
                    result = run_scenario(guardrail, workdir, fault="")
                self.assertEqual(result["refund_count"], 1)
                self.assertEqual(result["report"]["refunds_total"], 1)


if __name__ == "__main__":
    unittest.main()
