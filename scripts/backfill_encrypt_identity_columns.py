#!/usr/bin/env python3
"""Encrypt legacy plaintext identity-linkage columns in place.

Migration 029 widened the columns and the app now AES-GCM encrypts them on
write (api.column_crypto). Rows written before the cutover still hold legacy
64-hex plaintext. This script upgrades them so a DB dump never reveals the
PPID-enumeration key for already-verified people.

Idempotent: already-encrypted values (``lc1:`` envelope) are skipped. Requires
the same key material as the running app (LEMMA_COLUMN_ENCRYPTION_KEY or
LEMMA_PERSON_ROOT_SALT_V1); aborts if no key is configured so it cannot silently
no-op in production.

Run on Heroku:
    heroku run python scripts/backfill_encrypt_identity_columns.py --app lemma-enterprise
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_backfill() -> None:
    from api.column_crypto import _column_key, encrypt_column, is_encrypted
    from api.database import IsHumanVerification, LemmaPerson, get_db

    if not _column_key():
        raise SystemExit(
            "no column-encryption key configured "
            "(set LEMMA_COLUMN_ENCRYPTION_KEY or LEMMA_PERSON_ROOT_SALT_V1); aborting"
        )

    db = get_db()
    updated = {"lemma_persons": 0, "ishuman_verifications": 0}
    try:
        for person in db.query(LemmaPerson).all():
            value = person.person_root_hash
            if value and not is_encrypted(value):
                person.person_root_hash = encrypt_column(value)
                updated["lemma_persons"] += 1

        for row in db.query(IsHumanVerification).all():
            value = row.document_root_hash
            if value and not is_encrypted(value):
                row.document_root_hash = encrypt_column(value)
                updated["ishuman_verifications"] += 1

        db.commit()
        print(f"backfill complete: {updated}")
    except Exception as exc:
        db.rollback()
        print(f"backfill failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_backfill()
