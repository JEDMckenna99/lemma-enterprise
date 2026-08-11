#!/usr/bin/env python3
"""Five-minute offline demo: mint, verify accept, tamper reject."""

from __future__ import annotations

import sys
from pathlib import Path

OSS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OSS_ROOT / "packages" / "proof-verifier-py"))

from lemma_proof_verifier_testing import (  # noqa: E402
    create_offline_test_context,
    mint_test_issuer,
    mint_test_presentation,
)

SITE_ID = "localhost"
PPID = "did:lemma:ppid_demo_user"
REQUIRED = "passkey"


def _ok(label: str) -> None:
    print(f"  PASS  {label}")


def _fail(label: str, detail: str) -> None:
    print(f"  FAIL  {label}: {detail}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    print("lemma.id offline verifier demo (Python)\n")

    print("1. Mint test presentation")
    issuer = mint_test_issuer()
    presentation = mint_test_presentation(
        site_id=SITE_ID,
        ppid=PPID,
        assurance=REQUIRED,
        issuer=issuer,
    )
    if not presentation.get("credential", {}).get("proof", {}).get("signatureValueWeb"):
        _fail("mint", "missing signature")
    _ok("signed presentation minted")

    print("2. Verify accept")
    ctx = create_offline_test_context(
        site_id=SITE_ID,
        issuer_did=issuer["did"],
        issuer_pubkey_hex=issuer["pubkey_hex"],
        required_assurance=REQUIRED,
    )
    result = ctx.verify(presentation)
    if not result.ok:
        _fail("verify", getattr(result, "reason", "unknown"))
    if result.ppid != PPID:
        _fail("verify", f"unexpected ppid {result.ppid!r}")
    _ok(f"ppid={result.ppid} assurance={result.assurance}")

    print("3. Wrong site binding -> reject")
    wrong_site = mint_test_presentation(
        site_id="evil.example",
        ppid=PPID,
        assurance=REQUIRED,
        issuer=issuer,
    )
    reject = ctx.verify(wrong_site)
    if reject.ok:
        _fail("tamper", "expected rejection")
    if reject.reason != "site_id_mismatch":
        _fail("tamper", f"expected site_id_mismatch got {reject.reason!r}")
    _ok(f"fail-closed reason={reject.reason}")

    print("\nDone — verifier accept/reject path works offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
