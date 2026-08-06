#!/usr/bin/env python3
"""Verify identity-root pepper/salt restore without touching production.

Usage:
  # After restoring env vars from backup into a throwaway shell:
  python scripts/identity_root_backup_drill.py --verify

  # Print the fixed test vector (store with your backup archive):
  python scripts/identity_root_backup_drill.py --print-expected

  # Custom pepper/salt (flags override env):
  python scripts/identity_root_backup_drill.py --verify \\
    --pepper-v1 <hex-or-string> --salt-v1 <hex-or-string>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fixed claims vector — no production PII. Matches tests/test_identity_root_versioning.py.
DRILL_CLAIMS = {
    "schema": "lemma.identity.document-root.v1",
    "provider": "stripe_identity",
    "country": "US",
    "document_type": "driving_license",
    "document_number": "D1234567",
    "date_of_birth": "1985-03-12",
}

# Expected outputs with drill pepper/salt (40-char placeholders from unit tests).
DRILL_PEPPER = "A" * 40
DRILL_SALT = "C" * 40
DRILL_SITE = "app.example.com"


def _derive_with_pepper_salt(pepper: str, salt: str) -> dict[str, str]:
    from api.identity_roots import (
        derive_document_root_hash,
        derive_person_root_hash,
        derive_ppid_from_person_root_bytes,
        derive_person_root_bytes,
    )

    doc = derive_document_root_hash(DRILL_CLAIMS, version="V1")
    person_hash = derive_person_root_hash(doc, version="V1")
    person_bytes = derive_person_root_bytes(doc, version="V1")
    ppid = derive_ppid_from_person_root_bytes(person_bytes, DRILL_SITE)
    return {
        "document_root": doc,
        "person_root": person_hash,
        "site_ppid": ppid,
        "pepper_len": len(pepper),
        "salt_len": len(salt),
    }



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Derive drill vector from current env and compare to expected",
    )
    parser.add_argument(
        "--print-expected",
        action="store_true",
        help="Print expected document_root / person_root / site_ppid for drill pepper/salt",
    )
    parser.add_argument("--pepper-v1", help="Override LEMMA_IDENTITY_ROOT_PEPPER_V1")
    parser.add_argument("--salt-v1", help="Override LEMMA_PERSON_ROOT_SALT_V1")
    parser.add_argument("--site", default=DRILL_SITE, help="Sample site hostname for PPID")
    args = parser.parse_args()

    if not args.verify and not args.print_expected:
        parser.error("Specify --verify or --print-expected")

    if args.pepper_v1:
        os.environ["LEMMA_IDENTITY_ROOT_PEPPER_V1"] = args.pepper_v1
    if args.salt_v1:
        os.environ["LEMMA_PERSON_ROOT_SALT_V1"] = args.salt_v1

    if args.print_expected:
        os.environ["LEMMA_IDENTITY_ROOT_PEPPER_V1"] = DRILL_PEPPER
        os.environ["LEMMA_PERSON_ROOT_SALT_V1"] = DRILL_SALT
        os.environ["LEMMA_ACTIVE_ROOT_VERSION"] = "V1"
        expected = _derive_with_pepper_salt(DRILL_PEPPER, DRILL_SALT)
        print(json.dumps(expected, indent=2, sort_keys=True))
        return 0

    # --verify: use env (restored backup), not drill placeholders unless unset
    pepper = args.pepper_v1 or os.environ.get("LEMMA_IDENTITY_ROOT_PEPPER_V1", "")
    salt = args.salt_v1 or os.environ.get("LEMMA_PERSON_ROOT_SALT_V1", "")
    if args.pepper_v1:
        os.environ["LEMMA_IDENTITY_ROOT_PEPPER_V1"] = args.pepper_v1
    if args.salt_v1:
        os.environ["LEMMA_PERSON_ROOT_SALT_V1"] = args.salt_v1
    os.environ.setdefault("LEMMA_ACTIVE_ROOT_VERSION", "V1")

    if len(pepper) < 32 or len(salt) < 32:
        print(
            "ERROR: LEMMA_IDENTITY_ROOT_PEPPER_V1 and LEMMA_PERSON_ROOT_SALT_V1 "
            "must be set (>= 32 bytes each) for --verify",
            file=sys.stderr,
        )
        return 1

    try:
        actual = _derive_with_pepper_salt(pepper, salt)
    except Exception as exc:
        print(f"ERROR: derivation failed: {exc}", file=sys.stderr)
        return 1

    print("document_root:", actual["document_root"])
    print("person_root:", actual["person_root"])
    print("site_ppid:", actual["site_ppid"])
    print("pepper_bytes:", actual["pepper_len"])
    print("salt_bytes:", actual["salt_len"])

    if pepper == DRILL_PEPPER and salt == DRILL_SALT:
        os.environ["LEMMA_IDENTITY_ROOT_PEPPER_V1"] = DRILL_PEPPER
        os.environ["LEMMA_PERSON_ROOT_SALT_V1"] = DRILL_SALT
        expected = _derive_with_pepper_salt(DRILL_PEPPER, DRILL_SALT)
        if (
            actual["document_root"] == expected["document_root"]
            and actual["person_root"] == expected["person_root"]
            and actual["site_ppid"] == expected["site_ppid"]
        ):
            print("RESTORE_DRILL_OK")
            return 0
        print("RESTORE_DRILL_MISMATCH", file=sys.stderr)
        return 1

    print(
        "RESTORE_DRILL_OK (derivation succeeded; compare output to your stored drill record)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
