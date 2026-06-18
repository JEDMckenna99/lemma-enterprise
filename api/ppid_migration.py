"""
Site-scoped PPID migration after a wallet-bound document refresh.

When a user re-proves with a new government document number, Lemma merges the
wallet binding to the new LemmaPerson and can issue a signed, site-local
``lemma.ppid_migration.v1`` object so relying sites may opt in to updating an
existing account's PPID. Cross-site linkage is never exposed.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

PPID_MIGRATION_PREFIX = "lemma:ppid-migration:v1"
PPID_MIGRATION_TYPE = "lemma.ppid_migration.v1"
DEFAULT_MIGRATION_TTL_SECONDS = 3600


def _migration_ttl_seconds() -> int:
    try:
        return max(300, int(os.getenv("LEMMA_PPID_MIGRATION_TTL_SECONDS", str(DEFAULT_MIGRATION_TTL_SECONDS))))
    except (TypeError, ValueError):
        return DEFAULT_MIGRATION_TTL_SECONDS


def _max_merges_per_wallet_per_year() -> int:
    try:
        return max(1, int(os.getenv("LEMMA_PPID_MIGRATION_MAX_PER_YEAR", "2")))
    except (TypeError, ValueError):
        return 2


def pin_pending_merge_metadata(db, *, wallet_id: str, metadata: dict) -> dict:
    """Record the wallet's bound person at IDV start for merge eligibility."""
    from api.database import LemmaWalletBinding

    binding = db.query(LemmaWalletBinding).filter_by(wallet_id=wallet_id).first()
    person_id = binding.lemma_person_id if binding else None
    metadata = dict(metadata or {})
    if person_id:
        metadata["pending_merge_from_person_id"] = person_id
        metadata["merge_pinned_at_unix"] = int(time.time())
    return metadata


def wallet_has_sticky_revocation(db, wallet_id: str) -> bool:
    """True when a governance kill blocks amnesty (merge must fail closed)."""
    from api.database import RevocationList

    sticky = (
        db.query(RevocationList)
        .filter_by(wallet_id=wallet_id, revocation_type="wallet")
        .filter(RevocationList.is_amnesty_eligible.is_(False))
        .first()
    )
    return sticky is not None


def merge_count_last_year(db, wallet_id: str) -> int:
    from api.database import PersonMerge

    cutoff = datetime.utcnow() - timedelta(days=365)
    return (
        db.query(PersonMerge)
        .filter(
            PersonMerge.wallet_id == wallet_id,
            PersonMerge.created_at >= cutoff,
            PersonMerge.status == "completed",
        )
        .count()
    )


def record_person_merge(
    db,
    *,
    wallet_id: str,
    old_person_id: str,
    new_person_id: str,
    new_document_root_hash: str,
    provider_session_id: Optional[str] = None,
    old_document_root_hash: Optional[str] = None,
) -> Optional[str]:
    """Persist a completed wallet-bound person merge. Returns merge_id."""
    from api.database import PersonMerge

    if not wallet_id or not old_person_id or not new_person_id:
        return None
    if old_person_id == new_person_id:
        return None
    if wallet_has_sticky_revocation(db, wallet_id):
        logger.warning("Person merge denied: sticky wallet revocation wallet=%s", wallet_id[:24])
        return None
    if merge_count_last_year(db, wallet_id) >= _max_merges_per_wallet_per_year():
        logger.warning("Person merge denied: rate limit wallet=%s", wallet_id[:24])
        return None

    merge_id = f"merge_{secrets.token_urlsafe(16)}"
    row = PersonMerge(
        merge_id=merge_id,
        wallet_id=wallet_id,
        old_person_id=old_person_id,
        new_person_id=new_person_id,
        old_document_root_hash=old_document_root_hash,
        new_document_root_hash=new_document_root_hash,
        provider_session_id=provider_session_id,
        status="completed",
    )
    db.add(row)
    logger.info(
        "Person merge recorded merge=%s wallet=%s old=%s new=%s",
        merge_id,
        wallet_id[:24],
        old_person_id[:24],
        new_person_id[:24],
    )
    return merge_id


def latest_completed_merge_for_wallet(db, wallet_id: str):
    from api.database import PersonMerge

    return (
        db.query(PersonMerge)
        .filter_by(wallet_id=wallet_id, status="completed")
        .order_by(PersonMerge.created_at.desc())
        .first()
    )


def build_migration_canonical_message(payload: dict[str, Any]) -> bytes:
    lines = [
        PPID_MIGRATION_PREFIX,
        str(payload["type"]).strip(),
        str(payload["mergeId"]).strip(),
        str(payload["siteId"]).strip(),
        str(payload["legacyPpid"]).strip(),
        str(payload["currentPpid"]).strip(),
        str(payload["walletId"]).strip(),
        str(payload["nonce"]).strip(),
        str(payload["issuedAt"]),
        str(payload["expiresAt"]),
    ]
    return "\n".join(lines).encode("utf-8")


