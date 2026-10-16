"""Run a deterministic refund timeout scenario against the local mock service."""

import argparse
import json
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from . import payments_server, tools


def run_scenario(guardrail, workdir, fault="timeout_after_commit", fault_delay=1.5):
    """Run the retry-on-error policy and verify its real ledger and trace."""
    directory = Path(workdir)
    directory.mkdir(parents=True, exist_ok=True)
    db_path = str(directory / "ledger.db")
    trace_path = str(directory / "trace.jsonl")

    server = payments_server.create_server(
        db_path, port=0, fault=fault, fault_delay=fault_delay
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)

    env_keys = ("PAYMENTS_URL", "REQUEST_TIMEOUT", "TRACE_PATH")
    old_env = {key: os.environ.get(key) for key in env_keys}
    try:
        os.environ["PAYMENTS_URL"] = f"http://127.0.0.1:{server.server_address[1]}"
        os.environ["REQUEST_TIMEOUT"] = "1"
        os.environ["TRACE_PATH"] = trace_path
        thread.start()

        toolset = tools.get_tools(guardrail=guardrail)
        result = None
        for attempt in range(3):
            try:
                # Deliberately omit an idempotency key on every policy call.
                result = toolset["refund"]("1001", 100)
                break
            except tools.ToolError:
                if attempt == 2:
                    raise
                time.sleep(0.2)

        with sqlite3.connect(db_path) as connection:
            refund_count = connection.execute(
                "SELECT COUNT(*) FROM refunds"
            ).fetchone()[0]

        # Import at run time so the simulator uses the lead's verifier module.
        from . import verify

        report = verify.verify_refund_timeout(db_path, trace_path)
        return {
            "report": report,
            "refund_count": refund_count,
            "result": result,
            "db_path": db_path,
            "trace_path": trace_path,
        }
    finally:
        if thread.is_alive():
            server.shutdown()
            thread.join(timeout=2)
        server.server_close()
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _report(guardrail, workdir=None):
    """Run one mode and return the verifier report plus labels. A scripted policy, not an LLM."""
    def go(wd):
        out = run_scenario(guardrail, wd)
        r = dict(out["report"])
        r["guardrail"] = "on" if guardrail else "off"
        r["source"] = "scripted_simulation"   # the real LLM runner must set "llm_agent"
        return r
    if workdir:
        return go(workdir)
    with tempfile.TemporaryDirectory(prefix="firedrill-") as wd:
        return go(wd)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Simulate a refund timeout safely (scripted policy, no LLM)")
    parser.add_argument("--guardrail", choices=("off", "on"))
    parser.add_argument("--workdir")
    parser.add_argument("--compare", action="store_true", help="run both modes and print a before/after table")
    parser.add_argument("--out", help="with --compare: folder for results_off.json / results_on.json (+ .js wrappers)")
    args = parser.parse_args(argv)
    if not args.compare and not args.guardrail:
        parser.error("use --guardrail off|on or --compare")

    if args.compare:
        off, on = _report(False), _report(True)
        print(f"{'':16}{'refunds':>9}{'duplicates':>12}{'score':>7}  verdict")
        for name, r in (("guardrail OFF", off), ("guardrail ON", on)):
            print(f"{name:16}{r['refunds_total']:>9}{r['duplicate_refunds']:>12}{r['score']:>7}  {r['verdict']}")
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            for stem, var, r in (("results_off", "RESULTS_OFF", off), ("results_on", "RESULTS_ON", on)):
                with open(os.path.join(args.out, stem + ".json"), "w") as f:
                    json.dump(r, f, indent=2, sort_keys=True)
                with open(os.path.join(args.out, stem + ".js"), "w") as f:
                    f.write(f"window.{var} = " + json.dumps(r, indent=2, sort_keys=True) + ";\n")
        return
    print(json.dumps(_report(args.guardrail == "on", args.workdir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
