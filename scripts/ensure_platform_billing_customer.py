#!/usr/bin/env python3
"""
Ensure the platform owner has a lemma customers row and Stripe customer for billing.

Run on Heroku after billing deploy:
  heroku run python scripts/ensure_platform_billing_customer.py --apply -a lemma-enterprise
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.platform_owner import normalize_ppid, platform_owner_ppid  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision platform owner billing customer")
    parser.add_argument(
        "--owner-ppid",
        default=platform_owner_ppid() or os.getenv("LEMMA_PLATFORM_OWNER_PPID", ""),
    )
    parser.add_argument(
        "--email",
        default=os.getenv("LEMMA_ADMIN_EMAIL", "") or os.getenv("LEMMA_BILLING_OWNER_EMAIL", ""),
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    owner = normalize_ppid(args.owner_ppid)
    if not owner:
        print("ERROR: set LEMMA_PLATFORM_OWNER_PPID or pass --owner-ppid", file=sys.stderr)
        return 1

    from api.database import PlatformUser, SessionLocal
    from billing.billing_customer import ensure_billing_customer, link_customer_to_site

    db = SessionLocal()
    try:
        account = db.query(PlatformUser).filter_by(user_did=owner).first()
        email = (args.email or getattr(account, "email", None) or "").strip().lower()
        if not email:
            print("ERROR: pass --email or set LEMMA_ADMIN_EMAIL / owner platform_users.email", file=sys.stderr)
            return 1

        if not args.apply:
            print(f"[dry-run] would ensure billing customer for {owner[:32]}... email={email}")
            return 0

        customer = ensure_billing_customer(
            db,
            ppid=owner,
            email=email,
            name=getattr(account, "display_name", None) or getattr(account, "name", None),
            company=getattr(account, "company", None),
            wallet_id=getattr(account, "wallet_id", None),
        )
        if not customer:
            print("ERROR: failed to provision billing customer", file=sys.stderr)
            return 1

        site_domain = "lemma.id"
        site_id = f"site_{hashlib.sha256(site_domain.encode()).hexdigest()[:12]}"
        link_customer_to_site(
            db,
            customer_id=customer.customer_id,
            site_id=site_id,
            site_domain=site_domain,
            admin_email=email,
            company_name="Lemma.id Platform",
        )

        print("Billing customer ready:")
        print(f"  customer_id:       {customer.customer_id}")
        print(f"  email:             {customer.email}")
        print(f"  stripe_customer_id:{customer.stripe_customer_id or '(pending — complete Checkout)'}")
        print(f"  subscription:      {customer.subscription_status}")
        print(f"  anchor site:       {site_id} ({site_domain})")
        print("Next: open https://lemma.id/developer/billing and complete Stripe Checkout.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
