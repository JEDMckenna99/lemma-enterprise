#!/usr/bin/env python3
"""Run the default non-live CI regression bundle."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    label = " ".join(cmd)
    print(f"\n==> {label}")
    merged = os.environ.copy()
    if env:
        merged.update(env)
    subprocess.run(cmd, cwd=REPO_ROOT, env=merged, check=True)


def main() -> int:
    test_env = {
        "SESSION_SECRET": "test-session-secret",
        "DATABASE_URL": "sqlite:///:memory:",
        "LEMMA_PPID_ROOT_KEY": "x" * 32,
        "LEMMA_IDENTITY_ROOT_PEPPER_V1": "y" * 32,
        "LEMMA_PERSON_ROOT_SALT_V1": "z" * 32,
    }

    _run([sys.executable, "-m", "pytest", "tests/test_csp_security.py", "-q"], env=test_env)
    _run([sys.executable, "scripts/generate_auth_scope_matrix.py"], env=test_env)
    _run(
        [
            sys.executable,
            "scripts/review_auth_scope_matrix.py",
            "--strict-state-changing",
        ],
        env=test_env,
    )
    _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "--ignore=tests/live",
            "--ignore=tests/auth_contract",
            "-q",
        ],
        env=test_env,
    )
    print("\nCI regression suite passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
