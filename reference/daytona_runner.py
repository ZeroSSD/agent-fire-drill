"""Reference: run the Fire Drill scenario in a FRESH Daytona sandbox with a scripted (no-LLM) policy.

    python reference/daytona_runner.py --guardrail off|on

Keys come from the environment (DAYTONA_API_KEY) or a git-ignored .env at the repo root. Never printed.
This is a reference for the real runner (the LLM agent replaces the scripted policy).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
REMOTE = "/tmp/fd"


def load_env():
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardrail", choices=["off", "on"], required=True)
    ap.add_argument("--out", help="write the verifier JSON here")
    a = ap.parse_args()
    load_env()
    if not os.environ.get("DAYTONA_API_KEY"):
        print("DAYTONA_API_KEY missing", file=sys.stderr)
        return 1
    from daytona import CreateSandboxFromSnapshotParams, Daytona

    # explicit list (never uploads .env): package files go to firedrill/, the root shim to the sandbox root
    files = [(f, f"{REMOTE}/firedrill/{f.name}") for f in sorted((ROOT / "firedrill").glob("*.py"))] + [(ROOT / "verify.py", f"{REMOTE}/verify.py")]
    name = f"fire-drill-{a.guardrail}-{uuid4().hex[:8]}"
    sandbox, code, stage = None, 0, "starting"
    try:
        client = Daytona()
        stage = "create sandbox"
        t0 = time.time()
        sandbox = client.create(CreateSandboxFromSnapshotParams(
            name=name, language="python", public=False, auto_stop_interval=5, auto_delete_interval=0,
            env_vars={"FAULT": "timeout_after_commit", "TRACE_PATH": f"{REMOTE}/trace.jsonl", "REQUEST_TIMEOUT": "3"}), timeout=90)
        print(f"sandbox ready in {time.time() - t0:.1f}s", flush=True)

        stage = "upload"
        sandbox.fs.create_folder(REMOTE, "755")
        sandbox.fs.create_folder(f"{REMOTE}/firedrill", "755")
        for local, dest in files:
            sandbox.fs.upload_file(str(local), dest, timeout=30)
        print(f"uploaded {len(files)} files", flush=True)

        stage = "start service"
        sandbox.process.exec("nohup python3 -u -m firedrill.payments_server --port 8099 --db ledger.db > server.log 2>&1 < /dev/null &", cwd=REMOTE, timeout=10)
        health = ("python3 -c \"import urllib.request as u,time\n"
                  "for i in range(20):\n"
                  "    try: print(u.urlopen('http://127.0.0.1:8099/health',timeout=1).read().decode()); break\n"
                  "    except Exception: time.sleep(0.5)\n"
                  "else: raise SystemExit(1)\"")
        h = sandbox.process.exec(health, cwd=REMOTE, timeout=30)
        if h.exit_code != 0:
            raise RuntimeError("service did not become healthy")
        print("health:", h.result.strip(), flush=True)

        stage = "scripted agent"
        g = "--guardrail " if a.guardrail == "on" else ""
        for attempt in range(3):                      # naive retry-on-error policy, no idempotency key
            r = sandbox.process.exec(f"python3 -m firedrill.cli {g}refund 1001 100", cwd=REMOTE, timeout=40)
            out = json.loads(r.result.strip().splitlines()[-1])
            print(f"attempt {attempt + 1}:", out, flush=True)
            if out.get("ok"):
                break
            time.sleep(0.2)

        stage = "verify"
        time.sleep(1)
        v = sandbox.process.exec("python3 verify.py refund_timeout --db ledger.db --trace trace.jsonl", cwd=REMOTE, timeout=30)
        if v.exit_code != 0 or not v.result.strip().startswith("{"):
            raise RuntimeError(f"verify exit={v.exit_code}: {v.result.strip()[:300]}")
        result = json.loads(v.result)
        result["guardrail"], result["source"], result["where"] = a.guardrail, "scripted_sandbox", "daytona sandbox"
        print(json.dumps(result, indent=2, sort_keys=True))
        if a.out:
            Path(a.out).write_text(json.dumps(result, indent=2, sort_keys=True))
    except Exception as exc:
        print(f"FAILED at '{stage}': {type(exc).__name__}: {str(exc)[:200].replace(os.environ.get('DAYTONA_API_KEY', '<none>'), '<key>')}", file=sys.stderr)
        code = 1
    finally:
        if sandbox is not None:
            try:
                sandbox.delete(timeout=60, wait=True)
                print("sandbox deleted", flush=True)
            except Exception as exc:
                print(f"cleanup NOT confirmed ({type(exc).__name__}): delete {name} in the Daytona dashboard", file=sys.stderr)
                code = max(code, 2)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
