"""
Shared site ownership checks for developer platform routes.

Single authoritative module for binding site-scoped operations to verified
site ownership (PPID admin), site API keys, or explicit platform-operator access.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Optional, Tuple, Union

from flask import g, jsonify, request

logger = logging.getLogger(__name__)

SiteLike = Any
AuthzResult = Tuple[Optional[SiteLike], Optional[Tuple[Any, int]]]


def get_authenticated_ppid() -> Optional[str]:
    """Return PPID from request context set by auth decorators only."""
    ppid = getattr(g, "ppid", None)
    if ppid and str(ppid).startswith("did:lemma:ppid_"):
        return str(ppid)

    agent_credential = getattr(g, "agent_credential", None)
    if isinstance(agent_credential, dict):
        delegated = agent_credential.get("authorized_by_ppid")
        if delegated and str(delegated).startswith("did:lemma:ppid_"):
            return str(delegated)
    return None


def _deny(
    *,
    status: int,
    code: str,
    error: str,
    message: Optional[str] = None,
) -> Tuple[Any, int]:
    payload: Dict[str, Any] = {
        "success": False,
        "error": error,
        "code": code,
    }
    if message:
        payload["message"] = message
    return jsonify(payload), status


def hash_api_key(api_key: str) -> str:
    """SHA-256 hash for customer/site API key validation."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def query_param_api_key_present() -> bool:
    """True when the client supplied ?api_key= (always rejected for auth)."""
    return bool((request.args.get("api_key") or "").strip())


def reject_query_param_api_key() -> Optional[Tuple[Any, int]]:
    """Fail closed when API keys are supplied only via query string."""
    if not query_param_api_key_present():
        return None
    has_header = bool((request.headers.get("X-API-Key") or "").strip())
    auth_header = (request.headers.get("Authorization") or "").strip()
    has_bearer = auth_header.startswith("Bearer ") and auth_header[7:].strip()
    if has_header or has_bearer or getattr(g, "api_key", None):
        return None
    return _deny(
        status=401,
        code="QUERY_PARAM_API_KEY_REJECTED",
        error="API keys in query parameters are not accepted",
        message="Use X-API-Key header or Authorization: Bearer <key>.",
    )


def _platform_api_keys() -> Tuple[str, ...]:
    keys = []
    for name in ("LEMMA_API_KEY", "LEMMA_PLATFORM_API_KEY"):
        value = os.environ.get(name)
        if value:
            keys.append(value)
    return tuple(keys)


def is_platform_api_key(api_key: str) -> bool:
    """True when the key matches a configured platform operator key."""
    if not api_key:
        return False
    for platform_key in _platform_api_keys():
        if hmac.compare_digest(api_key, platform_key):
            return True
    return False


def _extract_request_api_key() -> Optional[str]:
    api_key = getattr(g, "api_key", None)
    if api_key:
        return str(api_key).strip()

    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "", 1).strip()
        if token.startswith("lemma_") or token.startswith("lm_"):
            return token

    header_key = request.headers.get("X-API-Key")
    if header_key:
        return str(header_key).strip()
    return None


