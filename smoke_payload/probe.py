"""Run inside Daytona: wait for the service and verify an actual HTTP response."""

import json
import time
from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            with urlopen("http://127.0.0.1:8000/hello", timeout=2) as response:
                status = response.status
                body = json.load(response)
            if status != 200 or body != {"message": "hello from Daytona"}:
                print("FAIL: unexpected HTTP response", flush=True)
                return 1
            print(json.dumps({"http_status": status, "body": body}), flush=True)
            return 0
        except (URLError, OSError):
            time.sleep(0.5)
    print("FAIL: hello service did not become ready within 25 seconds", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

