"""Pinned network-root public keys for trust-list verification."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import FrozenSet

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PIN_FILE = _REPO_ROOT / "docs" / "cryptographic" / "NETWORK_ROOT_PUBKEYS.json"


def _normalize_pubkey_hex(value: str) -> str | None:
    candidate = str(value or "").strip().lower()
    if len(candidate) != 64:
        return None
    if not all(ch in "0123456789abcdef" for ch in candidate):
        return None
    return candidate


def network_root_pubkeys_hex(*, extra: str | None = None) -> FrozenSet[str]:
    """Return configured network-root pubkey pins (env overrides JSON file)."""
    pins: set[str] = set()

    env_raw = (os.getenv("LEMMA_NETWORK_ROOT_PUBKEYS") or extra or "").strip()
    if env_raw:
        for part in env_raw.split(","):
            normalized = _normalize_pubkey_hex(part)
            if normalized:
                pins.add(normalized)

    if not pins and _PIN_FILE.exists():
        try:
            data = json.loads(_PIN_FILE.read_text(encoding="utf-8"))
            for item in data.get("pubkeys_hex") or []:
                normalized = _normalize_pubkey_hex(item)
                if normalized:
                    pins.add(normalized)
        except Exception as exc:
            logger.warning("Could not load %s: %s", _PIN_FILE, exc)

    return frozenset(pins)


def allow_unpinned_trust_root() -> bool:
    """Dev/test escape hatch only; production must configure pins."""
    if os.getenv("LEMMA_ALLOW_UNPINNED_TRUST_ROOT", "").strip() == "1":
        return True
    try:
        from api.config import is_production

        return not is_production()
    except Exception:
        return True


def signer_pubkey_is_pinned(signer_pubkey: str) -> bool:
    pins = network_root_pubkeys_hex()
    normalized = _normalize_pubkey_hex(signer_pubkey)
    if not normalized:
        return False
    if not pins:
        return allow_unpinned_trust_root()
    return normalized in pins


def assert_signer_pubkey_pinned(signer_pubkey: str) -> None:
    if not signer_pubkey_is_pinned(signer_pubkey):
        raise RuntimeError("trust_list_signer_not_pinned")