def validate_site_api_key(api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Hash-first API key validation for site-bound and platform keys.

    Platform keys authenticate via env compare_digest. Customer/site keys
    authenticate via customer_manager hash validation with optional postgres
    api_keys fallback. Plaintext Site.api_key matching is not used.
    """
    key = (api_key or _extract_request_api_key() or "").strip()
    if not key:
        return {"valid": False, "error": "missing_api_key", "code": "AUTH_REQUIRED"}

    if is_platform_api_key(key):
        return {"valid": True, "type": "platform", "site_id": None}

    from api.customer_accounts import customer_manager

    validation = customer_manager.validate_api_key(key)
    if validation.get("valid"):
        return {
            **validation,
            "type": "customer",
        }

    try:
        from api.storage_helpers import validate_api_key_hash_in_postgres

        pg_result = validate_api_key_hash_in_postgres(hash_api_key(key))
        if pg_result:
            return {
                "valid": True,
                "type": "customer",
                **pg_result,
            }
    except Exception as exc:
        logger.debug("Postgres api_keys fallback unavailable: %s", exc)

    return {
        "valid": False,
        "error": validation.get("error", "Invalid API key"),
        "code": "INVALID_API_KEY",
    }


def resolve_site_from_api_key(api_key: Optional[str] = None) -> Optional[SiteLike]:
    """Resolve Site from hash-validated customer-issued keys only."""
    key = (api_key or _extract_request_api_key() or "").strip()
    if not key:
        return None

    validation = validate_site_api_key(key)
    if not validation.get("valid") or validation.get("type") != "customer":
        return None

    site_id = validation.get("site_id")
    if not site_id:
        return None

    from api.database import SessionLocal, Site
    from api.site_hostname import try_canonicalize_site_hostname

    db = SessionLocal()
    try:
        site = db.query(Site).filter_by(site_id=site_id).first()
        if not site:
            return None

        _, domain_err = try_canonicalize_site_hostname(getattr(site, "site_domain", ""))
        if domain_err:
            return None
        return site
    finally:
        db.close()


def is_platform_operator_ppid(ppid: Optional[str] = None) -> bool:
    """True when principal is an active lemma.id platform operator admin."""
    candidate = ppid or get_authenticated_ppid()
    if not candidate:
        return False
    try:
        from api.agent_credentials import _is_lemma_platform_operator

        return bool(_is_lemma_platform_operator(str(candidate), None))
    except Exception as exc:
        logger.warning("Platform operator lookup failed: %s", exc)
        return False


def verify_site_ownership(site_id: str, ppid: str) -> bool:
    """True when ppid is an active admin for site_id."""
    if not ppid or not site_id:
        return False

    try:
        from api.database import SessionLocal, SiteAdmin

        db = SessionLocal()
        try:
            admin_record = db.query(SiteAdmin).filter(
                SiteAdmin.site_id == site_id,
                SiteAdmin.admin_did == ppid,
                SiteAdmin.is_active == True,  # noqa: E712
            ).first()
            if admin_record:
                logger.debug("Site ownership verified: %s... owns %s", ppid[:30], site_id)
                return True
            logger.warning(
                "SECURITY: Unauthorized site access attempt - user %s... tried to access %s",
                ppid[:30],
                site_id,
            )
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.error("Site ownership check failed: %s", exc)
        return False


def site_has_existing_owner(
    site_id: str,
    site_domain: str,
    caller_ppid: str,
) -> bool:
    """True when site/domain is claimed by another account (not caller)."""
    from api.developer_self_issue import _site_has_existing_owner

    return _site_has_existing_owner(site_id, site_domain, caller_ppid)


def _site_api_key_matches(site_id: str, api_key: str) -> bool:
    site = resolve_site_from_api_key(api_key)
    return bool(site and site.site_id == site_id)


def authorize_site_access(
    requested_site_id: Optional[str] = None,
    *,
    allow_site_api_key: bool = False,
    allow_platform_admin: bool = False,
) -> AuthzResult:
    """
    Authorize access to a site-scoped resource.

    Returns (site, None) on success or (None, (response, status)) on denial.
    When allow_site_api_key is True and an API key resolves to a site, that site
    is authoritative; a mismatched requested_site_id is rejected.
    """
    normalized_requested = (requested_site_id or "").strip() or None

    if allow_site_api_key:
        query_reject = reject_query_param_api_key()
        if query_reject:
            return None, query_reject

        api_key = _extract_request_api_key()
        if api_key:
            site = resolve_site_from_api_key(api_key)
            if not site:
                return None, _deny(
                    status=401,
                    code="INVALID_API_KEY",
                    error="Invalid or missing API key",
                )
            if normalized_requested and site.site_id != normalized_requested:
                return None, _deny(
                    status=403,
                    code="SITE_ID_MISMATCH",
                    error="Requested site_id does not match API key site binding",
                    message="Do not supply a site_id that disagrees with the authenticated API key.",
                )
            return site, None

    ppid = get_authenticated_ppid()
    if not ppid:
        return None, _deny(
            status=401,
            code="AUTH_REQUIRED",
            error="Authentication required",
            message="Provide X-Lemma-Credential, X-Agent-Token, or site API key for site access.",
        )

    if allow_platform_admin and is_platform_operator_ppid(ppid):
        if normalized_requested:
            from api.database import SessionLocal, Site

            db = SessionLocal()
            try:
                site = db.query(Site).filter(Site.site_id == normalized_requested).first()
                if site:
                    return site, None
            finally:
                db.close()
        return normalized_requested, None

    if not normalized_requested:
        return None, _deny(
            status=400,
            code="SITE_ID_REQUIRED",
            error="site_id is required",
        )

    if not verify_site_ownership(normalized_requested, ppid):
        return None, _deny(
            status=403,
            code="UNAUTHORIZED_SITE_ACCESS",
            error="You do not have access to this site",
        )

    from api.database import SessionLocal, Site

    db = SessionLocal()
    try:
        site = db.query(Site).filter(Site.site_id == normalized_requested).first()
        return site or normalized_requested, None
    finally:
        db.close()


def require_site_ownership(
    site_id: str,
    *,
    allow_site_api_key: bool = False,
    allow_platform_admin: bool = False,
) -> Optional[Tuple]:
    """
    Verify site access for the current request.

    Returns None if authorized, or (response, status_code) if denied.
    """
    _, denied = authorize_site_access(
        site_id,
        allow_site_api_key=allow_site_api_key,
        allow_platform_admin=allow_platform_admin,
    )
    return denied


def resolved_site_id(site_or_id: Union[SiteLike, str, None]) -> Optional[str]:
    if site_or_id is None:
        return None
    if isinstance(site_or_id, str):
        return site_or_id.strip() or None
    return getattr(site_or_id, "site_id", None)


@contextmanager
def tenant_db_context(site_or_id: Union[SiteLike, str, None]):
    """Set PostgreSQL tenant GUC for the duration of a block (SET LOCAL)."""
    site_id = resolved_site_id(site_or_id)
    from api.database import tenant_local_site_context

    with tenant_local_site_context(site_id):
        yield site_id
