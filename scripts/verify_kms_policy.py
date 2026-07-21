#!/usr/bin/env python3
"""Verify AWS KMS policy readiness for Section 7 secrets."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from api.config import is_production
    from api.kms_manager import get_kms_manager

    kms = get_kms_manager()
    checks: list[tuple[str, bool, object]] = []

    enabled = kms.is_enabled()
    checks.append(("kms-enabled", enabled, {"enabled": enabled}))

    info = kms.get_key_info() if enabled else None
    checks.append(
        (
            "kms-key-metadata",
            bool(info and info.get("enabled") and info.get("key_state") == "Enabled"),
            info or "missing",
        )
    )

    rotation = kms.get_rotation_status() if enabled else None
    checks.append(
        (
            "kms-rotation-status-readable",
            rotation is not None,
            rotation or "missing",
        )
    )

    oauth_roundtrip = (
        kms.verify_identity_encryption_context(
            key_type="site_oauth_client",
            purpose="oauth_client_secret",
            context_id="section7-policy-probe",
        )
        if enabled
        else not is_production()
    )
    checks.append(("oauth-secret-kms-context", oauth_roundtrip, oauth_roundtrip))

    person_roundtrip = (
        kms.verify_identity_encryption_context(
            key_type="ishuman_person_root",
            purpose="ppid_derivation",
            context_id="section7-policy-probe",
        )
        if enabled
        else not is_production()
    )
    checks.append(("person-root-kms-context", person_roundtrip, person_roundtrip))

    passed = 0
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {json.dumps(detail, default=str)}")
        if ok:
            passed += 1

    print(f"\nKMS policy verification: {passed}/{len(checks)} passed")
    if is_production() and passed != len(checks):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
