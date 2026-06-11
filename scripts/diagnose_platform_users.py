#!/usr/bin/env python3
"""Print platform user registry state (diagnostic)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import PlatformUser, PlatformUserSite, SessionLocal, SiteAdmin
from api.platform_membership import collect_registered_platform_ppids, list_registered_platform_user_rows
from api.platform_owner import platform_owner_ppid


def main() -> int:
    db = SessionLocal()
    owner = platform_owner_ppid() or os.getenv("LEMMA_PLATFORM_OWNER_PPID", "")
    print("OWNER", (owner or "")[:48])
    print("--- platform_users (member account_type) ---")
    for row in db.query(PlatformUser).all():
        account_type = (row.account_type or "").lower()
        if account_type in {"developer", "dev", "admin", "owner", "super_admin", "platform_admin"}:
            print(account_type, (row.user_did or "")[:40], row.email)
    print("--- site_admins active (lemma.id / lemma_platform) ---")
    for row in (
        db.query(SiteAdmin)
        .filter(
            SiteAdmin.is_active == True,  # noqa: E712
            SiteAdmin.site_id.in_(["lemma.id", "lemma_platform"]),
        )
        .all()
    ):
        print(row.site_id, (row.admin_did or "")[:40], row.admin_role, row.admin_email)
    print("--- platform_user_sites (lemma.id) ---")
    for row in db.query(PlatformUserSite).filter(PlatformUserSite.site_id == "lemma.id").all():
        print((row.user_did or "")[:40], row.role, row.status)
    print("--- registered ---")
    print("count", len(collect_registered_platform_ppids(db=db)))
    for item in list_registered_platform_user_rows(db=db):
        print(item.get("role"), (item.get("ppid") or "")[:40], item.get("email"), item.get("source"))
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
