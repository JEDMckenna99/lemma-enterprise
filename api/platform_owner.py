"""Platform sole-owner enforcement for lemma.id admin/high-scope access."""

from __future__ import annotations

import hmac
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_PLATFORM_SITES = frozenset({"lemma.id", "lemma_platform"})
_PPID_RE = re.compile(r"^did:lemma:ppid_[0-9a-f]{64}$")
_ADMIN_ROLES = frozenset(
    {"admin", "owner", "super_admin", "superadmin", "site_admin", "platform_admin"}
)


def platform_owner_ppid() -> Optional[str]:
    raw = (os.getenv("LEMMA_PLATFORM_OWNER_PPID") or "").strip()
    if raw and _PPID_RE.match(raw):
        return raw
    return None


def platform_owner_enforcement_enabled() -> bool:
    return platform_owner_ppid() is not None


def is_platform_site(site_id: Optional[str]) -> bool:
    normalized = (site_id or "").strip().lower()
    return normalized in _PLATFORM_SITES


def normalize_ppid(value: Optional[str]) -> Optional[str]:
    candidate = (value or "").strip()
    if candidate and _PPID_RE.match(candidate):
        return candidate
    return None


def is_platform_owner_ppid(ppid: Optional[str]) -> bool:
    owner = platform_owner_ppid()
    normalized = normalize_ppid(ppid)
    if not owner or not normalized:
        return False
    return hmac.compare_digest(owner, normalized)


def _default_user_profile() -> Dict[str, object]:
    return {
        "role": "user",
        "permission_id": "customer_access",
        "permissions": ["read", "access"],
        "scope": ["read"],
        "source": "platform_owner_cap",
    }


