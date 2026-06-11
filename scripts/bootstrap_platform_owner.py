#!/usr/bin/env python3
"""Bootstrap lemma.id platform admin to a single person-root owner PPID."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.platform_owner import normalize_ppid, platform_owner_ppid


def bootstrap(owner_ppid: str, admin_email: str | None = None) -> int:
    owner = normalize_ppid(owner_ppid)
    if not owner:
        print("ERROR: invalid owner PPID (expected did:lemma:ppid_<64-hex>)", file=sys.stderr)
        return 1

    from api.database import PlatformUserSite, SessionLocal, SiteAdmin
    from api.platform_account import ensure_owner_account

    db = SessionLocal()
    deactivated = 0
    try:
        for site_id in ("lemma.id", "lemma_platform"):
            rows = (
                db.query(SiteAdmin)
                .filter(SiteAdmin.site_id == site_id, SiteAdmin.is_active == True)  # noqa: E712
                .all()
            )
            for row in rows:
                if row.admin_did != owner:
                    row.is_active = False
                    deactivated += 1

            existing = (
                db.query(SiteAdmin)
                .filter(SiteAdmin.site_id == site_id, SiteAdmin.admin_did == owner)
                .first()
            )
            email = admin_email or os.getenv("LEMMA_ADMIN_EMAIL", "admin@lemma.id")
            if existing:
                existing.admin_email = email
                existing.admin_role = "owner"
                existing.is_active = True
                existing.last_activity = datetime.utcnow()
            else:
                db.add(
                    SiteAdmin(
                        site_id=site_id,
                        admin_did=owner,
                        admin_email=email,
                        admin_role="owner",
                        permissions=["users", "permissions", "billing"],
                        added_by="bootstrap_platform_owner",
                        is_active=True,
                        last_activity=datetime.utcnow(),
                    )
                )

            membership = (
                db.query(PlatformUserSite)
                .filter(PlatformUserSite.site_id == site_id, PlatformUserSite.user_did == owner)
                .order_by(PlatformUserSite.id.desc())
                .first()
            )
            if membership:
                membership.role = "owner"
                membership.status = "active"
            else:
                db.add(
                    PlatformUserSite(
                        user_did=owner,
                        site_id=site_id,
                        role="owner",
                        status="active",
                        joined_at=datetime.utcnow(),
                    )
                )

        ensure_owner_account(owner, email=admin_email or os.getenv("LEMMA_ADMIN_EMAIL", "admin@lemma.id"), db=db)

        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"ERROR: bootstrap failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Platform owner bootstrapped: {owner[:32]}...")
    print(f"Deactivated non-owner site_admins rows: {deactivated}")
    print("Set LEMMA_PLATFORM_OWNER_PPID to this value on Heroku if not already set.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap lemma.id platform owner admin PPID")
    parser.add_argument(
        "--owner-ppid",
        default=platform_owner_ppid() or os.getenv("LEMMA_PLATFORM_OWNER_PPID", ""),
        help="Person-root PPID for lemma.id (defaults to LEMMA_PLATFORM_OWNER_PPID env)",
    )
    parser.add_argument(
        "--admin-email",
        default=os.getenv("LEMMA_ADMIN_EMAIL", ""),
        help="Admin email stored on site_admins (defaults to LEMMA_ADMIN_EMAIL env)",
    )
    args = parser.parse_args()
    if not args.owner_ppid:
        print("ERROR: --owner-ppid or LEMMA_PLATFORM_OWNER_PPID required", file=sys.stderr)
        return 1
    return bootstrap(args.owner_ppid, args.admin_email or None)


if __name__ == "__main__":
    raise SystemExit(main())
