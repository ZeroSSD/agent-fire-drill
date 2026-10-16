"""Step (a): upload a hello HTTP service to a fresh Daytona sandbox, then delete it."""

import os
from pathlib import Path
import sys
from uuid import uuid4


def main() -> int:
    if not os.environ.get("DAYTONA_API_KEY"):
        print("DAYTONA_API_KEY is missing. Set it in this terminal; do not put it in source.", file=sys.stderr)
        return 1

    try:
        from daytona import CreateSandboxFromSnapshotParams, Daytona
    except ImportError:
        print("Install the SDK: python -m pip install -r requirements.txt", file=sys.stderr)
        return 1

    payload = Path(__file__).resolve().parent / "smoke_payload"
    # This explicit list uploads only our fixture, never environment files or keys.
    files = [payload / "hello.py", payload / "probe.py"]
    if any(not path.is_file() for path in files):
        print("smoke_payload/hello.py or smoke_payload/probe.py is missing.", file=sys.stderr)
        return 1

    sandbox = None
    sandbox_name = f"fire-drill-smoke-{uuid4().hex[:12]}"
    stage = "initializing Daytona"
    exit_code = 0
    try:
        client = Daytona()  # Reads DAYTONA_API_KEY; credentials stay on this machine.
        stage = "creating sandbox"
        print(f"Creating sandbox: {sandbox_name}", flush=True)
        sandbox = client.create(
            CreateSandboxFromSnapshotParams(
                name=sandbox_name,
                language="python",
                public=False,
                env_vars={"FAULT": "timeout_after_commit"},
                auto_stop_interval=5,
                auto_delete_interval=0,
            ),
            timeout=60,
        )
        print(f"Sandbox ready: {sandbox.id}", flush=True)

        stage = "uploading fixture folder"
        remote_dir = "/tmp/agent-fire-drill"
        sandbox.fs.create_folder(remote_dir, "755")
        for source in files:
            sandbox.fs.upload_file(str(source), f"{remote_dir}/{source.name}", timeout=30)
        print("Uploaded smoke_payload (2 files)", flush=True)

        stage = "starting HTTP service"
        started = sandbox.process.exec(
            "nohup python3 -u hello.py > server.log 2>&1 < /dev/null &",
            cwd=remote_dir,
            timeout=10,
        )
        if started.exit_code != 0:
            raise RuntimeError("HTTP service launch command failed")
        print("HTTP service starting on sandbox port 8000", flush=True)

        stage = "checking HTTP response inside sandbox"
        checked = sandbox.process.exec("python3 probe.py", cwd=remote_dir, timeout=40)
        if checked.exit_code != 0:
            raise RuntimeError("HTTP probe failed; check the service startup")
        print(checked.result.strip(), flush=True)
    except Exception as exc:
        # SDK error strings may contain request details; do not print credentials or headers.
        print(f"FAILED while {stage} ({type(exc).__name__}).", file=sys.stderr, flush=True)
        if sandbox is None:
            print(
                f"If creation timed out, check the Daytona dashboard for {sandbox_name}.",
                file=sys.stderr,
            )
        exit_code = 1
    finally:
        if sandbox is not None:
            print(f"Deleting sandbox: {sandbox.id}", flush=True)
            try:
                sandbox.delete(timeout=60, wait=True)
                print("Sandbox deleted", flush=True)
            except Exception as exc:
                print(
                    f"Cleanup not confirmed ({type(exc).__name__}). "
                    f"Check/delete sandbox {sandbox.id} in the Daytona dashboard.",
                    file=sys.stderr,
                    flush=True,
                )
                exit_code = 2

    if exit_code == 0:
        print("PASS: sandbox boot, folder upload, HTTP call, and teardown", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

