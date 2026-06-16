"""Local verification for route credentials, packages, and delivery events."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from crypto.canonical import canonical_json_bytes, chain_hash
from crypto.device_keys import verify_bytes


def _parse_iso(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _verify_signed_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    signature = payload.get("signature")
    issuer_pubkey = payload.get("issuer_pubkey")
    if not signature or not issuer_pubkey:
        return False, "missing_signature"
    message = hashlib.sha256(canonical_json_bytes(payload)).digest()
    if not verify_bytes(issuer_pubkey, message, signature):
        return False, "invalid_signature"
    return True, "ok"


def verify_route_credential(
    credential: dict[str, Any],
    *,
    device_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[bool, str]:
    ok, reason = _verify_signed_payload(credential)
    if not ok:
        return ok, reason
    if credential.get("credential_type") != "RouteCredential":
        return False, "wrong_credential_type"
    expires = credential.get("expires_at")
    if expires:
        current = now or datetime.now(timezone.utc)
        if current > _parse_iso(expires):
            return False, "credential_expired"
    if device_id and credential.get("device_id") != device_id:
        return False, "device_mismatch"
    return True, "ok"


def verify_package_assignment(assignment: dict[str, Any]) -> tuple[bool, str]:
    ok, reason = _verify_signed_payload(assignment)
    if not ok:
        return ok, reason
    if assignment.get("credential_type") != "PackageAssignment":
        return False, "wrong_credential_type"
    return True, "ok"


def verify_package_against_route(
    assignment: dict[str, Any],
    route_credential: dict[str, Any],
) -> tuple[bool, str, dict[str, bool]]:
    ok, reason = verify_package_assignment(assignment)
    if not ok:
        return False, reason, {}
    route_match = assignment.get("route_id") == route_credential.get("route_id")
    if not route_match:
        return False, "route_mismatch", {}
    stop_match = assignment.get("stop_id") in (route_credential.get("stops") or [])
    if not stop_match:
        return False, "stop_mismatch", {}
    policy = assignment.get("policy") or {}
    return True, "ok", policy


def verify_delivery_event(
    event: dict[str, Any],
    *,
    route_credential: dict[str, Any],
    prior_event: Optional[dict[str, Any]] = None,
) -> tuple[bool, str]:
    signature = event.get("signature")
    device_pubkey = event.get("device_pubkey") or route_credential.get("device_pubkey")
    if not signature or not device_pubkey:
        return False, "missing_signature"
    message = hashlib.sha256(canonical_json_bytes(event)).digest()
    if not verify_bytes(device_pubkey, message, signature):
        return False, "invalid_signature"
    if event.get("route_id") != route_credential.get("route_id"):
        return False, "route_mismatch"
    if event.get("device_id") != route_credential.get("device_id"):
        return False, "device_mismatch"
    expected_prev = chain_hash(prior_event) if prior_event else "genesis"
    if event.get("previous_event_hash") != expected_prev:
        return False, "previous_hash_invalid"
    return True, "ok"


def sign_delivery_event(
    event: dict[str, Any],
    private_key,
    route_credential: dict[str, Any],
    prior_event: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from crypto.device_keys import load_public_key_b64, sign_bytes

    payload = dict(event)
    payload["device_pubkey"] = load_public_key_b64(private_key)
    payload["previous_event_hash"] = chain_hash(prior_event) if prior_event else "genesis"
    message = hashlib.sha256(canonical_json_bytes(payload)).digest()
    payload["signature"] = sign_bytes(private_key, message)
    return payload
