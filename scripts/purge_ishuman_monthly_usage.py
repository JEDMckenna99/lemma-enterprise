"""Delete expired subject-level isHuman MAU rows; retain aggregates."""

from api.database import SessionLocal
from billing.credential_billing import purge_monthly_subject_usage


def main() -> int:
    db = SessionLocal()
    try:
        deleted = purge_monthly_subject_usage(db)
        print(f"deleted_monthly_subject_rows={deleted}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
