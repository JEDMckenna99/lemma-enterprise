"""
Utilities for notifying site owners when admin credentials are issued.
"""

import logging
from typing import Optional, Dict, Any

from api.email_service import send_email

logger = logging.getLogger(__name__)


def _resolve_site_admin_email(site_id: str, site_domain: Optional[str] = None) -> Optional[str]:
    """Resolve notification recipient from the canonical Site record."""
    try:
        from api.database import SessionLocal, Site
        db = SessionLocal()
        try:
            site = db.query(Site).filter(Site.site_id == site_id).first()
            if not site and site_domain:
                site = db.query(Site).filter(Site.site_domain == site_domain).first()
            if site and site.admin_email:
                return str(site.admin_email).strip().lower()
            return None
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to resolve site admin email for {site_id}: {e}")
        return None


def notify_admin_lemma_issued(
    *,
    site_id: str,
    site_domain: Optional[str],
    user_did: str,
    permission_level: str,
    issued_via: str,
    credential_id: Optional[str] = None,
    fallback_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a security notification when an admin lemma is issued for a site.
    Returns a structured status payload and never raises.
    """
    recipient = _resolve_site_admin_email(site_id, site_domain) or (str(fallback_email).strip().lower() if fallback_email else None)
    if not recipient:
        logger.warning(f"No notification recipient found for admin issuance on site {site_id}")
        return {"success": False, "sent": False, "reason": "missing_recipient"}

    subject = f"Admin credential issued for {site_id}"
    html = (
        "<p>An admin credential was issued for your site.</p>"
        f"<p><strong>Site ID:</strong> {site_id}<br>"
        f"<strong>Site domain:</strong> {site_domain or site_id}<br>"
        f"<strong>Permission:</strong> {permission_level}<br>"
        f"<strong>User PPID:</strong> {user_did}<br>"
        f"<strong>Issued via:</strong> {issued_via}<br>"
        f"<strong>Credential ID:</strong> {credential_id or 'n/a'}</p>"
        "<p>If this was not expected, rotate API keys and review site admin bindings immediately.</p>"
    )

    try:
        result = send_email(to=recipient, subject=subject, html=html)
        return {
            "success": bool(result.get("success")),
            "sent": bool(result.get("success")),
            "recipient": recipient,
            "provider": result.get("provider"),
        }
    except Exception as e:
        logger.warning(f"Failed sending admin issuance notification for {site_id}: {e}")
        return {"success": False, "sent": False, "recipient": recipient, "reason": str(e)}

