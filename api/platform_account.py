"""Unified lemma.id platform account, one identity row per person-root PPID."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from api.platform_owner import normalize_ppid

logger = logging.getLogger(__name__)

_PLATFORM_MEMBER_ACCOUNT_TYPES = frozenset(
    {"developer", "dev", "admin", "owner", "super_admin", "superadmin", "platform_admin"}
)
_ACCOUNT_TYPE_RANK = {
    "customer": 0,
    "user": 0,
    "developer": 1,
    "dev": 1,
    "admin": 2,
    "platform_admin": 2,
    "site_admin": 2,
    "super_admin": 3,
    "superadmin": 3,
    "owner": 4,
}


def normalize_account_type(value: Optional[str]) -> str:
    return (value or "customer").strip().lower()


def resolve_account_type(ppid: Optional[str], db=None) -> str:
    """Return platform account_type for a PPID, defaulting to customer."""
    account = get_platform_account(ppid, db=db)
    if account and getattr(account, "account_type", None):
        return normalize_account_type(account.account_type)
    return "customer"


def resolve_account_type_for_customer(customer, db=None) -> str:
    """Resolve platform account_type from a billing customer record."""
    ppid = getattr(customer, "customer_did", None)
    if ppid:
        return resolve_account_type(ppid, db=db)
    return "customer"


def is_admin_account_type(account_type: Optional[str]) -> bool:
    return normalize_account_type(account_type) in {
        "admin",
        "owner",
        "super_admin",
        "superadmin",
        "platform_admin",
    }


def is_platform_member_account_type(account_type: Optional[str]) -> bool:
    return normalize_account_type(account_type) in _PLATFORM_MEMBER_ACCOUNT_TYPES


def _account_type_rank(account_type: Optional[str]) -> int:
    return _ACCOUNT_TYPE_RANK.get(normalize_account_type(account_type), 0)


def get_platform_account(ppid: Optional[str], db=None):
    """Return the canonical platform_users row for a PPID."""
    normalized = normalize_ppid(ppid)
    if not normalized:
        return None

    close_db = False
    if db is None:
        from api.database import get_db

        db = get_db()
        close_db = True

    try:
        from api.database import PlatformUser

        return db.query(PlatformUser).filter(PlatformUser.user_did == normalized).first()
    finally:
        if close_db and db is not None:
            db.close()


def upsert_platform_account(
    ppid: str,
    *,
    account_type: Optional[str] = None,
    email: Optional[str] = None,
    display_name: Optional[str] = None,
    name: Optional[str] = None,
    company: Optional[str] = None,
    wallet_id: Optional[str] = None,
    replace_wallet_id: bool = False,
    passkey_credential_id: Optional[str] = None,
    verification_level: Optional[str] = None,
    billing_customer_id: Optional[str] = None,
    site_id: Optional[str] = None,
    site_role: Optional[str] = None,
    db=None,
):
    """
    Create or update the canonical platform account and optional site membership.

    account_type is only upgraded, never downgraded, unless explicitly forced
    by passing a higher-ranked type.
    """
    normalized = normalize_ppid(ppid)
    if not normalized:
        raise ValueError("invalid_ppid")

    close_db = False
    own_session = False
    if db is None:
        from api.database import get_db

        db = get_db()
        close_db = True
        own_session = True

    try:
        from api.database import PlatformUser, PlatformUserSite

        account = db.query(PlatformUser).filter(PlatformUser.user_did == normalized).first()
        now = datetime.utcnow()
        if not account:
            account = PlatformUser(
                user_did=normalized,
                account_type=normalize_account_type(account_type or site_role or "customer"),
                email=email,
                display_name=display_name,
                name=name,
                company=company,
                wallet_id=wallet_id,
                passkey_credential_id=passkey_credential_id,
                verification_level=verification_level or "base",
                billing_customer_id=billing_customer_id,
                status="active",
                auth_method="passkey" if passkey_credential_id else "wallet",
                created_at=now,
                last_seen=now,
            )
            db.add(account)
        else:
            account.last_seen = now
            if email:
                account.email = email
            if display_name:
                account.display_name = display_name
            if name:
                account.name = name
            if company:
                account.company = company
            if wallet_id and (not account.wallet_id or replace_wallet_id):
                account.wallet_id = wallet_id
            if passkey_credential_id and not account.passkey_credential_id:
                account.passkey_credential_id = passkey_credential_id
            if verification_level:
                account.verification_level = verification_level
            if billing_customer_id:
                account.billing_customer_id = billing_customer_id
            if account_type:
                incoming = normalize_account_type(account_type)
                current = normalize_account_type(account.account_type)
                if _account_type_rank(incoming) >= _account_type_rank(current):
                    account.account_type = incoming
            if (account.status or "").lower() == "suspended":
                account.status = "active"

        if site_id:
            role = normalize_account_type(site_role or account_type or account.account_type or "customer")
            membership = (
                db.query(PlatformUserSite)
                .filter(PlatformUserSite.user_did == normalized, PlatformUserSite.site_id == site_id)
                .order_by(PlatformUserSite.id.desc())
                .first()
            )
            if not membership:
                membership = PlatformUserSite(
                    user_did=normalized,
                    site_id=site_id,
                    role=role,
                    status="active",
                    joined_at=now,
                )
                db.add(membership)
            else:
                membership.role = role
                membership.status = "active"

        if own_session:
            db.commit()
        return account
    except Exception:
        if own_session and db is not None:
            db.rollback()
        raise
    finally:
        if close_db and db is not None:
            db.close()


def register_developer_account(
    ppid: str,
    *,
    email: str,
    name: str,
    company: str,
    wallet_id: Optional[str] = None,
    passkey_credential_id: Optional[str] = None,
    billing_customer_id: Optional[str] = None,
    db=None,
) -> Dict[str, Any]:
    """Single registration write path for wallet-first developers."""
    normalized = normalize_ppid(ppid)
    upsert_platform_account(
        normalized,
        account_type="developer",
        email=email,
        display_name=name,
        name=name,
        company=company,
        wallet_id=wallet_id,
        passkey_credential_id=passkey_credential_id,
        verification_level="human_verified",
        billing_customer_id=billing_customer_id,
        site_id="lemma.id",
        site_role="developer",
        db=db,
    )
    upsert_platform_account(
        normalized,
        site_id="lemma_platform",
        site_role="developer",
        db=db,
    )
    return {
        "ppid": normalized,
        "account_type": "developer",
        "billing_customer_id": billing_customer_id,
    }


def ensure_owner_account(
    ppid: str,
    *,
    email: Optional[str] = None,
    db=None,
) -> None:
    """Ensure the platform owner has a canonical account row."""
    upsert_platform_account(
        ppid,
        account_type="owner",
        email=email,
        verification_level="human_verified",
        site_id="lemma.id",
        site_role="owner",
        db=db,
    )
    upsert_platform_account(
        ppid,
        site_id="lemma_platform",
        site_role="owner",
        db=db,
    )