def sign_ppid_migration_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return payload with issuer metadata and Ed25519 signature."""
    from api.ishuman import _get_ishuman_issuer
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    issuer = _get_ishuman_issuer()
    message = build_migration_canonical_message(payload)
    digest = hashlib.sha256(message).digest()
    seed = bytes(issuer.signing_key_bytes())
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    signature_hex = sk.sign(digest).hex()
    signed = dict(payload)
    signed["issuerDid"] = issuer.get_did()
    signed["issuerPubkey"] = issuer.get_public_key_hex()
    signed["signature"] = signature_hex
    return signed


def verify_ppid_migration_signature(payload: dict[str, Any], trusted_pubkey_hex: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted_pubkey_hex))
        message = build_migration_canonical_message(payload)
        digest = hashlib.sha256(message).digest()
        pubkey.verify(bytes.fromhex(str(payload["signature"])), digest)
        return True
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False


def issue_ppid_migration_for_site(
    db,
    *,
    wallet_id: str,
    target_site: str,
    current_ppid: str,
) -> Optional[dict[str, Any]]:
    """Issue or return an active site-scoped migration token after a person merge."""
    from api.database import PpidMigrationIssued
    from api.identity_person import load_person_root_bytes
    from api.ppid import derive_ppid_from_person_root

    merge = latest_completed_merge_for_wallet(db, wallet_id)
    if not merge:
        return None

    now = datetime.utcnow()
    existing = (
        db.query(PpidMigrationIssued)
        .filter_by(merge_id=merge.merge_id, target_site=target_site)
        .filter(PpidMigrationIssued.consumed_at.is_(None))
        .filter(PpidMigrationIssued.expires_at > now)
        .order_by(PpidMigrationIssued.issued_at.desc())
        .first()
    )
    if existing:
        payload = {
            "type": PPID_MIGRATION_TYPE,
            "mergeId": merge.merge_id,
            "siteId": target_site,
            "legacyPpid": existing.legacy_ppid,
            "currentPpid": existing.current_ppid,
            "walletId": wallet_id,
            "nonce": existing.nonce,
            "issuedAt": int(existing.issued_at.timestamp()),
            "expiresAt": int(existing.expires_at.timestamp()),
        }
        return sign_ppid_migration_payload(payload)

    try:
        old_root = load_person_root_bytes(db, merge.old_person_id)
        legacy_ppid = derive_ppid_from_person_root(old_root, target_site)
    except ValueError:
        return None

    if legacy_ppid == current_ppid:
        return None

    ttl = _migration_ttl_seconds()
    issued_at = datetime.utcnow()
    expires_at = issued_at + timedelta(seconds=ttl)
    migration_id = f"mig_{secrets.token_urlsafe(16)}"
    nonce = secrets.token_urlsafe(16)

    row = PpidMigrationIssued(
        migration_id=migration_id,
        merge_id=merge.merge_id,
        wallet_id=wallet_id,
        target_site=target_site,
        legacy_ppid=legacy_ppid,
        current_ppid=current_ppid,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()

    payload = {
        "type": PPID_MIGRATION_TYPE,
        "mergeId": merge.merge_id,
        "siteId": target_site,
        "legacyPpid": legacy_ppid,
        "currentPpid": current_ppid,
        "walletId": wallet_id,
        "nonce": nonce,
        "issuedAt": int(issued_at.timestamp()),
        "expiresAt": int(expires_at.timestamp()),
    }
    return sign_ppid_migration_payload(payload)


def confirm_ppid_migration_for_site(
    db,
    *,
    target_site: str,
    legacy_ppid: str,
    current_ppid: str,
) -> dict[str, Any]:
    """Server-side approval check for relying sites with their own auth."""
    from api.database import PersonMerge, PpidMigrationIssued
    from api.identity_person import load_person_root_bytes
    from api.ppid import canonicalize_rp_id, derive_ppid_from_person_root

    site = canonicalize_rp_id(target_site)
    legacy = (legacy_ppid or "").strip()
    current = (current_ppid or "").strip()
    if not site or not legacy or not current:
        return {"approved": False, "reason": "invalid_input"}
    if legacy == current:
        return {"approved": False, "reason": "same_ppid"}

    now = datetime.utcnow()
    issued = (
        db.query(PpidMigrationIssued)
        .filter_by(target_site=site, legacy_ppid=legacy, current_ppid=current)
        .filter(PpidMigrationIssued.expires_at > now)
        .order_by(PpidMigrationIssued.issued_at.desc())
        .first()
    )
    if issued:
        merge = db.query(PersonMerge).filter_by(merge_id=issued.merge_id, status="completed").first()
        if merge:
            return {
                "approved": True,
                "merge_id": merge.merge_id,
                "migration_id": issued.migration_id,
                "expires_at_unix": int(issued.expires_at.timestamp()),
            }

    cutoff = now - timedelta(days=90)
    merges = (
        db.query(PersonMerge)
        .filter(PersonMerge.status == "completed", PersonMerge.created_at >= cutoff)
        .order_by(PersonMerge.created_at.desc())
        .limit(100)
        .all()
    )
    for merge in merges:
        try:
            old_root = load_person_root_bytes(db, merge.old_person_id)
            new_root = load_person_root_bytes(db, merge.new_person_id)
            derived_legacy = derive_ppid_from_person_root(old_root, site)
            derived_current = derive_ppid_from_person_root(new_root, site)
        except ValueError:
            continue
        if derived_legacy == legacy and derived_current == current:
            return {
                "approved": True,
                "merge_id": merge.merge_id,
                "expires_at_unix": int((merge.created_at + timedelta(days=365)).timestamp()),
            }

    return {"approved": False, "reason": "not_approved"}
