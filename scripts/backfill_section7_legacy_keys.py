#!/usr/bin/env python3
"""Backfill Section 7 legacy plaintext secrets to hash-only / encrypted storage.

Idempotent operations:
1. Strip raw ``key`` / ``api_key`` fields from customers.api_keys JSON; ensure key_hash.
2. Upsert normalized api_keys rows for any hash discovered.
3. Replace legacy plaintext sites.api_key values with non-auth placeholders.
4. Encrypt plaintext oauth_client_secret values under KMS/column envelope.

Run on Heroku after deploy:
    heroku run python scripts/backfill_section7_legacy_keys.py --app lemma-enterprise
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _placeholder_site_api_key() -> str:
    return f"__hash_only__{secrets.token_hex(12)}"


def backfill_customer_json_keys(dry_run: bool = False) -> dict:
    from api.database import Customer as DBCustomer, get_db

    stats = {"customers_scanned": 0, "keys_scrubbed": 0, "keys_hashed": 0}
    db = get_db()
    try:
        rows = db.query(DBCustomer.customer_id, DBCustomer.api_keys).all()
        for customer_id, api_keys in rows:
            stats["customers_scanned"] += 1
            changed = False
            keys = list(api_keys or [])
            for key_data in keys:
                raw = key_data.pop("key", None) or key_data.pop("api_key", None)
                if raw:
                    stats["keys_scrubbed"] += 1
                    changed = True
                if not key_data.get("key_hash") and raw:
                    key_data["key_hash"] = _hash_api_key(str(raw))
                    stats["keys_hashed"] += 1
                    changed = True
                site_id = key_data.get("site_id")
                key_hash = key_data.get("key_hash")
                if (
                    not dry_run
                    and site_id
                    and key_hash
                    and key_data.get("status", "active") != "revoked"
                ):
                    from api.storage_helpers import upsert_api_key_to_postgres

                    upsert_api_key_to_postgres(
                        customer_id=customer_id,
                        site_id=site_id,
                        key_hash=key_hash,
                        key_hint=str(key_data.get("key_hint") or key_hash[:8]),
                        name=str(key_data.get("name") or "API Key"),
                    )
            if changed and not dry_run:
                customer = db.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).first()
                if customer:
                    customer.api_keys = keys
                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(customer, "api_keys")
        if not dry_run:
            db.commit()
    finally:
        db.close()
    return stats


def backfill_legacy_site_api_keys(dry_run: bool = False) -> dict:
    from api.api_key_rotation import is_legacy_plaintext_site_api_key
    from api.database import Site, get_db

    stats = {"sites_scanned": 0, "site_api_keys_replaced": 0, "hashes_backfilled": 0}
    db = get_db()
    try:
        for site in db.query(Site).all():
            stats["sites_scanned"] += 1
            raw = (site.api_key or "").strip()
            if not is_legacy_plaintext_site_api_key(raw):
                continue
            stats["hashes_backfilled"] += 1
            if dry_run:
                continue
            site.api_key = _placeholder_site_api_key()
            stats["site_api_keys_replaced"] += 1
        if not dry_run:
            db.commit()
    finally:
        db.close()
    return stats


def backfill_oauth_client_secrets(dry_run: bool = False) -> dict:
    from api.database import Site, get_db
    from api.oauth_client_secret_crypto import encrypt_oauth_client_secret, is_encrypted_oauth_client_secret

    stats = {"sites_scanned": 0, "oauth_secrets_encrypted": 0}
    db = get_db()
    try:
        for site in db.query(Site).all():
            stats["sites_scanned"] += 1
            stored = (site.oauth_client_secret or "").strip()
            if not stored or is_encrypted_oauth_client_secret(stored):
                continue
            if dry_run:
                stats["oauth_secrets_encrypted"] += 1
                continue
            site.oauth_client_secret = encrypt_oauth_client_secret(site.site_id, stored)
            stats["oauth_secrets_encrypted"] += 1
        if not dry_run:
            db.commit()
    finally:
        db.close()
    return stats


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    print("Section 7 legacy backfill", "(dry-run)" if dry_run else "")
    print("customer keys:", json.dumps(backfill_customer_json_keys(dry_run=dry_run), indent=2))
    print("site api_key:", json.dumps(backfill_legacy_site_api_keys(dry_run=dry_run), indent=2))
    print("oauth secrets:", json.dumps(backfill_oauth_client_secrets(dry_run=dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
