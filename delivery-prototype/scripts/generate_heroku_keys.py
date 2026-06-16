#!/usr/bin/env python3
"""Print DELIVERY_*_KEY_HEX values for Heroku config vars."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from crypto.device_keys import private_key_to_hex


def main() -> None:
    issuer = Ed25519PrivateKey.generate()
    device = Ed25519PrivateKey.generate()
    print("Set these Heroku config vars (Config Vars in dashboard or `heroku config:set`):")
    print()
    print(f"DELIVERY_ISSUER_KEY_HEX={private_key_to_hex(issuer)}")
    print(f"DELIVERY_DEVICE_KEY_HEX={private_key_to_hex(device)}")
    print()
    print("Keep these secret. Same keys must be used if you redeploy and want old QR labels to verify.")


if __name__ == "__main__":
    main()
