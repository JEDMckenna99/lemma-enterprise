"""Signed site-scoped PPID convergence artifacts (provisional -> known person)."""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

CONVERGENCE_PREFIX = "lemma:ppid-convergence:v1"
CONVERGENCE_SCHEMA = "ppid_convergence.v1"
CONVERGENCE_TTL_SECONDS = 3600


def build_convergence_canonical_message(artifact: dict, *, include_issuer: bool = True) -> bytes:
    """Byte-exact convergence signing input (see CANONICAL_MESSAGES.md §9)."""
    lines = [CONVERGENCE_PREFIX]
    if include_issuer:
        lines.append(str(artifact.get("issuer") or "").strip())
    lines.extend(
        [
            str(artifact.get("site_id") or "").strip(),
            str(artifact.get("legacy_ppid") or "").strip(),
            str(artifact.get("canonical_ppid") or "").strip(),
            str(artifact.get("convergence_id") or "").strip(),
            str(artifact.get("nonce") or "").strip(),
            str(int(artifact.get("issued_at_unix") or 0)),
            str(int(artifact.get("expires_at_unix") or 0)),
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _artifact_signing_issuer_did() -> str:
    from api.federated_signer import get_federated_signer, use_remote_federated_signer
    from api.ishuman import _get_ishuman_issuer

    if use_remote_federated_signer():
        return str(get_federated_signer().get_did() or "").strip()
    return str(_get_ishuman_issuer().get_did() or "").strip()


def _sign_convergence_digest(digest: bytes) -> tuple[str, str]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from api.federated_signer import get_federated_signer, use_remote_federated_signer
    from api.ishuman import _get_ishuman_issuer

    if use_remote_federated_signer():
        signer = get_federated_signer()
        return signer.sign_digest_hex(digest), signer.get_did()

    issuer = _get_ishuman_issuer()
    seed = bytes(issuer.signing_key_bytes())
    if len(seed) != 32:
        raise ValueError("issuer signing key seed must be 32 bytes")
    signature_hex = Ed25519PrivateKey.from_private_bytes(seed).sign(digest).hex()
    return signature_hex, issuer.get_did()


def sign_ppid_convergence_artifact(artifact: dict) -> dict:
    """Attach issuer + Ed25519 proof to a convergence artifact dict."""
    signed = dict(artifact)
    signed["issuer"] = _artifact_signing_issuer_did()
    message = build_convergence_canonical_message(signed, include_issuer=True)
    digest = hashlib.sha256(message).digest()
    signature_hex, issuer_did = _sign_convergence_digest(digest)
    signed["issuer"] = issuer_did
    signed["proof"] = {"signatureValueWeb": signature_hex}
    return signed


def _pubkeys_for_issuer(
    *,
    issuer_did: str,
    trusted_issuer_pubkeys: Optional[list[str]] = None,
    trusted_issuers: Optional[dict] = None,
) -> list[str]:
    did = str(issuer_did or "").strip()
    if not did:
        return []
    if trusted_issuers is not None:
        entry = trusted_issuers.get(did) if hasattr(trusted_issuers, "get") else None
        if entry is None:
            return []
        if hasattr(entry, "pubkeys_hex"):
            return sorted(str(p).lower() for p in entry.pubkeys_hex)
        if isinstance(entry, (set, list, tuple)):
            return sorted(str(p).lower() for p in entry)
        return []
    return [str(p).strip().lower() for p in (trusted_issuer_pubkeys or []) if str(p).strip()]


def verify_ppid_convergence_artifact(
    artifact: dict,
    *,
    site_id: str,
    canonical_ppid: str,
    trusted_issuer_pubkeys: Optional[list[str]] = None,
    trusted_issuers: Optional[dict] = None,
    expected_issuer_did: Optional[str] = None,
    now_unix: Optional[int] = None,
) -> tuple[bool, str]:
    """Verify a convergence artifact against the claimed issuer's keys only."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(artifact, dict):
        return False, "convergence_missing"
    if str(artifact.get("schema") or "") != CONVERGENCE_SCHEMA:
        return False, "convergence_schema_mismatch"
    issuer_did = str(artifact.get("issuer") or "").strip()
    if not issuer_did:
        return False, "convergence_issuer_missing"
    if expected_issuer_did and issuer_did != str(expected_issuer_did).strip():
        return False, "convergence_issuer_mismatch"
    if str(artifact.get("site_id") or "").strip() != str(site_id or "").strip():
        return False, "convergence_site_mismatch"
    if str(artifact.get("canonical_ppid") or "").strip() != str(canonical_ppid or "").strip():
        return False, "convergence_canonical_ppid_mismatch"

    now = int(now_unix if now_unix is not None else time.time())
    try:
        expires_at = int(artifact.get("expires_at_unix") or 0)
        issued_at = int(artifact.get("issued_at_unix") or 0)
    except (TypeError, ValueError):
        return False, "convergence_timestamps_invalid"
    if not issued_at or not expires_at or expires_at < now:
        return False, "convergence_expired"
    if issued_at > now + 300:
        return False, "convergence_issued_in_future"

    proof = artifact.get("proof") or {}
    signature_hex = str(proof.get("signatureValueWeb") or "").strip()
    if not signature_hex:
        return False, "convergence_signature_missing"
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False, "convergence_signature_malformed"

    unsigned = {
        key: artifact[key]
        for key in (
            "schema",
            "issuer",
            "convergence_id",
            "site_id",
            "legacy_ppid",
            "canonical_ppid",
            "issued_at_unix",
            "expires_at_unix",
            "nonce",
        )
        if key in artifact
    }
    pubkeys = _pubkeys_for_issuer(
        issuer_did=issuer_did,
        trusted_issuer_pubkeys=trusted_issuer_pubkeys,
        trusted_issuers=trusted_issuers,
    )
    if not pubkeys:
        return False, "convergence_untrusted_issuer"

    digests = [
        hashlib.sha256(build_convergence_canonical_message(unsigned, include_issuer=True)).digest(),
        hashlib.sha256(build_convergence_canonical_message(unsigned, include_issuer=False)).digest(),
    ]
    for digest in digests:
        for pubkey_hex in pubkeys:
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(signature, digest)
                return True, "valid"
            except (InvalidSignature, ValueError):
                continue
    return False, "convergence_invalid_signature"


def record_person_convergence_event(
    db,
    *,
    wallet_id: str,
    superseded_person_id: str,
    canonical_person_id: str,
    idv_session_id: Optional[str] = None,
) -> Optional[str]:
    """Persist a pending convergence event; returns convergence_id."""
    from api.database import PersonConvergenceEvent

    wallet_id = str(wallet_id or "").strip()
    superseded_person_id = str(superseded_person_id or "").strip()
    canonical_person_id = str(canonical_person_id or "").strip()
    if not wallet_id or not superseded_person_id or not canonical_person_id:
        return None
    if superseded_person_id == canonical_person_id:
        return None

    existing = (
        db.query(PersonConvergenceEvent)
        .filter_by(
            wallet_id=wallet_id,
            superseded_person_id=superseded_person_id,
            canonical_person_id=canonical_person_id,
            status="pending",
        )
        .first()
    )
    if existing:
        return existing.convergence_id

    convergence_id = f"conv_{secrets.token_urlsafe(16)}"
    row = PersonConvergenceEvent(
        convergence_id=convergence_id,
        wallet_id=wallet_id,
        superseded_person_id=superseded_person_id,
        canonical_person_id=canonical_person_id,
        idv_session_id=(idv_session_id or "").strip() or None,
        status="pending",
    )
    db.add(row)
    logger.info(
        "Recorded person convergence wallet=%s superseded=%s canonical=%s",
        wallet_id[:24],
        superseded_person_id[:24],
        canonical_person_id[:24],
    )
    return convergence_id


def issue_ppid_convergence_for_site(
    db,
    *,
    wallet_id: str,
    target_site: str,
    canonical_ppid: str,
    canonical_person_id: str,
) -> Optional[dict]:
    """Issue a single-use, site-scoped convergence artifact when needed."""
    from api.config import ppid_convergence_enabled
    from api.database import PersonConvergenceEvent, PpidConvergenceIssued
    from api.identity_person import load_person_root_bytes
    from api.ppid import derive_ppid_from_person_root

    if not ppid_convergence_enabled():
        return None

    wallet_id = str(wallet_id or "").strip()
    target_site = str(target_site or "").strip()
    canonical_ppid = str(canonical_ppid or "").strip()
    canonical_person_id = str(canonical_person_id or "").strip()
    if not wallet_id or not target_site or not canonical_ppid or not canonical_person_id:
        return None

    event = (
        db.query(PersonConvergenceEvent)
        .filter_by(
            wallet_id=wallet_id,
            canonical_person_id=canonical_person_id,
            status="pending",
        )
        .order_by(PersonConvergenceEvent.created_at.desc())
        .first()
    )
    if not event:
        return None

    now = datetime.utcnow()

    issued = (
        db.query(PpidConvergenceIssued)
        .filter_by(convergence_id=event.convergence_id, target_site=target_site)
        .first()
    )
    if issued and issued.consumed_at is not None:
        return None

    if issued and issued.consumed_at is None and issued.expires_at and issued.expires_at > now:
        unsigned = {
            "schema": CONVERGENCE_SCHEMA,
            "convergence_id": event.convergence_id,
            "site_id": target_site,
            "legacy_ppid": issued.legacy_ppid,
            "canonical_ppid": issued.canonical_ppid,
            "issued_at_unix": int(issued.issued_at.timestamp()),
            "expires_at_unix": int(issued.expires_at.timestamp()),
            "nonce": issued.nonce,
        }
        return sign_ppid_convergence_artifact(unsigned)

    try:
        superseded_root = load_person_root_bytes(db, event.superseded_person_id)
        legacy_ppid = derive_ppid_from_person_root(superseded_root, target_site)
    except Exception:
        logger.exception(
            "Failed to derive legacy PPID for convergence %s",
            event.convergence_id[:24],
        )
        return None

    if legacy_ppid == canonical_ppid:
        event.status = "completed"
        event.completed_at = now
        return None

    now_unix = int(time.time())
    expires_unix = now_unix + CONVERGENCE_TTL_SECONDS
    nonce = secrets.token_urlsafe(16)

    if not issued:
        issued = PpidConvergenceIssued(
            convergence_id=event.convergence_id,
            target_site=target_site,
            legacy_ppid=legacy_ppid,
            canonical_ppid=canonical_ppid,
            nonce=nonce,
            issued_at=now,
            expires_at=now + timedelta(seconds=CONVERGENCE_TTL_SECONDS),
        )
        db.add(issued)
    else:
        issued.legacy_ppid = legacy_ppid
        issued.canonical_ppid = canonical_ppid
        issued.nonce = nonce
        issued.issued_at = now
        issued.expires_at = now + timedelta(seconds=CONVERGENCE_TTL_SECONDS)
        issued.consumed_at = None

    unsigned = {
        "schema": CONVERGENCE_SCHEMA,
        "convergence_id": event.convergence_id,
        "site_id": target_site,
        "legacy_ppid": legacy_ppid,
        "canonical_ppid": canonical_ppid,
        "issued_at_unix": now_unix,
        "expires_at_unix": expires_unix,
        "nonce": nonce,
    }
    signed = sign_ppid_convergence_artifact(unsigned)
    return signed


def consume_ppid_convergence_artifact(
    db,
    *,
    convergence_id: str,
    target_site: str,
    nonce: str,
) -> bool:
    """Mark a convergence artifact consumed after a relying site accepts it."""
    from api.database import PpidConvergenceIssued

    row = (
        db.query(PpidConvergenceIssued)
        .filter_by(convergence_id=str(convergence_id or "").strip(), target_site=str(target_site or "").strip())
        .first()
    )
    if not row or row.consumed_at is not None:
        return False
    if str(row.nonce or "").strip() != str(nonce or "").strip():
        return False
    row.consumed_at = datetime.utcnow()
    return True


def purge_convergence_for_wallet(db, wallet_id: str) -> None:
    """Remove convergence rows during wallet erasure."""
    from api.database import PersonConvergenceEvent, PpidConvergenceIssued

    wallet_id = str(wallet_id or "").strip()
    if not wallet_id:
        return
    events = db.query(PersonConvergenceEvent).filter_by(wallet_id=wallet_id).all()
    convergence_ids = [row.convergence_id for row in events]
    if convergence_ids:
        db.query(PpidConvergenceIssued).filter(
            PpidConvergenceIssued.convergence_id.in_(convergence_ids)
        ).delete(synchronize_session=False)
    db.query(PersonConvergenceEvent).filter_by(wallet_id=wallet_id).delete(
        synchronize_session=False
    )
