"""Idempotent maintenance-window cutover for privacy-minimized isHuman state."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime


def _site_scope(db, target_site: str) -> str:
    from billing.credential_billing import resolve_billing_site_key
    return resolve_billing_site_key(db, target_site)


def run(*, commit: bool, import_redis: bool = True) -> dict:
    from api.column_crypto import decrypt_column
    from api.database import (
        IsHumanSiteMonthlyUsage,
        IsHumanSiteBillingSubject,
        LemmaPerson,
        SessionLocal,
    )
    from api.person_root_crypto import decrypt_person_root, encrypt_person_root, is_kms_person_root
    from api.usage_tracking import REDIS_AVAILABLE, _hash_ppid_for_mau, redis_client
    from sqlalchemy import text

    db = SessionLocal()
    summary = defaultdict(int)
    try:
        issuance_bounds: dict[tuple[str, str], tuple[datetime, datetime]] = {}
        legacy_rows = db.execute(text(
            "SELECT target_site, derived_ppid, created_at FROM derived_credentials"
        )).mappings().all()
        for row in legacy_rows:
            scope = _site_scope(db, row["target_site"])
            token = _hash_ppid_for_mau(row["derived_ppid"])
            key = (scope, token)
            created = row["created_at"] or datetime.utcnow()
            if key not in issuance_bounds:
                issuance_bounds[key] = (created, created)
            else:
                first, last = issuance_bounds[key]
                issuance_bounds[key] = (min(first, created), max(last, created))
        summary["legacy_derived_rows"] = len(legacy_rows)

        for (scope, token), (first_created, last_created) in issuance_bounds.items():
            existing = db.query(IsHumanSiteBillingSubject).filter_by(
                site_scope=scope, subject_token=token,
            ).first()
            if existing:
                summary["subjects_existing"] += 1
                if commit:
                    existing.first_issued_at = min(existing.first_issued_at, first_created)
                    existing.first_issuance_month = existing.first_issued_at.strftime("%Y-%m")
                    existing.last_issued_at = max(existing.last_issued_at, last_created)
                continue
            summary["subjects_to_create"] += 1
            if commit:
                db.add(IsHumanSiteBillingSubject(
                    site_scope=scope,
                    subject_token=token,
                    first_issuance_month=first_created.strftime("%Y-%m"),
                    first_issued_at=first_created,
                    last_issued_at=last_created,
                ))

        if import_redis and REDIS_AVAILABLE:
            deployment_month = datetime.utcnow().strftime("%Y-%m")
            for raw_key in redis_client.scan_iter(match=f"mau:*:{deployment_month}"):
                key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
                _prefix, scope, month = key.split(":", 2)
                for raw_token in redis_client.smembers(raw_key):
                    token = raw_token.decode() if isinstance(raw_token, bytes) else str(raw_token)
                    existing = db.query(IsHumanSiteMonthlyUsage).filter_by(
                        site_scope=scope, month=month, subject_token=token,
                    ).first()
                    if existing:
                        summary["monthly_existing"] += 1
                    else:
                        summary["monthly_to_create"] += 1
                        if commit:
                            db.add(IsHumanSiteMonthlyUsage(
                                site_scope=scope, month=month,
                                subject_token=token, first_seen_at=datetime.utcnow(),
                            ))

        for person in db.query(LemmaPerson).all():
            if is_kms_person_root(person.person_root_hash):
                if commit:
                    decrypted = decrypt_person_root(person.person_id, person.person_root_hash)
                    if not isinstance(decrypted, str) or len(decrypted) != 64:
                        raise RuntimeError(f"KMS round-trip failed for {person.person_id}")
                summary["kms_roots_existing"] += 1
                continue
            root_hex = decrypt_column(person.person_root_hash)
            if not isinstance(root_hex, str) or len(root_hex) != 64:
                raise RuntimeError(f"invalid legacy person root for {person.person_id}")
            summary["kms_roots_to_encrypt"] += 1
            if commit:
                encrypted = encrypt_person_root(person.person_id, root_hex)
                if not is_kms_person_root(encrypted):
                    raise RuntimeError("KMS encryption did not return kms1 envelope")
                if decrypt_person_root(person.person_id, encrypted) != root_hex:
                    raise RuntimeError(f"KMS round-trip mismatch for {person.person_id}")
                person.person_root_hash = encrypted

        if commit:
            if import_redis and REDIS_AVAILABLE:
                db.flush()
                db.execute(text("""
                    INSERT INTO ishuman_site_usage_aggregates
                        (site_scope, month, active_subjects, initial_issuances,
                         mau_renewals, doubt_reentries, updated_at)
                    SELECT site_scope, month, COUNT(*), 0, 0, 0, NOW()
                    FROM ishuman_site_monthly_usage
                    WHERE month = :month
                    GROUP BY site_scope, month
                    ON CONFLICT (site_scope, month) DO UPDATE
                    SET active_subjects = EXCLUDED.active_subjects,
                        updated_at = NOW()
                """), {"month": deployment_month})
            db.commit()
            remaining = db.query(LemmaPerson).filter(
                ~LemmaPerson.person_root_hash.like("kms1:%")
            ).count()
            if remaining:
                raise RuntimeError(f"{remaining} person roots remain outside KMS")
        else:
            db.rollback()
        summary["committed"] = int(commit)
        return dict(summary)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="persist the cutover")
    parser.add_argument("--skip-redis", action="store_true")
    args = parser.parse_args()
    result = run(commit=args.commit, import_redis=not args.skip_redis)
    for key in sorted(result):
        print(f"{key}={result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
