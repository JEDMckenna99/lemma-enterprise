"""Canonical JSON and hash-chain helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _sort_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sort_value(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_sort_value(item) for item in value]
    return value


def canonical_json_bytes(payload: dict, *, exclude: frozenset[str] = frozenset({"signature"})) -> bytes:
    """Deterministic JSON bytes for signing (signature field excluded by default)."""
    cleaned = {k: v for k, v in payload.items() if k not in exclude}
    return json.dumps(_sort_value(cleaned), separators=(",", ":"), sort_keys=True).encode("utf-8")


def chain_hash(payload: dict) -> str:
    """SHA-256 hex digest of canonical event JSON (includes signature)."""
    digest = hashlib.sha256(canonical_json_bytes(payload, exclude=frozenset())).hexdigest()
    return digest
