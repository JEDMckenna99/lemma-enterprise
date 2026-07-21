"""Reconcile internal billing aggregates with outbox reporting state."""

from __future__ import annotations

import argparse
import json

from api.database import SessionLocal
from billing.billing_reconcile import reconcile_billing_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        report = reconcile_billing_state(db)
        payload = report.to_dict()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"ok={payload['ok']} scanned={payload['scanned_site_months']} issues={payload['issue_count']}")
            for issue in payload["issues"]:
                print(f"- {issue['code']} {issue['site_scope']} {issue['month']}: {issue['detail']}")
        return 0 if report.ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