def cap_platform_role_profile(
    ppid: str,
    site_id: str,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Downgrade platform admin roles for non-owner PPIDs when enforcement is on."""
    if not platform_owner_enforcement_enabled() or not is_platform_site(site_id):
        return profile
    role = str(profile.get("role") or "user").strip().lower()
    if role in _ADMIN_ROLES and not is_platform_owner_ppid(ppid):
        logger.info(
            "Capping non-owner platform role for %s on %s (was %s)",
            ppid[:20],
            site_id,
            role,
        )
        return {**_default_user_profile()}
    return profile


def enforce_platform_admin_ppid(
    ppid: str,
    site_id: str,
) -> Optional[Tuple[Dict[str, str], int]]:
    """Return an error payload and status when platform admin is denied."""
    if not platform_owner_enforcement_enabled() or not is_platform_site(site_id):
        return None
    if is_platform_owner_ppid(ppid):
        return None
    return (
        {
            "success": False,
            "error": "platform_owner_required",
            "message": (
                "Platform admin access is restricted to the configured "
                "platform owner PPID."
            ),
        },
        403,
    )


def resolve_platform_login_ppid(
    *,
    client_ppid: Optional[str],
    wallet_id: Optional[str],
    passkey_credential_id: Optional[str] = None,
    db=None,
) -> str:
    """Prefer person-root PPID from wallet IDV binding when available."""
    close_db = False
    if db is None:
        from api.database import get_db

        db = get_db()
        close_db = True

    try:
        if wallet_id:
            from api.ishuman import _derive_ppid_for_site, _resolve_person_id_for_wallet

            if _resolve_person_id_for_wallet(db, wallet_id):
                server_ppid = _derive_ppid_for_site(
                    rp_id="lemma.id",
                    wallet_id=wallet_id,
                    db=db,
                )
                normalized_client = normalize_ppid(client_ppid)
                if normalized_client and normalized_client != server_ppid:
                    logger.warning(
                        "Client PPID %s... disagrees with person-root %s...; using server value",
                        normalized_client[:24],
                        server_ppid[:24],
                    )
                return server_ppid
    finally:
        if close_db and db is not None:
            db.close()

    normalized_client = normalize_ppid(client_ppid)
    if normalized_client:
        return normalized_client

    if passkey_credential_id:
        from api.services.wallet_service import derive_user_ppid

        return derive_user_ppid("lemma.id", passkey_credential_id=passkey_credential_id)

    raise ValueError("ppid or passkey_credential_id required for platform login")


def enforce_platform_login_wallet(
    *,
    client_ppid: Optional[str],
    wallet_id: Optional[str],
    passkey_credential_id: Optional[str] = None,
    db=None,
) -> Tuple[Optional[str], Optional[Tuple[Dict[str, str], int]]]:
    """
    Resolve platform-login PPID or deny when owner enforcement requires IDV.

    When LEMMA_PLATFORM_OWNER_PPID is set, platform login/restore must come from
    a wallet with a completed isHuman person-root binding. Bare client PPIDs are
    not accepted.
    """
    try:
        ppid = resolve_platform_login_ppid(
            client_ppid=client_ppid,
            wallet_id=wallet_id,
            passkey_credential_id=passkey_credential_id,
            db=db,
        )
    except ValueError:
        return None, (
            {
                "success": False,
                "error": "ppid_or_passkey_required",
                "message": "ppid or passkey_credential_id required",
            },
            400,
        )

    if not platform_owner_enforcement_enabled():
        return ppid, None

    close_db = False
    if db is None:
        from api.database import get_db

        db = get_db()
        close_db = True

    person_root_verified = False
    try:
        if wallet_id:
            from api.ishuman import _resolve_person_id_for_wallet

            person_root_verified = bool(_resolve_person_id_for_wallet(db, wallet_id))
    finally:
        if close_db and db is not None:
            db.close()

    if not person_root_verified:
        return None, (
            {
                "success": False,
                "error": "person_root_required",
                "message": "Complete isHuman IDV on this wallet before platform login.",
            },
            403,
        )

    return ppid, None


def platform_owner_admin_email() -> str:
    return str(
        os.getenv("LEMMA_ADMIN_EMAIL", os.getenv("PLATFORM_ADMIN_EMAIL", "")) or "admin@lemma.id"
    ).strip().lower()


def evaluate_platform_owner_bootstrap(
    *,
    client_ppid: Optional[str],
    wallet_id: Optional[str],
    db=None,
) -> Dict[str, Any]:
    """Evaluate whether the wallet qualifies for platform-owner auto-bootstrap."""
    close_db = False
    if db is None:
        from api.database import get_db

        db = get_db()
        close_db = True

    owner = platform_owner_ppid()
    server_ppid: Optional[str] = None
    person_root_verified = False

    try:
        if wallet_id:
            from api.ishuman import _resolve_person_id_for_wallet

            person_root_verified = bool(_resolve_person_id_for_wallet(db, wallet_id))
            if person_root_verified:
                server_ppid = resolve_platform_login_ppid(
                    client_ppid=client_ppid,
                    wallet_id=wallet_id,
                    db=db,
                )
    except ValueError:
        server_ppid = None
    finally:
        if close_db and db is not None:
            db.close()

    effective_ppid = normalize_ppid(server_ppid) or normalize_ppid(client_ppid)
    client_norm = normalize_ppid(client_ppid)
    ppid_consistent = (
        not client_norm
        or not server_ppid
        or hmac.compare_digest(client_norm, server_ppid)
    )

    is_owner = is_platform_owner_ppid(effective_ppid)
    return {
        "owner_configured": owner is not None,
        "person_root_verified": person_root_verified,
        "is_platform_owner": is_owner,
        "ppid_consistent": ppid_consistent,
        "can_auto_issue": bool(
            owner
            and person_root_verified
            and is_owner
            and ppid_consistent
            and effective_ppid
        ),
        "ppid": effective_ppid,
        "site_id": "lemma.id",
        "site_domain": "lemma.id",
        "admin_email": platform_owner_admin_email(),
    }


def verify_platform_owner_wallet(
    *,
    client_ppid: Optional[str],
    wallet_id: Optional[str],
    db=None,
) -> Tuple[Optional[str], Optional[Tuple[Dict[str, str], int]]]:
    """Return canonical owner PPID or an error payload for bootstrap issuance."""
    status = evaluate_platform_owner_bootstrap(
        client_ppid=client_ppid,
        wallet_id=wallet_id,
        db=db,
    )
    if not status.get("owner_configured"):
        return None, (
            {
                "success": False,
                "error": "platform_owner_not_configured",
                "message": (
                    "Set LEMMA_PLATFORM_OWNER_PPID on the server to your person-root "
                    "lemma.id PPID before using owner auto-bootstrap."
                ),
            },
            503,
        )
    if not status.get("person_root_verified"):
        return None, (
            {
                "success": False,
                "error": "person_root_required",
                "message": "Complete isHuman IDV on this wallet before platform admin bootstrap.",
            },
            403,
        )
    if not status.get("ppid_consistent"):
        return None, (
            {
                "success": False,
                "error": "ppid_mismatch",
                "message": "Wallet PPID does not match the server person-root derivation.",
            },
            403,
        )
    if not status.get("is_platform_owner"):
        return None, (
            {
                "success": False,
                "error": "platform_owner_required",
                "message": "This wallet is not the configured lemma.id platform owner.",
            },
            403,
        )
    return status.get("ppid"), None
