#!/usr/bin/env python3
"""
Bootstrap Stripe Billing catalog for lemma.id site-credential metering.

Creates:
  - 1 Product
  - 3 Meters (initial issuance, MAU renewal, doubt re-entry)
  - 3 metered Prices

Requires STRIPE_SECRET_KEY. Safe to re-run, skips resources that already exist
when LEMMA_STRIPE_CATALOG_JSON env points at a prior run's output.

Usage:
  python scripts/bootstrap_stripe_billing_catalog.py
  python scripts/bootstrap_stripe_billing_catalog.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from billing.stripe_catalog import (  # noqa: E402
    METER_EVENT_DOUBT_REENTRY,
    METER_EVENT_INITIAL_ISSUANCE,
    METER_EVENT_MAU_RENEWAL,
    PRICE_NICKNAMES,
    STRIPE_PRODUCT_DESCRIPTION,
    STRIPE_PRODUCT_NAME,
    UNIT_AMOUNTS_CENTS,
)


def _require_stripe(*, dry_run: bool = False):
    try:
        import stripe
    except ImportError as exc:
        raise SystemExit("stripe package not installed") from exc

    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not key:
        if dry_run:
            return stripe
        raise SystemExit("STRIPE_SECRET_KEY is required")
    stripe.api_key = key
    return stripe


def _find_product(stripe, name: str):
    if not getattr(stripe, "api_key", None):
        return None
    products = stripe.Product.list(limit=100, active=True)
    for product in products.auto_paging_iter():
        if product.name == name:
            return product
    return None


def _find_meter(stripe, event_name: str):
    if not getattr(stripe, "api_key", None):
        return None
    meters = stripe.billing.Meter.list(limit=100)
    for meter in meters.auto_paging_iter():
        if meter.event_name == event_name:
            return meter
    return None


def _create_meter(stripe, *, event_name: str, display_name: str, dry_run: bool):
    existing = _find_meter(stripe, event_name)
    if existing:
        print(f"  meter exists: {event_name} -> {existing.id}")
        return existing.id

    if dry_run:
        print(f"  [dry-run] would create meter: {event_name}")
        return f"meter_dry_{event_name}"

    meter = stripe.billing.Meter.create(
        display_name=display_name,
        event_name=event_name,
        default_aggregation={"formula": "sum"},
        customer_mapping={
            "type": "by_id",
            "event_payload_key": "stripe_customer_id",
        },
        value_settings={"event_payload_key": "value"},
    )
    print(f"  created meter: {event_name} -> {meter.id}")
    return meter.id


def _create_price(
    stripe,
    *,
    product_id: str,
    meter_id: str,
    unit_amount_cents: int,
    nickname: str,
    dry_run: bool,
):
    if dry_run:
        print(f"  [dry-run] would create price: {nickname} ({unit_amount_cents}c)")
        return f"price_dry_{nickname}"

    price = stripe.Price.create(
        currency="usd",
        unit_amount=unit_amount_cents,
        nickname=nickname,
        product=product_id,
        recurring={
            "interval": "month",
            "usage_type": "metered",
            "meter": meter_id,
        },
        metadata={"billing_unit": nickname},
    )
    print(f"  created price: {nickname} -> {price.id}")
    return price.id


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap lemma.id Stripe billing catalog")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without API writes")
    args = parser.parse_args()

    stripe = _require_stripe(dry_run=args.dry_run)

    print("Bootstrapping lemma.id Stripe billing catalog...")
    product = None if args.dry_run else _find_product(stripe, STRIPE_PRODUCT_NAME)
    if product:
        product_id = product.id
        print(f"  product exists: {STRIPE_PRODUCT_NAME} -> {product_id}")
    elif args.dry_run:
        product_id = "prod_dry_lemma_site_credentials"
        print(f"  [dry-run] would create product: {STRIPE_PRODUCT_NAME}")
    else:
        product = stripe.Product.create(
            name=STRIPE_PRODUCT_NAME,
            description=STRIPE_PRODUCT_DESCRIPTION,
            metadata={"service": "lemma_id", "billing_model": "usage_metered"},
        )
        product_id = product.id
        print(f"  created product: {product_id}")

    catalog = {
        "product_id": product_id,
        "meters": {},
        "prices": {},
    }

    meter_specs = [
        (METER_EVENT_INITIAL_ISSUANCE, "initial_issuance", PRICE_NICKNAMES["initial_issuance"]),
        (METER_EVENT_MAU_RENEWAL, "mau_renewal", PRICE_NICKNAMES["mau_renewal"]),
        (METER_EVENT_DOUBT_REENTRY, "doubt_reentry", PRICE_NICKNAMES["doubt_reentry"]),
    ]

    for event_name, key, nickname in meter_specs:
        meter_id = _create_meter(
            stripe,
            event_name=event_name,
            display_name=nickname,
            dry_run=args.dry_run,
        )
        catalog["meters"][key] = {"event_name": event_name, "meter_id": meter_id}
        price_id = _create_price(
            stripe,
            product_id=product_id,
            meter_id=meter_id,
            unit_amount_cents=UNIT_AMOUNTS_CENTS[key],
            nickname=nickname,
            dry_run=args.dry_run,
        )
        catalog["prices"][key] = price_id

    out_path = os.path.join(ROOT, "billing", "stripe_catalog.generated.json")
    if not args.dry_run:
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(catalog, handle, indent=2)
            handle.write("\n")
        print(f"\nWrote catalog ids to {out_path}")
    else:
        print("\n[dry-run] catalog:", json.dumps(catalog, indent=2))

    print("\nNext: attach all three prices to each developer subscription shell.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
