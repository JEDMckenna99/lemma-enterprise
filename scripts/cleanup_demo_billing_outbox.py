"""Mark legacy pending demo-site outbox rows as non-billable dead letters."""

from __future__ import annotations

import argparse
from datetime import datetime

from api.database import IsHumanBillingOutbox, SessionLocal
from api.platform_sites import is_demo_site


def cleanup_demo_pending_outbox(*, dry_run: bool = True) -> dict[str, int]:
    db = SessionLocal()
    try:
        rows = db.query(IsHumanBillingOutbox).filter_by(status="pending").all()
        targets = [row for row in rows if is_demo_site(row.site_scope)]
        if not dry_run:
            now = datetime.utcnow()
            for row in targets:
                row.status = "dead_letter"
                row.last_error = "demo_legacy_not_billable"
                row.next_attempt_at = None
                row.reported_at = None
            if targets:
                db.commit()
        return {
            "pending_scanned": len(rows),
            "demo_pending_selected": len(targets),
            "updated": 0 if dry_run else len(targets),
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist changes (default is dry-run)")
    args = parser.parse_args()
    stats = cleanup_demo_pending_outbox(dry_run=not args.apply)
    mode = "dry_run" if not args.apply else "applied"
    print(f"mode={mode} pending_scanned={stats['pending_scanned']} demo_pending_selected={stats['demo_pending_selected']} updated={stats['updated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
