#!/usr/bin/env python3
"""Fail CI/deploy smoke when production isHuman config is unsafe."""

from __future__ import annotations

import os
import sys


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _truthy(name: str) -> bool:
    return _env(name).lower() in {"1", "true", "yes", "on"}


def _verify_didit_via_live() -> list[str]:
    """Confirm Didit is enabled on production without requiring Didit secrets in CI."""
    try:
        import requests
    except ImportError:
        return ["requests is required for live Didit config verification"]

    base = _env("ISHUMAN_LIVE_BASE_URL") or _env("LEMMA_BASE_URL") or "https://lemma.id"
    wallet_id = _env("ISHUMAN_LIVE_WALLET_ID") or _env("LEMMA_ISHUMAN_PROD_TEST_WALLET_ID")
    wallet_secret = _env("ISHUMAN_LIVE_WALLET_SECRET") or _env("LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET")
    if not wallet_id or not wallet_secret:
        return ["Didit live verification requires prod test wallet credentials in CI"]

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from api.wallet_keys import build_wallet_assertion, register_self_signature  # noqa: E402

    session = requests.Session()
    pubkey_b64, sig_b64 = register_self_signature(wallet_id, wallet_secret)
    reg = session.post(
        f"{base.rstrip('/')}/api/wallet/register-signing-key",
        json={"wallet_id": wallet_id, "pubkey": pubkey_b64, "signature": sig_b64},
        timeout=30,
    )
    if reg.status_code not in (200, 403):
        return [f"register-signing-key failed during Didit probe: HTTP {reg.status_code}"]

    challenge = session.post(
        f"{base.rstrip('/')}/api/wallet/challenge",
        json={"wallet_id": wallet_id},
        timeout=30,
    )
    if not challenge.ok:
        return [f"wallet challenge failed during Didit probe: HTTP {challenge.status_code}"]
    nonce = (challenge.json() or {}).get("nonce")
    if not nonce:
        return ["wallet challenge returned no nonce during Didit probe"]

    return_url = f"{base.rstrip('/')}/demo/ishuman"
    assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=["return_url"],
        field_values={"return_url": return_url},
        nonce_b64=nonce,
    )
    start = session.post(
        f"{base.rstrip('/')}/api/ishuman/start-verification",
        json={
            "wallet_id": wallet_id,
            "return_url": return_url,
            "provider": "didit",
            "wallet_assertion": {"nonce": assertion.nonce, "signature": assertion.signature},
        },
        timeout=30,
    )
    try:
        data = start.json()
    except ValueError:
        data = {}

    if start.status_code == 400 and (data.get("error") or "") == "didit_not_enabled":
        return ["Didit rail is not enabled on production"]
    if start.status_code != 200 or not data.get("success"):
        return [f"Didit start-verification probe failed: HTTP {start.status_code} {str(data)[:180]}"]
    if data.get("provider") != "didit" or not data.get("url"):
        return ["Didit start-verification did not return a hosted Didit URL"]
    if "client_secret" in data:
        return ["Didit start-verification leaked client_secret in response"]
    return []


def main() -> int:
    env = _env("ENVIRONMENT").lower()
    if env != "production":
        print(f"OK: ENVIRONMENT={env or '(unset)'}, production-only isHuman gate skipped")
        return 0

    errors: list[str] = []

    if _truthy("LEMMA_ISHUMAN_SKELETON_IDV_ENABLED"):
        errors.append("LEMMA_ISHUMAN_SKELETON_IDV_ENABLED must be off on production")
    if _truthy("LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED"):
        errors.append("LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED must be off on production")
    if _truthy("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY"):
        errors.append("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY must be off on production")

    didit_env_present = all(_env(name) for name in ("DIDIT_API_KEY", "DIDIT_WORKFLOW_ID", "DIDIT_WEBHOOK_SECRET"))
    if didit_env_present:
        pass
    else:
        errors.extend(_verify_didit_via_live())

    if _env("LEMMA_IDV_HANDOFF_STRICT_CLAIM").lower() in {"0", "false", "no", "off"}:
        errors.append("LEMMA_IDV_HANDOFF_STRICT_CLAIM must stay enabled on production")

    if errors:
        print("isHuman production config check FAILED:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("OK: isHuman production config gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
