"""
Stripe Billing catalog constants for lemma.id site-credential metering.

Three metered events, aligned with the public pricing page
(templates/modern/pricing_new.html):
  - initial issuance ($0.83 = $0.33 IDV pass-through at cost + $0.50 one-time
    lemma.id proof binding)
  - MAU renewal ($0.03/user/month, starting the month after binding)
  - doubt re-entry after an active site doubt ($0.33 — fresh IDV passed
    through at cost, never marked up)

Site blocks, hard bans, and local verification never emit meter events.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

# Stripe Billing Meter event_name values (must match Dashboard / bootstrap script).
METER_EVENT_INITIAL_ISSUANCE = "lemma.initial_issuance"
METER_EVENT_MAU_RENEWAL = "lemma.mau_renewal"
METER_EVENT_DOUBT_REENTRY = "lemma.doubt_reentry"

METER_EVENTS: Dict[str, str] = {
    "initial_issuance": METER_EVENT_INITIAL_ISSUANCE,
    "mau_renewal": METER_EVENT_MAU_RENEWAL,
    "doubt_reentry": METER_EVENT_DOUBT_REENTRY,
}

# Unit amounts in cents (USD). Must match the public pricing page.
# initial_issuance = $0.33 IDV pass-through + $0.50 proof binding.
UNIT_AMOUNTS_CENTS: Dict[str, int] = {
    "initial_issuance": 83,
    "mau_renewal": 3,
    "doubt_reentry": 33,
}

STRIPE_PRODUCT_NAME = "Lemma.id — Site Credentials"
STRIPE_PRODUCT_DESCRIPTION = (
    "Per-site human credential issuance, monthly continuity renewals, "
    "and doubt re-entry after an active site doubt."
)

PRICE_NICKNAMES: Dict[str, str] = {
    "initial_issuance": "Initial site credential (IDV + binding) — $0.83/user/site",
    "mau_renewal": "MAU renewal — $0.03/user/month",
    "doubt_reentry": "Doubt re-entry (fresh IDV at cost) — $0.33/user",
}

CATALOG_KEYS = ("initial_issuance", "mau_renewal", "doubt_reentry")

_GENERATED_CATALOG_PATH = Path(__file__).resolve().parent / "stripe_catalog.generated.json"


def load_catalog_price_ids() -> Dict[str, Optional[str]]:
    """Resolve Stripe Price ids from env vars or bootstrap output file."""
    env_map = {
        "initial_issuance": os.getenv("LEMMA_STRIPE_PRICE_INITIAL_ISSUANCE"),
        "mau_renewal": os.getenv("LEMMA_STRIPE_PRICE_MAU_RENEWAL"),
        "doubt_reentry": os.getenv("LEMMA_STRIPE_PRICE_DOUBT_REENTRY"),
    }
    if all(env_map.values()):
        return env_map

    if _GENERATED_CATALOG_PATH.is_file():
        try:
            payload = json.loads(_GENERATED_CATALOG_PATH.read_text(encoding="utf-8"))
            prices = payload.get("prices") or {}
            for key in CATALOG_KEYS:
                if not env_map.get(key) and prices.get(key):
                    env_map[key] = prices[key]
        except (OSError, json.JSONDecodeError):
            pass
    return env_map


def catalog_prices_configured() -> bool:
    ids = load_catalog_price_ids()
    return all(ids.get(key) for key in CATALOG_KEYS)

