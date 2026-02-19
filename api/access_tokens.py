"""
Access token helpers for server-enforced controlled actions.

These tokens are issued after proof verification and are intended for
short-lived API authorization via `Authorization: Bearer <token>`.
"""

import os
import time
import logging
import uuid
import hashlib
from typing import Optional, Tuple

import jwt

logger = logging.getLogger(__name__)

ACCESS_TOKEN_PREFIX = "lm_at_"
DEFAULT_TTL_SECONDS = 900
MAX_TTL_SECONDS = 3600
MIN_TTL_SECONDS = 300
ACCESS_TOKEN_ISSUER = os.environ.get("LEMMA_ACCESS_TOKEN_ISSUER", "lemma.id").strip().lower()


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


def _legacy_token_jti(raw_jwt_token: str) -> str:
    return hashlib.sha256(raw_jwt_token.encode("utf-8")).hexdigest()[:32]


def _revocation_store_key(jti: str) -> str:
    return f"access_token_revoked:{jti}"


def _store_revocation(jti: str, ttl_seconds: int, reason: str, revoked_by: str) -> bool:
    try:
        from auth.redis_store import store
        return store(
            _revocation_store_key(jti),
            {
                "revoked": True,
                "reason": reason,
                "revoked_by": revoked_by,
                "revoked_at": int(time.time()),
            },
            ttl_seconds=max(60, int(ttl_seconds)),
        )
    except Exception as e:
        logger.error(f"Failed to store token revocation for {jti}: {e}")
        return False


def _get_revocation(jti: str) -> Optional[dict]:
    try:
        from auth.redis_store import get
        return get(_revocation_store_key(jti))
    except Exception as e:
        logger.error(f"Failed to read token revocation for {jti}: {e}")
        return None


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
        "jti": uuid.uuid4().hex,
        "sub": subject,
        "site_id": (site_id or "").strip().lower(),
        "aud": (site_id or "").strip().lower(),
        "iss": ACCESS_TOKEN_ISSUER,
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


def _decode_signed_token(jwt_token: str, *, verify_exp: bool = True) -> Tuple[Optional[dict], Optional[str]]:
    try:
        payload = jwt.decode(
            jwt_token,
            _get_access_token_secret(),
            algorithms=["HS256"],
            options={"verify_exp": verify_exp},
        )
        return payload, None
    except jwt.ExpiredSignatureError:
        return None, "token_expired"
    except Exception:
        return None, "invalid_token_signature"


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

    payload, decode_error = _decode_signed_token(jwt_token, verify_exp=True)
    if not payload:
        return None, decode_error

    if payload.get("token_use") != "controlled_action_access":
        return None, "invalid_token_use"

    issuer = str(payload.get("iss", "")).strip().lower()
    if issuer and issuer != ACCESS_TOKEN_ISSUER:
        return None, "invalid_issuer"

    site_id = str(payload.get("site_id", "")).strip().lower()
    audience = str(payload.get("aud", "")).strip().lower()
    if audience and site_id and audience != site_id:
        return None, "audience_site_mismatch"

    if required_site_id and site_id != required_site_id.strip().lower():
        return None, "site_mismatch"
    if required_site_id and audience and audience != required_site_id.strip().lower():
        return None, "audience_mismatch"

    scopes = _normalize_scopes(payload.get("scope", []))
    permission_id = str(payload.get("permission_id", "")).strip().lower()
    if required_scope:
        required_scope = required_scope.strip().lower()
        if required_scope not in scopes and not (_is_admin_permission(permission_id) and required_scope in {"read", "write", "admin"}):
            return None, "missing_scope"

    jti = str(payload.get("jti", "")).strip() or _legacy_token_jti(jwt_token)
    revocation = _get_revocation(jti)
    if revocation and revocation.get("revoked"):
        return None, "token_revoked"

    payload["jti"] = jti
    payload["scope"] = scopes
    payload["is_admin"] = _is_admin_permission(permission_id)
    return payload, None


def introspect_access_token(token: str, *, required_site_id: Optional[str] = None) -> dict:
    payload, error = validate_access_token(token, required_site_id=required_site_id)
    if not payload:
        return {"active": False, "error": error}

    return {
        "active": True,
        "jti": payload.get("jti"),
        "subject": payload.get("sub"),
        "site_id": payload.get("site_id"),
        "permission_id": payload.get("permission_id"),
        "scope": payload.get("scope", []),
        "exp": payload.get("exp"),
        "iat": payload.get("iat"),
        "is_admin": payload.get("is_admin", False),
    }


def revoke_access_token(
    *,
    token: Optional[str] = None,
    jti: Optional[str] = None,
    reason: str = "revoked_by_api",
    revoked_by: str = "api_key",
) -> Tuple[bool, Optional[dict], Optional[str]]:
    if not token and not jti:
        return False, None, "token_or_jti_required"

    effective_jti = (jti or "").strip()
    ttl_seconds = MAX_TTL_SECONDS
    subject = None
    site_id = None
    expires_at = None

    if token:
        if not token.startswith(ACCESS_TOKEN_PREFIX):
            return False, None, "invalid_token_prefix"
        raw_jwt = token[len(ACCESS_TOKEN_PREFIX):].strip()
        if not raw_jwt:
            return False, None, "invalid_token_format"

        payload, decode_error = _decode_signed_token(raw_jwt, verify_exp=False)
        if not payload:
            return False, None, decode_error

        effective_jti = effective_jti or str(payload.get("jti", "")).strip() or _legacy_token_jti(raw_jwt)
        subject = payload.get("sub")
        site_id = payload.get("site_id")
        expires_at = payload.get("exp")
        if isinstance(expires_at, int):
            ttl_seconds = max(60, expires_at - int(time.time()))

    if not effective_jti:
        return False, None, "invalid_jti"

    stored = _store_revocation(effective_jti, ttl_seconds, reason, revoked_by)
    if not stored:
        return False, None, "revocation_store_failed"

    return True, {
        "jti": effective_jti,
        "subject": subject,
        "site_id": site_id,
        "expires_at": expires_at,
        "ttl_seconds": ttl_seconds,
    }, None

