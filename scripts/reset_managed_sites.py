#!/usr/bin/env python3
"""Keep only managed platform/demo sites in the sites table."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.platform_sites import MANAGED_SITE_IDS, normalize_site_id


def reset(*, apply: bool) -> int:
    import psycopg2

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 1
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    keep = {normalize_site_id(s) for s in MANAGED_SITE_IDS}
    conn = psycopg2.connect(db_url, sslmode="require")
    removed = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT site_id FROM sites ORDER BY site_id")
            rows = [r[0] for r in cur.fetchall()]
            for site_id in rows:
                if normalize_site_id(site_id) in keep:
                    print(f"  keep site: {site_id}")
                    continue
                print(f"  remove site: {site_id}")
                removed += 1
                if apply:
                    cur.execute("DELETE FROM sites WHERE site_id = %s", (site_id,))
        if apply:
            conn.commit()
            print("Managed sites reset applied.")
        else:
            conn.rollback()
            print("Dry run only — no changes committed.")
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"Summary: removed={removed}, kept={sorted(keep)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset sites table to managed platform/demo sites")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print("Managed sites reset")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    return reset(apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
