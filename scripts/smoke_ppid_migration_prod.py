#!/usr/bin/env python3
"""Production smoke for PPID migration confirm (run on Heroku)."""

from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")


def main() -> int:
    from api.database import SessionLocal
    from api.ppid_migration import confirm_ppid_migration_for_site

    db = SessionLocal()
    try:
        result = confirm_ppid_migration_for_site(
            db,
            target_site="lemma.id",
            legacy_ppid="did:lemma:ppid_" + ("a" * 64),
            current_ppid="did:lemma:ppid_" + ("b" * 64),
        )
        print(json.dumps({"smoke": "confirm_unapproved_pair", **result}))
        if result.get("approved"):
            print("FAIL: expected not_approved for synthetic pair", file=sys.stderr)
            return 1
        print("OK: synthetic pair correctly not approved")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
