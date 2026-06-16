#!/usr/bin/env python3
"""Seed a demo route with fake packages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app


def main() -> None:
    client = app.test_client()
    payload = {
        "route_id": "R-001",
        "driver_id": "D-42",
        "device_id": "DEVICE-001",
        "package_count": 20,
        "stops": ["S-014", "S-015", "S-016"],
        "photo_required": True,
        "signature_required": False,
        "otp_required": False,
        "expires_hours": 12,
    }
    res = client.post("/api/routes", json=payload)
    data = res.get_json()
    if res.status_code != 200:
        print("Failed:", data)
        sys.exit(1)
    print(f"Seeded route {data['route_id']} with {len(data.get('packages', []))} packages")
    out = ROOT / "data" / "seed_route.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Saved bundle snapshot to {out}")


if __name__ == "__main__":
    main()
