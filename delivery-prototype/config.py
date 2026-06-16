"""Delivery prototype configuration."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Heroku dynos have an ephemeral filesystem; keep mutable data on /tmp there.
_ON_HEROKU = bool(os.getenv("DYNO"))
_DEFAULT_DATA = Path("/tmp/delivery-prototype") if _ON_HEROKU else ROOT / "data"
DATA_DIR = Path(os.getenv("DELIVERY_DATA_DIR", str(_DEFAULT_DATA)))
KEYS_DIR = DATA_DIR / "keys"
DB_PATH = Path(os.getenv("DELIVERY_DB_PATH", str(DATA_DIR / "delivery_prototype.db")))
BENCHMARK_DIR = DATA_DIR / "benchmark_results"

FAKE_DATA_ONLY = os.getenv("DELIVERY_PROTOTYPE_FAKE_DATA_ONLY", "1") == "1"
ISSUER_KEY_PATH = KEYS_DIR / "issuer_private.pem"
DEVICE_KEY_PATH = KEYS_DIR / "device_private.pem"

# Optional hex overrides (recommended on Heroku so signing keys survive dyno restarts).
ISSUER_KEY_HEX = os.getenv("DELIVERY_ISSUER_KEY_HEX", "").strip()
DEVICE_KEY_HEX = os.getenv("DELIVERY_DEVICE_KEY_HEX", "").strip()

CLOUD_DELAYS = {
    "good": 0.5,
    "weak": 3.0,
    "bad": 8.0,
    "timeout": 30.0,
    "offline": None,
}

DELAY_BUCKET_SECONDS = {
    "0-2_sec": 1,
    "3-5_sec": 4,
    "6-10_sec": 8,
    "10-20_sec": 15,
    "20+_sec": 25,
    "failed_retry": 20,
}

SENSITIVE_FIELD_PATTERNS = (
    "package_id",
    "tracking",
    "address",
    "customer",
    "photo",
    "gps",
    "access_code",
    "tba",
)
