from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from flask import g, jsonify, request


VerifierFn = Callable[[dict], dict]


@dataclass
class LemmaPrincipal:
    ppid: str
    credential_id: Optional[str]
    permission_id: str
    scope: list[str]
    site_binding: Optional[str]
    raw_credential: dict[str, Any]


def _decode_lemma_header(raw_header: str) -> Optional[dict[str, Any]]:
    if not raw_header:
        return None

    text = str(raw_header).strip()
    if not text:
        return None

    try:
        if text.startswith("{"):
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        padded = text + ("=" * (-len(text) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _normalize_scope(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        source = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        source = value
    else:
        source = [str(value)]

    normalized: list[str] = []
    for item in source:
        token = str(item).strip().lower()
        if token and token not in normalized:
            normalized.append(token)
    return normalized


def _canonical_site(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None

    host = text
    try:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        host = (parsed.hostname or "").strip().lower() or text
    except Exception:
        host = text

    host = host.split("/")[0].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    host = host.rstrip(".")
    return host or None


def _error_message_for(code: str) -> str:
    value = str(code or "").strip()
    if value == "auth_required":
        return "Authentication required"
    if value == "missing_scope":
        return "Insufficient scope"
    if value == "site_mismatch":
        return "Credential site binding mismatch"
    if value == "AUTH_PROOF_REQUIRED":
        return "Proof-native authorization is required"
    if value == "AUTH_MODE_DOWNGRADE":
        return "Authorization mode downgrade is not allowed"
    if value == "AUTH_CHAIN_BROKEN":
        return "Proof chain validation failed"
    if value == "AUTH_REPLAY_DETECTED":
        return "Replay detected"
    if value == "AUTH_PROOF_OF_POSSESSION_FAILED":
        return "Proof-of-possession validation failed"
    if value == "invalid_lemma_header":
        return "Invalid X-Lemma-Credential header"
    if value.startswith("invalid_lemma:"):
        return "Credential verification failed"
    return "Authentication required"


def _error_payload(code: str) -> dict[str, Any]:
    error = str(code or "auth_required")
    return {
        "success": False,
        "error": error,
        "message": _error_message_for(error),
    }


def evaluate_proof_contract(proof: dict[str, Any], *, required_scope: Optional[str] = None) -> dict[str, Any]:
    scope_required = str(required_scope or "").strip().lower()
    out = {
        "decision": "deny",
        "reason_code": "AUTH_CHAIN_BROKEN",
        "proof_id": (proof or {}).get("proof_id"),
        "root_grant_id": (proof or {}).get("root_grant_id"),
        "policy_version": (proof or {}).get("policy_version") or (proof or {}).get("version"),
        "profile": str((proof or {}).get("profile") or (proof or {}).get("version") or "authz_profile_v2"),
    }
    if not isinstance(proof, dict):
        return out
    expires_at = proof.get("expires_at")
    try:
        exp = int(expires_at) if expires_at is not None else None
    except (TypeError, ValueError):
        exp = None
    if exp is not None:
        import time

        if exp <= int(time.time()):
            return out
    scope = _normalize_scope(proof.get("scope"))
    if scope_required and scope_required not in scope:
        return out
    out["decision"] = "allow"
    out["reason_code"] = "OK"
    return out


class LemmaAuth:
    def __init__(self, verifier: Optional[VerifierFn] = None, required_site: Optional[str] = None):
        self._verifier = verifier
        self._required_site = _canonical_site(required_site)

    def _verify_credential(self, credential: dict[str, Any]) -> dict[str, Any]:
        if self._verifier:
            return self._verifier(credential)

        try:
            from api.trusted_issuers import verify_credential_with_trust
        except Exception as exc:  # pragma: no cover - fallback for external package usage
            return {"valid": False, "reason": f"verifier_unavailable:{exc}"}
        return verify_credential_with_trust(credential)

    def _extract_principal(self) -> tuple[Optional[LemmaPrincipal], Optional[str]]:
        raw = request.headers.get("X-Lemma-Credential")
        if not raw:
            return None, "missing_lemma_header"

        credential = _decode_lemma_header(raw)
        if not credential:
            return None, "invalid_lemma_header"

        try:
            verification = self._verify_credential(credential)
        except Exception:
            return None, "invalid_lemma:verification_error"
        if not isinstance(verification, dict):
            return None, "invalid_lemma:verification_error"
        if not verification.get("valid"):
            return None, f"invalid_lemma:{verification.get('reason', 'verification_failed')}"

        claims = credential.get("claims") or credential.get("credentialSubject") or {}
        ppid = (
            credential.get("subject")
            or credential.get("sub")
            or claims.get("ppid")
            or claims.get("id")
            or claims.get("subject")
        )
        if not ppid or not str(ppid).startswith("did:lemma:ppid_"):
            return None, "invalid_lemma:missing_ppid"

        permission_id = (
            claims.get("permissionId")
            or claims.get("permission_id")
            or claims.get("permission_level")
            or claims.get("permission")
            or "read"
        )
        scope = _normalize_scope(claims.get("scope"))
        if not scope:
            scope = ["read"]

        site_binding = (
            claims.get("siteId")
            or claims.get("site_id")
            or claims.get("siteDomain")
            or claims.get("site_domain")
        )
        if site_binding:
            site_binding = _canonical_site(site_binding)

        return (
            LemmaPrincipal(
                ppid=str(ppid),
                credential_id=credential.get("id"),
                permission_id=str(permission_id),
                scope=scope,
                site_binding=site_binding,
                raw_credential=credential,
            ),
            None,
        )

    def require_lemma(self, scope: Optional[str] = None, site_bound: bool = False):
        required_scope = scope.strip().lower() if scope else None

        def decorator(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                principal, error = self._extract_principal()
                if error or not principal:
                    return jsonify(_error_payload(error or "auth_required")), 401

                if required_scope and required_scope not in principal.scope:
                    return jsonify(_error_payload("missing_scope")), 403

                if site_bound and self._required_site and principal.site_binding != self._required_site:
                    return jsonify(_error_payload("site_mismatch")), 403

                g.lemma_principal = principal
                return fn(*args, **kwargs)

            return wrapped

        return decorator

