"""
Shared site ownership checks for developer platform routes.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from flask import g, jsonify

logger = logging.getLogger(__name__)


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


def _site_api_key_matches(site_id: str, api_key: str) -> bool:
    if not site_id or not api_key:
        return False
    try:
        from api.database import SessionLocal, Site

        db = SessionLocal()
        try:
            site = db.query(Site).filter(Site.site_id == site_id).first()
            return bool(site and site.api_key == api_key)
        finally:
            db.close()
    except Exception:
        return False


def require_site_ownership(
    site_id: str,
    *,
    allow_site_api_key: bool = False,
) -> Optional[Tuple]:
    """
    Verify site access for the current request.

    Returns None if authorized, or (response, status_code) if denied.
    """
    if allow_site_api_key and getattr(g, "api_key", None):
        if _site_api_key_matches(site_id, g.api_key):
            return None

    ppid = get_authenticated_ppid()
    if not ppid:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Authentication required",
                    "code": "AUTH_REQUIRED",
                    "message": "Provide X-Lemma-Credential or X-Agent-Token for site access.",
                }
            ),
            401,
        )

    if not verify_site_ownership(site_id, ppid):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "You do not have access to this site",
                    "code": "UNAUTHORIZED_SITE_ACCESS",
                }
            ),
            403,
        )
    return None
