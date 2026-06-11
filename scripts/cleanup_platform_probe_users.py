#!/usr/bin/env python3
"""Remove legacy probe/orphan platform users; keep configured platform owner only."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.platform_membership import collect_registered_platform_ppids, is_probe_ppid
from api.platform_owner import normalize_ppid, platform_owner_ppid


def cleanup(*, keep_ppids: set[str], apply: bool) -> int:
    from api.database import Customer, PlatformUser, PlatformUserSite, SessionLocal, SiteAdmin

    db = SessionLocal()
    stats = {
        "platform_user_sites_removed": 0,
        "platform_users_removed": 0,
        "customers_removed": 0,
        "site_admins_deactivated": 0,
    }
    try:
        keep = {normalize_ppid(p) for p in keep_ppids if normalize_ppid(p)}

        pus_rows = db.query(PlatformUserSite).all()
        for row in pus_rows:
            ppid = normalize_ppid(row.user_did)
            if not ppid:
                continue
            if ppid in keep:
                continue
            if is_probe_ppid(ppid) or ppid not in collect_registered_platform_ppids(db=db):
                print(f"  remove platform_user_sites: {ppid[:32]}... site={row.site_id} role={row.role}")
                stats["platform_user_sites_removed"] += 1
                if apply:
                    db.delete(row)

        pu_rows = db.query(PlatformUser).all()
        for row in pu_rows:
            ppid = normalize_ppid(row.user_did)
            if not ppid:
                continue
            if ppid in keep:
                continue
            remaining = (
                db.query(PlatformUserSite)
                .filter(PlatformUserSite.user_did == ppid)
                .count()
            )
            if remaining == 0 or is_probe_ppid(ppid):
                print(f"  remove platform_users: {ppid[:32]}... email={row.email}")
                stats["platform_users_removed"] += 1
                if apply:
                    db.delete(row)

        cust_rows = db.query(Customer).filter(Customer.customer_did.isnot(None)).all()
        for row in cust_rows:
            ppid = normalize_ppid(row.customer_did)
            if not ppid or ppid in keep:
                continue
            if is_probe_ppid(ppid) or ppid not in collect_registered_platform_ppids(db=db):
                print(f"  remove customers: {ppid[:32]}... email={row.email}")
                stats["customers_removed"] += 1
                if apply:
                    db.delete(row)

        admin_rows = db.query(SiteAdmin).filter(SiteAdmin.is_active == True).all()  # noqa: E712
        for row in admin_rows:
            ppid = normalize_ppid(row.admin_did)
            if not ppid or ppid in keep:
                continue
            if is_probe_ppid(ppid):
                print(f"  deactivate site_admins: {ppid[:32]}... site={row.site_id}")
                stats["site_admins_deactivated"] += 1
                if apply:
                    row.is_active = False
                    row.last_activity = datetime.utcnow()

        if apply:
            db.commit()
            print("Cleanup applied.")
        else:
            db.rollback()
            print("Dry run only — no changes committed.")
    except Exception as exc:
        db.rollback()
        print(f"ERROR: cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print("Summary:", stats)
    print("Kept PPIDs:", ", ".join(sorted(keep)[:3]) + ("..." if len(keep) > 3 else ""))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove probe/orphan lemma.id platform users")
    parser.add_argument(
        "--keep-ppid",
        action="append",
        default=[],
        help="PPID to preserve (repeatable). Defaults to LEMMA_PLATFORM_OWNER_PPID.",
    )
    parser.add_argument(
        "--include-registered",
        action="store_true",
        help="Also keep developer/admin customers and site_admins (default: owner only).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist removals (default is dry-run).",
    )
    args = parser.parse_args()

    keep = set(args.keep_ppid)
    owner = platform_owner_ppid() or os.getenv("LEMMA_PLATFORM_OWNER_PPID", "")
    if owner:
        keep.add(owner)

    if args.include_registered:
        keep.update(collect_registered_platform_ppids())

    if not keep:
        print("ERROR: no keep PPID configured; set LEMMA_PLATFORM_OWNER_PPID or pass --keep-ppid", file=sys.stderr)
        return 1

    print("lemma.id platform user cleanup")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    return cleanup(keep_ppids=keep, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
