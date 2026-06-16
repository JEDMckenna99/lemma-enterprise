"""Signed route and package credential issuance."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from crypto.canonical import canonical_json_bytes
from crypto.device_keys import load_public_key_b64, sign_bytes


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def issue_route_credential(
    issuer_key: Ed25519PrivateKey,
    *,
    route_id: str,
    driver_id: str,
    device_id: str,
    device_pubkey: str,
    stops: list[str],
    packages: list[dict[str, Any]],
    policy_defaults: dict[str, bool],
    expires_hours: int = 12,
) -> dict[str, Any]:
    issued_at = _iso_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).replace(microsecond=0)
    payload: dict[str, Any] = {
        "credential_type": "RouteCredential",
        "route_id": route_id,
        "driver_id": driver_id,
        "device_id": device_id,
        "device_pubkey": device_pubkey,
        "stops": stops,
        "policy_defaults": policy_defaults,
        "packages": packages,
        "issued_at": issued_at,
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "issuer_pubkey": load_public_key_b64(issuer_key),
    }
    message = hashlib.sha256(canonical_json_bytes(payload)).digest()
    payload["signature"] = sign_bytes(issuer_key, message)
    return payload


def issue_package_assignment(
    issuer_key: Ed25519PrivateKey,
    *,
    package_id: str,
    route_id: str,
    stop_id: str,
    policy: dict[str, bool],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "credential_type": "PackageAssignment",
        "package_id": package_id,
        "route_id": route_id,
        "stop_id": stop_id,
        "policy": policy,
        "issued_at": _iso_now(),
        "issuer_pubkey": load_public_key_b64(issuer_key),
    }
    message = hashlib.sha256(canonical_json_bytes(payload)).digest()
    payload["signature"] = sign_bytes(issuer_key, message)
    return payload


def build_fake_packages(
    issuer_key: Ed25519PrivateKey,
    route_id: str,
    stops: list[str],
    count: int,
    policy_defaults: dict[str, bool],
) -> list[dict[str, Any]]:
    packages = []
    for i in range(1, count + 1):
        stop_id = stops[(i - 1) % len(stops)]
        policy = dict(policy_defaults)
        if i % 5 == 0:
            policy["signature_required"] = True
        if i % 7 == 0:
            policy["otp_required"] = True
        pkg_id = f"P-{1000 + i}"
        assignment = issue_package_assignment(
            issuer_key,
            package_id=pkg_id,
            route_id=route_id,
            stop_id=stop_id,
            policy=policy,
        )
        packages.append({
            "package_id": pkg_id,
            "stop_id": stop_id,
            "policy": policy,
            "assignment": assignment,
        })
    return packages
