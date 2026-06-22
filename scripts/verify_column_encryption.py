#!/usr/bin/env python3
"""Verify at-rest column encryption is configured (production gate)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from api.column_crypto import column_encryption_active, reset_key_cache

    reset_key_cache()
    explicit = bool((os.environ.get("LEMMA_COLUMN_ENCRYPTION_KEY") or "").strip())
    salt = bool((os.environ.get("LEMMA_PERSON_ROOT_SALT_V1") or "").strip())

    if not column_encryption_active():
        print("FAIL: no column encryption key material configured", file=sys.stderr)
        return 1

    source = "LEMMA_COLUMN_ENCRYPTION_KEY" if explicit else "LEMMA_PERSON_ROOT_SALT_V1"
    if not explicit and not salt:
        print("FAIL: unexpected encryption active state", file=sys.stderr)
        return 1

    print(f"OK: column encryption active via {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
