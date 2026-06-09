#!/usr/bin/env python3
"""Thin wrapper for canvas Phase B revoke-to-deny smoke (delegates to evidence script)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / "revoke_to_deny_evidence.py"


def main() -> int:
    if not _TARGET.exists():
        print(f"revoke_to_deny_result=FAIL missing={_TARGET}", file=sys.stderr)
        return 1
    result = subprocess.run([sys.executable, str(_TARGET)], check=False)
    return int(result.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
