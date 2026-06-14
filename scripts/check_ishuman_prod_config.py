#!/usr/bin/env python3
"""Fail CI/deploy smoke when production isHuman config is unsafe."""

from __future__ import annotations

import os
import sys


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _truthy(name: str) -> bool:
    return _env(name).lower() in {"1", "true", "yes", "on"}


def main() -> int:
    env = _env("ENVIRONMENT").lower()
    if env != "production":
        print(f"OK: ENVIRONMENT={env or '(unset)'} — production-only isHuman gate skipped")
        return 0

    errors: list[str] = []

    if _truthy("LEMMA_ISHUMAN_SKELETON_IDV_ENABLED"):
        errors.append("LEMMA_ISHUMAN_SKELETON_IDV_ENABLED must be off on production")
    if _truthy("LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED"):
        errors.append("LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED must be off on production")
    if _truthy("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY"):
        errors.append("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY must be off on production")

    if not _env("DIDIT_API_KEY"):
        errors.append("DIDIT_API_KEY must be set on production")
    if not _env("DIDIT_WORKFLOW_ID"):
        errors.append("DIDIT_WORKFLOW_ID must be set on production")
    if not _env("DIDIT_WEBHOOK_SECRET"):
        errors.append("DIDIT_WEBHOOK_SECRET must be set on production")

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
