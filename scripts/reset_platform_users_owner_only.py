#!/usr/bin/env python3
"""Reset lemma.id platform registry to configured owner only."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.platform_account import upsert_platform_account
from api.platform_membership import is_probe_ppid
from api.platform_owner import normalize_ppid, platform_owner_ppid


def reset(*, keep_ppids: set[str], apply: bool) -> int:
    from api.database import Customer, PlatformUser, PlatformUserSite, SessionLocal, SiteAdmin

    db = SessionLocal()
    stats = {
        "platform_user_sites_removed": 0,
        "platform_users_removed": 0,
        "platform_users_downgraded": 0,
        "customers_removed": 0,
        "site_admins_deactivated": 0,
    }
    try:
        keep = {normalize_ppid(p) for p in keep_ppids if normalize_ppid(p)}
        if not keep:
            print("ERROR: no owner PPID to keep", file=sys.stderr)
            return 1

        for row in db.query(PlatformUserSite).all():
            raw_ppid = (row.user_did or "").strip()
            ppid = normalize_ppid(raw_ppid)
            if raw_ppid in keep or (ppid and ppid in keep):
                continue
            print(f"  remove platform_user_sites: {ppid[:32]}... site={row.site_id} role={row.role}")
            stats["platform_user_sites_removed"] += 1
            if apply:
                db.delete(row)

        for row in db.query(PlatformUser).all():
            raw_ppid = (row.user_did or "").strip()
            ppid = normalize_ppid(raw_ppid)
            if raw_ppid in keep or (ppid and ppid in keep):
                continue
            if is_probe_ppid(raw_ppid) or is_probe_ppid(ppid):
                print(f"  remove platform_users (probe): {ppid[:32]}...")
                stats["platform_users_removed"] += 1
                if apply:
                    db.delete(row)
                continue
            print(f"  remove platform_users: {ppid[:32]}... type={row.account_type} email={row.email}")
            stats["platform_users_removed"] += 1
            if apply:
                db.delete(row)

        for row in db.query(Customer).filter(Customer.customer_did.isnot(None)).all():
            ppid = normalize_ppid(row.customer_did)
            if not ppid or ppid in keep:
                continue
            print(f"  remove customers: {ppid[:32]}... email={row.email}")
            stats["customers_removed"] += 1
            if apply:
                db.delete(row)

        for row in db.query(SiteAdmin).filter(SiteAdmin.is_active == True).all():  # noqa: E712
            ppid = normalize_ppid(row.admin_did)
            if ppid in keep:
                continue
            print(f"  deactivate site_admins: {ppid[:32] if ppid else '?'}... site={row.site_id} role={row.admin_role}")
            stats["site_admins_deactivated"] += 1
            if apply:
                row.is_active = False
                row.last_activity = datetime.utcnow()

        for owner_ppid in sorted(keep):
            print(f"  ensure owner account: {owner_ppid[:32]}...")
            if apply:
                upsert_platform_account(
                    owner_ppid,
                    account_type="owner",
                    verification_level="human_verified",
                    site_id="lemma.id",
                    site_role="owner",
                    db=db,
                )
                upsert_platform_account(
                    owner_ppid,
                    site_id="lemma_platform",
                    site_role="owner",
                    db=db,
                )

        if apply:
            db.commit()
            print("Reset applied.")
        else:
            db.rollback()
            print("Dry run only, no changes committed.")
    except Exception as exc:
        db.rollback()
        print(f"ERROR: reset failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print("Summary:", stats)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset platform users to owner only")
    parser.add_argument("--keep-ppid", action="append", default=[], help="PPID to preserve")
    parser.add_argument("--apply", action="store_true", help="Persist changes")
    args = parser.parse_args()

    keep = set(args.keep_ppid)
    owner = platform_owner_ppid() or os.getenv("LEMMA_PLATFORM_OWNER_PPID", "")
    if owner:
        keep.add(owner)
    if not keep:
        print("ERROR: set LEMMA_PLATFORM_OWNER_PPID or pass --keep-ppid", file=sys.stderr)
        return 1

    print("lemma.id platform user reset (owner only)")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    return reset(keep_ppids=keep, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
