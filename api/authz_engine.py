"""
Unified authz engine scaffold.

Phase 1 scope:
- Parse `X-Lemma-Credential`
- Verify with trusted issuer + signature checks
- Return normalized principal context for decorators/policies
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from auth.permissions import normalize_scopes, is_admin_permission
from api.site_hostname import normalize_runtime_site_binding


@dataclass
class AuthzPrincipal:
    principal_type: str
    auth_method: str
    ppid: str
    credential_id: Optional[str]
    permission_id: str
    scope: list[str]
    site_binding: Optional[str]


def _decode_lemma_header(raw_header: str) -> Optional[dict]:
    """Decode JSON or base64url(JSON) lemma credential header."""
    if not raw_header:
        return None

    text = str(raw_header).strip()
    if not text:
        return None

    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    try:
        padded = text + ("=" * (-len(text) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def extract_user_lemma_principal(
    headers: Mapping[str, str],
) -> Tuple[Optional[AuthzPrincipal], Optional[str]]:
    """
    Extract and verify a user lemma principal from request headers.
    Returns (principal, error_code).
    """
    raw_credential = headers.get("X-Lemma-Credential")
    if not raw_credential:
        return None, "missing_lemma_header"

    credential = _decode_lemma_header(raw_credential)
    if not credential:
        return None, "invalid_lemma_header"

    try:
        from api.trusted_issuers import verify_credential_with_trust
    except Exception:
        return None, "verifier_unavailable"

    verification = verify_credential_with_trust(credential)
    if not verification.get("valid"):
        reason = verification.get("reason", "unknown")
        if reason == "untrusted_issuer":
            issuer = str(verification.get("issuer") or "").strip()
            if issuer:
                # Include compact issuer fingerprint for diagnostics.
                safe_issuer = issuer[:120]
                return None, f"invalid_lemma:untrusted_issuer:{safe_issuer}"
        return None, f"invalid_lemma:{reason}"

    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    ppid = (
        credential.get("subject")
        or credential.get("sub")
        or claims.get("sub")
        or claims.get("ppid")
        or claims.get("id")
        or claims.get("subject")
    )
    if not ppid or not str(ppid).startswith("did:lemma:ppid_"):
        return None, "invalid_lemma_subject"

    permission_id = (
        claims.get("permissionId")
        or claims.get("permission_id")
        or claims.get("permission_level")
        or claims.get("permission")
        or claims.get("accountType")
        or "read"
    )

    raw_scope = claims.get("scope", [])
    if isinstance(raw_scope, str):
        scope = normalize_scopes([part.strip() for part in raw_scope.split(",") if part.strip()])
    else:
        scope = normalize_scopes(raw_scope if isinstance(raw_scope, (list, tuple, set)) else [])
    if not scope:
        permission_text = str(permission_id or "").strip().lower()
        if is_admin_permission(permission_text):
            scope = ["admin", "write", "read"]
        elif "developer" in permission_text or permission_text in {"developer_access", "write_access"}:
            scope = ["write", "read"]
        else:
            scope = ["read"]

    credential_id = credential.get("id")
    header_credential_id = headers.get("X-Credential-ID")
    if header_credential_id and credential_id and header_credential_id != credential_id:
        return None, "credential_id_mismatch"

    site_binding = None
    for candidate in (
        claims.get("siteDomain"),
        claims.get("site_domain"),
        claims.get("siteId"),
        claims.get("site_id"),
        claims.get("site"),
    ):
        normalized = normalize_runtime_site_binding(candidate)
        if normalized:
            site_binding = normalized
            break

    return AuthzPrincipal(
        principal_type="user_lemma",
        auth_method="lemma_header",
        ppid=str(ppid),
        credential_id=credential_id,
        permission_id=str(permission_id),
        scope=scope,
        site_binding=site_binding,
    ), None


def build_principal_from_credential_dict(
    credential: dict,
    *,
    auth_method: str = "lemma_header",
) -> Optional[AuthzPrincipal]:
    """Build a normalized principal from a decoded credential payload."""
    if not isinstance(credential, dict):
        return None

    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    ppid = (
        credential.get("subject")
        or credential.get("sub")
        or claims.get("sub")
        or claims.get("ppid")
        or claims.get("id")
        or claims.get("subject")
    )
    if not ppid or not str(ppid).startswith("did:lemma:ppid_"):
        return None

    permission_id = (
        claims.get("permissionId")
        or claims.get("permission_id")
        or claims.get("permission_level")
        or claims.get("permission")
        or claims.get("accountType")
        or "read"
    )

    raw_scope = claims.get("scope", [])
    if isinstance(raw_scope, str):
        scope = normalize_scopes([part.strip() for part in raw_scope.split(",") if part.strip()])
    else:
        scope = normalize_scopes(raw_scope if isinstance(raw_scope, (list, tuple, set)) else [])
    if not scope:
        permission_text = str(permission_id or "").strip().lower()
        if is_admin_permission(permission_text):
            scope = ["admin", "write", "read"]
        elif "developer" in permission_text or permission_text in {"developer_access", "write_access"}:
            scope = ["write", "read"]
        else:
            scope = ["read"]

    site_binding = None
    for candidate in (
        claims.get("siteDomain"),
        claims.get("site_domain"),
        claims.get("siteId"),
        claims.get("site_id"),
        claims.get("site"),
    ):
        normalized = normalize_runtime_site_binding(candidate)
        if normalized:
            site_binding = normalized
            break

    return AuthzPrincipal(
        principal_type="user_lemma",
        auth_method=auth_method,
        ppid=str(ppid),
        credential_id=credential.get("id"),
        permission_id=str(permission_id),
        scope=scope,
        site_binding=site_binding,
    )


def try_wallet_session_principal(headers: Mapping[str, str]) -> Tuple[Optional[AuthzPrincipal], Optional[str]]:
    """
    Browser fallback when strict credential verification fails.

    Requires a valid lemma_wallet_session cookie and a parseable
    X-Lemma-Credential header containing a PPID. Used for developer/admin
    self-service pages where wallet-selected credentials may not pass the
    strict verifier (legacy package shapes, local metadata, etc.).
    """
    try:
        from api.agent_credentials import (
            _decode_lemma_header_credential,
            _has_valid_wallet_unlock_session,
        )
    except Exception:
        return None, "wallet_auth_unavailable"

    if not _has_valid_wallet_unlock_session():
        return None, "wallet_session_required"

    credential = _decode_lemma_header_credential()
    if not credential:
        return None, "missing_lemma_header"

    principal = build_principal_from_credential_dict(
        credential,
        auth_method="wallet_session",
    )
    if not principal:
        return None, "invalid_lemma_subject"

    # SECURITY: This is the fallback used precisely when strict signature/trust
    # verification of the credential has already failed. The credential body is
    # therefore UNVERIFIED and fully attacker-controllable; the only thing
    # actually proven here is possession of a valid wallet-unlock session cookie.
    # A stolen/replayed cookie plus a crafted X-Lemma-Credential JSON must never
    # be able to assert admin or write scope. We establish identity (PPID) for
    # low-risk read flows only and force least privilege. Privileged actions must
    # go through a verified credential (extract_user_lemma_principal) or a
    # proof-native authorization path.
    principal.scope = ["read"]
    principal.permission_id = "read"

    return principal, None

