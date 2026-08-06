#!/usr/bin/env python3
"""Fetch, cryptographically verify, and publish the signed trust/bloom bundle.

Used by CI to mirror ``GET /api/revocation/bloom-filter`` to GitHub Pages.
Exits non-zero if fetch or signature verification fails (fail closed).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIMARY = "https://lemma.id/api/revocation/bloom-filter"


def _load_verifier_module():
    path = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
    spec = importlib.util.spec_from_file_location("lemma_proof_verifier_publish", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load verifier module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch_and_verify(primary_url: str) -> dict:
    with urllib.request.urlopen(primary_url, timeout=30) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("success"):
        raise RuntimeError("primary bundle returned success=false")

    verifier = _load_verifier_module()
    trust_list = data.get("trust_list") or {}
    issuers = verifier._verify_signed_trust_list_payload(trust_list)
    snapshot = data.get("snapshot") or {}
    hashed = data.get("hashed_revoked_ids") or []

    ctx = verifier.VerificationContext(site_id="lemma.id")
    ctx._verify_bloom_snapshot(snapshot, hashed, issuers)  # noqa: SLF001

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", default=DEFAULT_PRIMARY, help="Primary bloom-filter URL")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    data = fetch_and_verify(args.primary)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"published verified bundle -> {out} ({len(data.get('hashed_revoked_ids') or [])} revocations)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
