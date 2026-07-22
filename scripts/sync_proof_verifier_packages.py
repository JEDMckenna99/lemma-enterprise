#!/usr/bin/env python3
"""Sync canonical proof-verifier packages to served and demo mirror paths."""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_PKG_PY = REPO_ROOT / "packages/proof-verifier-py"
_MAIN_PY = _PKG_PY / "lemma_proof_verifier.py"
_SITE_POLICY_PY = _PKG_PY / "lemma_proof_verifier_site_policy.py"
_NONCE_STORE_PY = _PKG_PY / "lemma_proof_verifier_nonce_store.py"
_MAIN_MJS = REPO_ROOT / "packages/proof-verifier-js/index.mjs"

SYNC_PAIRS: list[tuple[Path, Path]] = [
    (_MAIN_MJS, REPO_ROOT / "static/js/proof-verifier.mjs"),
    (_MAIN_PY, REPO_ROOT / "examples/proof-verifier.py"),
    (_MAIN_PY, REPO_ROOT / "demo-sites/lemma_proof_verifier.py"),
    (_SITE_POLICY_PY, REPO_ROOT / "demo-sites/lemma_proof_verifier_site_policy.py"),
    (_NONCE_STORE_PY, REPO_ROOT / "demo-sites/lemma_proof_verifier_nonce_store.py"),
    (_MAIN_PY, REPO_ROOT / "demo-sites/lemma_ishuman_verify.py"),
    (_SITE_POLICY_PY, REPO_ROOT / "demo-sites/lemma_ishuman_site_policy.py"),
    (_NONCE_STORE_PY, REPO_ROOT / "demo-sites/lemma_ishuman_nonce_store.py"),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync(*, check_only: bool = False) -> bool:
    ok = True
    for src, dst in SYNC_PAIRS:
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
