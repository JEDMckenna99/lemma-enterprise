#!/usr/bin/env python3
"""Sync canonical isHuman verifier packages to served and demo mirror paths."""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SYNC_MAP = {
    REPO_ROOT / "packages/ishuman-verify-js/index.mjs": REPO_ROOT / "static/js/lemma-ishuman-verify.mjs",
    REPO_ROOT / "packages/ishuman-verify-py/lemma_ishuman_verify.py": REPO_ROOT / "examples/relying_site_offline_verify.py",
    REPO_ROOT / "packages/ishuman-verify-py/lemma_ishuman_verify.py": REPO_ROOT / "demo-sites/lemma_ishuman_verify.py",
    REPO_ROOT / "packages/ishuman-verify-py/lemma_ishuman_site_policy.py": REPO_ROOT / "demo-sites/lemma_ishuman_site_policy.py",
    REPO_ROOT / "packages/ishuman-verify-py/lemma_ishuman_nonce_store.py": REPO_ROOT / "demo-sites/lemma_ishuman_nonce_store.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync(*, check_only: bool = False) -> bool:
    ok = True
    for src, dst in SYNC_MAP.items():
        if not src.is_file():
            print(f"MISSING source {src}")
            ok = False
            continue
        if check_only:
            if not dst.is_file() or _sha256(src) != _sha256(dst):
                print(f"DRIFT {src.name}: {src} -> {dst}")
                ok = False
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"synced {src.relative_to(REPO_ROOT)} -> {dst.relative_to(REPO_ROOT)}")
    return ok


def main() -> int:
    check_only = "--check" in sys.argv
    ok = sync(check_only=check_only)
    if check_only:
        print("sync check:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
