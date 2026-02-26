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

    scope = normalize_scopes(claims.get("scope", []))
    if not scope:
        scope = ["admin", "write", "read"] if is_admin_permission(str(permission_id)) else ["read"]

    credential_id = credential.get("id")
    header_credential_id = headers.get("X-Credential-ID")
    if header_credential_id and credential_id and header_credential_id != credential_id:
        return None, "credential_id_mismatch"

    site_binding = (
        claims.get("siteId")
        or claims.get("site_id")
        or claims.get("siteDomain")
        or claims.get("site_domain")
    )

    return AuthzPrincipal(
        principal_type="user_lemma",
        auth_method="lemma_header",
        ppid=str(ppid),
        credential_id=credential_id,
        permission_id=str(permission_id),
        scope=scope,
        site_binding=str(site_binding).strip().lower() if site_binding else None,
    ), None

