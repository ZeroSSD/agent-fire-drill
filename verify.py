"""Shim so `python verify.py refund_timeout` works from the repo root."""
from firedrill.verify import main

if __name__ == "__main__":
    main()
