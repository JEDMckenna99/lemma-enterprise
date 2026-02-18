"""
Access token helpers for server-enforced controlled actions.

These tokens are issued after proof verification and are intended for
short-lived API authorization via `Authorization: Bearer <token>`.
"""

import os
import time
import logging
from typing import Optional, Tuple

import jwt

logger = logging.getLogger(__name__)

ACCESS_TOKEN_PREFIX = "lm_at_"
DEFAULT_TTL_SECONDS = 900
MAX_TTL_SECONDS = 3600
MIN_TTL_SECONDS = 300


def _get_access_token_secret() -> str:
    secret = (
        os.environ.get("LEMMA_ACCESS_TOKEN_SECRET")
        or os.environ.get("SESSION_SECRET")
        or os.environ.get("SECRET_KEY")
    )
    if not secret:
        raise RuntimeError("Access token secret is not configured")
    return secret


def _normalize_scopes(scopes) -> list[str]:
    if scopes is None:
        return []
    if isinstance(scopes, str):
        return [s.strip().lower() for s in scopes.split(",") if s.strip()]
    if isinstance(scopes, (list, tuple, set)):
        out = []
        for item in scopes:
            val = str(item).strip().lower()
            if val and val not in out:
                out.append(val)
        return out
    return []


def _is_admin_permission(permission_id: Optional[str]) -> bool:
    if not permission_id:
        return False
    value = permission_id.strip().lower()
    return value in {"admin", "admin_access", "super_admin", "superadmin", "site_admin"} or "admin" in value


def issue_access_token(
    *,
    subject: str,
    site_id: str,
    permission_id: Optional[str],
    scopes,
    credential_id: Optional[str] = None,
    issuer_did: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Tuple[str, int]:
    ttl = int(ttl_seconds or DEFAULT_TTL_SECONDS)
    ttl = max(MIN_TTL_SECONDS, min(MAX_TTL_SECONDS, ttl))

    now = int(time.time())
    exp = now + ttl

    payload = {
        "sub": subject,
        "site_id": (site_id or "").strip().lower(),
        "permission_id": (permission_id or "").strip().lower(),
        "scope": _normalize_scopes(scopes),
        "credential_id": credential_id,
        "issuer": issuer_did,
        "token_use": "controlled_action_access",
        "iat": now,
        "exp": exp,
    }

    secret = _get_access_token_secret()
    jwt_token = jwt.encode(payload, secret, algorithm="HS256")
    return f"{ACCESS_TOKEN_PREFIX}{jwt_token}", ttl


def validate_access_token(
    token: str,
    *,
    required_site_id: Optional[str] = None,
    required_scope: Optional[str] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    if not token:
        return None, "missing_token"

    if not token.startswith(ACCESS_TOKEN_PREFIX):
        return None, "invalid_token_prefix"

    jwt_token = token[len(ACCESS_TOKEN_PREFIX):].strip()
    if not jwt_token:
        return None, "invalid_token_format"

    try:
        payload = jwt.decode(jwt_token, _get_access_token_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, "token_expired"
    except Exception:
        return None, "invalid_token_signature"

    site_id = str(payload.get("site_id", "")).strip().lower()
    if required_site_id and site_id != required_site_id.strip().lower():
        return None, "site_mismatch"

    scopes = _normalize_scopes(payload.get("scope", []))
    permission_id = str(payload.get("permission_id", "")).strip().lower()
    if required_scope:
        required_scope = required_scope.strip().lower()
        if required_scope not in scopes and not (_is_admin_permission(permission_id) and required_scope in {"read", "write", "admin"}):
            return None, "missing_scope"

    payload["scope"] = scopes
    payload["is_admin"] = _is_admin_permission(permission_id)
    return payload, None

