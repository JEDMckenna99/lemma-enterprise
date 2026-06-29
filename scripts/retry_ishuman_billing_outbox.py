"""Retry pending privacy-safe isHuman Stripe meter events."""

import argparse

from api.database import SessionLocal
from billing.credential_billing import retry_pending_billing_outbox


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = retry_pending_billing_outbox(db, limit=args.limit)
        for key in ("selected", "reported", "failed"):
            print(f"{key}={result[key]}")
        return 0 if result["failed"] == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
