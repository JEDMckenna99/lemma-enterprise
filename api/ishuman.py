"""
isHuman Network API
===================

Core product endpoints for the Lemma isHuman proof-of-humanity network.

Flows
-----
1. **Start verification**: create a Didit hosted IDV session and return the
   redirect URL.
2. **Didit webhook**: receive verification outcomes, issue an Ed25519-signed
   isHuman credential on approval.
3. **Site-block**: a site persistently blocks its site-private PPID.
4. **Site-doubt**: a site deliberately requests fresh IDV without a ban.
5. **Check**: return separate block and doubt decisions for one site.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from sqlalchemy.exc import IntegrityError

from auth.decorators import require_api_key
from api.column_crypto import encrypt_column

logger = logging.getLogger(__name__)

ishuman_bp = Blueprint("ishuman", __name__)

_WALLET_SECRET_REMOVED = {
    "success": False,
    "error": "wallet_secret_not_accepted",
    "message": (
        "wallet_secret is no longer accepted by isHuman endpoints; "
        "use wallet_assertion and person-root derivation"
    ),
}


def _reject_wallet_secret_payload(body) -> tuple | None:
    if isinstance(body, dict) and body.get("wallet_secret"):
        logger.warning("Rejected legacy wallet_secret payload on isHuman path")
        return jsonify(_WALLET_SECRET_REMOVED), 410
    return None


def _validate_client_ppid(ppid: str) -> bool:
    import re

    value = str(ppid or "").strip()
    return bool(re.match(r"^did:lemma:ppid_[0-9a-f]{64}$", value))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ISHUMAN_CREDENTIAL_TTL_DAYS = int(os.getenv("ISHUMAN_CREDENTIAL_TTL_DAYS", "365"))
ISHUMAN_SITE_CREDENTIAL_TTL_DAYS = int(
    os.getenv("ISHUMAN_SITE_CREDENTIAL_TTL_DAYS", "30")
)
STRIPE_IDENTITY_COST_CENTS = 200  # $2.00 per verification


def _default_credential_lifetime_seconds(site_id: Optional[str]) -> int:
    """Site-bound proofs renew monthly; master proofs use policy TTL by default.

    Master issuance passes an explicit ``ttl_seconds`` when document expiration
    is available from IDV (see ``_master_credential_ttl_seconds``).
    """
    if site_id and site_id not in ("lemma.id",):
        return ISHUMAN_SITE_CREDENTIAL_TTL_DAYS * 86400
    return ISHUMAN_CREDENTIAL_TTL_DAYS * 86400


def _document_expiration_date_from_record(record, db=None) -> Optional[str]:
    """Load document expiration from encrypted document-root row (not metadata)."""
    person_id = getattr(record, "lemma_person_id", None)
    if db and person_id:
        from api.identity_person import document_expiration_date_for_person

        resolved = document_expiration_date_for_person(db, person_id)
        if resolved:
            return resolved
    return None


def _master_expires_at_datetime(
    issued_at: datetime,
    document_expiration_date: Optional[str],
) -> datetime:
    """Master verification row expiry: document end-of-day when known, else policy TTL."""
    from api.identity_roots import document_expiration_end_of_day_utc

    doc_expiry = document_expiration_end_of_day_utc(document_expiration_date)
    if doc_expiry and doc_expiry > issued_at:
        return doc_expiry
    return issued_at + timedelta(days=ISHUMAN_CREDENTIAL_TTL_DAYS)


def _master_credential_ttl_seconds(
    document_expiration_date: Optional[str],
    *,
    issued_at: Optional[datetime] = None,
) -> int:
    """TTL for a master isHuman credential anchored to document expiration."""
    issued = issued_at or datetime.utcnow()
    expires = _master_expires_at_datetime(issued, document_expiration_date)
    return max(1, int((expires - issued).total_seconds()))


def _apply_master_expiry_to_record(record, document_expiration_date: Optional[str]) -> None:
    """Bind server-side master expiry to the verified document when available."""
    issued = datetime.utcnow()
    record.expires_at = _master_expires_at_datetime(issued, document_expiration_date)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ishuman_issuer():
    """Return the platform-wide isHuman credential issuer (KMS-backed)."""
    from api.issuer_management import get_issuer_manager
    return get_issuer_manager().get_federated_issuer()


def _browser_canonical_message(credential: dict) -> bytes:
    """Build the exact canonical message format used by ishuman-verifier.js.

    Mirrors `canonicalMessage(credential)` in static/js/ishuman-verifier.js:
    JSON.stringify({issuer, subject, claims: sorted, optional id, issuedAt, expiresAt})
    with JSON.stringify default separators and undefined-key omission.
    """
    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    sorted_claims: dict = {}
    for key in sorted(claims.keys()):
        value = claims[key]
        if value is True:
            sorted_claims[key] = "true"
        elif value is False:
            sorted_claims[key] = "false"
        elif isinstance(value, (list, dict)):
            sorted_claims[key] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        else:
            sorted_claims[key] = value

    payload: dict = {
        "issuer": credential.get("issuer"),
        "subject": credential.get("subject"),
        "claims": sorted_claims,
    }
    credential_id = str(credential.get("id") or "").strip()
    if credential_id:
        payload["id"] = credential_id
    if credential.get("issuedAt") is not None:
        payload["issuedAt"] = credential["issuedAt"]
    if credential.get("expiresAt") is not None:
        payload["expiresAt"] = credential["expiresAt"]

    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _assurance_meets_policy(actual: str | None, required: str) -> bool:
    if not actual:
        return False
    policy = (required or "ishuman").strip().lower()
    normalized = str(actual).strip().lower()
    if policy == "passkey":
        return normalized in ("passkey", "ishuman")
    return normalized == "ishuman"


def _sign_with_issuer_for_browser(credential: dict, issuer) -> str:
    """Sign the browser-canonical SHA-256 digest with the issuer's Ed25519 key.

    Returns hex-encoded 64-byte signature compatible with
    static/js/ishuman-verifier.js _verifyCredentialCore signature check.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    seed = bytes(issuer.signing_key_bytes())
    if len(seed) != 32:
        raise ValueError("issuer signing key seed must be 32 bytes")
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    message = _browser_canonical_message(credential)
    digest = hashlib.sha256(message).digest()
    return sk.sign(digest).hex()


def _issue_ishuman_credential(
    ppid: str,
    wallet_id: Optional[str] = None,
    site_id: Optional[str] = None,
    site_signing_pubkey: Optional[str] = None,
    ppid_derivation: Optional[str] = None,
    verification_method: str = "didit",
    ttl_seconds: Optional[int] = None,
    assurance: str = "ishuman",
) -> dict:
    """Sign and return a site or master credential for *ppid*.

    *assurance* is ``passkey`` (wallet-bound, pre-IDV) or ``ishuman`` (IDV-backed).
    Site PPIDs are identical across tiers; assurance records proof strength only.
    """
    issuer = _get_ishuman_issuer()
    now = int(time.time())
    prefix = "ishuman_site" if site_id else "ishuman_master"
    credential_id = f"{prefix}_{secrets.token_urlsafe(24)}"
    lifetime_seconds = (
        int(ttl_seconds)
        if ttl_seconds is not None
        else _default_credential_lifetime_seconds(site_id)
    )

    claims: dict = {
        "assurance": assurance or "ishuman",
        "verificationMethod": (verification_method or "didit"),
        "packageType": "identity",
        "siteId": site_id or "lemma.id",
        "issuedAt": str(now),
        "expiresAt": str(now + lifetime_seconds),
    }
    if (assurance or "ishuman") == "ishuman":
        claims["isHuman"] = True
    else:
        claims["isHuman"] = False
    is_lemma_master = not site_id or site_id == "lemma.id"
    if is_lemma_master:
        claims["siteDomain"] = "lemma.id"

    if is_lemma_master:
        from api.platform_owner import is_platform_owner_ppid

    if is_lemma_master and is_platform_owner_ppid(ppid):
        claims.update({
            "permissionId": "admin_access",
            "permission_level": "admin",
            "accountType": "admin",
            "credentialScope": "site_specific",
            "scope": ["admin", "write", "read", "developer"],
            "permissions": "admin_access",
        })
    if site_signing_pubkey:
        claims["site_signing_pubkey"] = site_signing_pubkey
    if ppid_derivation:
        claims["ppidDerivation"] = ppid_derivation

    # The Rust issuer accepts string claim values. Keep the public credential
    # shape typed, but sign over deterministic string forms that the browser
    # verifier also canonicalizes before Ed25519 verification.
    claims_for_issuer = {
        key: ("true" if value is True else "false" if value is False else str(value))
        for key, value in claims.items()
    }

    credential_json = issuer.issue_credential(ppid, claims_for_issuer)
    credential = json.loads(credential_json)
    credential["id"] = credential_id
    credential["claims"] = claims
    credential["credentialSubject"] = claims

    credential["issuerInfo"] = {
        "did": issuer.get_did(),
        "publicKey": issuer.get_public_key_hex(),
        "name": "Lemma isHuman Network",
        "verified": True,
    }

    # Add a parallel signature in the browser-verifier canonical format so the
    # JS isHuman verifier can locally verify credentials without bridging back
    # to the Rust crypto engine. The native Rust signature stays in
    # proof.signatureValue for server-side verification compatibility.
    try:
        browser_sig_hex = _sign_with_issuer_for_browser(credential, issuer)
        proof = credential.setdefault("proof", {})
        proof["signatureValueWeb"] = browser_sig_hex
    except Exception as exc:  # noqa: BLE001, non-fatal: server still has Rust sig
        logger.warning("Failed to add browser-format signature to credential: %s", exc)

    return credential


def _resolve_site_from_request_api_key():
    """Resolve Site from X-API-Key: legacy sites.api_key or customer-issued keys."""
    from api.site_access import resolve_site_from_api_key

    return resolve_site_from_api_key()


def _require_site_api_key():
    """Backward-compatible alias for site API key resolution."""
    return _resolve_site_from_request_api_key()


@ishuman_bp.route("/api/ishuman/site-binding-check", methods=["GET"])
@cross_origin()
def site_binding_check():
    """Read-only hostname binding check for SDK siteId alignment."""
    from api.database import SessionLocal
    from api.site_hostname import try_canonicalize_site_hostname
    from api.site_ppid_revocation import resolve_site_by_domain

    hostname = (
        request.args.get("hostname")
        or request.args.get("site_domain")
        or ""
    ).strip()
    canonical, err = try_canonicalize_site_hostname(hostname)
    if err:
        return jsonify({"success": False, "error": err}), 400

    db = SessionLocal()
    try:
        site = resolve_site_by_domain(db, canonical)
        return jsonify({
            "success": True,
            "canonical_hostname": canonical,
            "registered": site is not None,
            "site_id": getattr(site, "site_id", None) if site else None,
            "sdk_siteId_hint": canonical,
            "ppid_derivation_site": canonical,
        })
    finally:
        db.close()


def _resolve_person_id_for_wallet(db, wallet_id: Optional[str]) -> Optional[str]:
    """Resolve the canonical lemma_person_id for a wallet via its IDV binding.

    Every wallet that completed IDV has a LemmaWalletBinding (created in
    resolve_or_create_person_from_material). Resolving through it means any
    verified wallet takes the canonical person-root PPID path even if the
    immediate caller did not thread lemma_person_id through.
    """
    if not wallet_id or db is None:
        return None
    try:
        from api.database import LemmaWalletBinding

        binding = db.query(LemmaWalletBinding).filter_by(wallet_id=wallet_id).first()
        return getattr(binding, "lemma_person_id", None) if binding else None
    except Exception:
        return None


def _derive_ppid_for_site(
    *,
    rp_id: str,
    wallet_secret: Optional[str] = None,
    wallet_id: Optional[str] = None,
    lemma_person_id: Optional[str] = None,
    db=None,
    provisional: bool = False,
) -> str:
    """Derive site PPID from the person-root (canonical) path.

    The person-root path is the sole authoritative derivation: it is what issued
    credentials are bound to. The legacy wallet-secret path produces a DIFFERENT
    identifier, so using it after a person root exists silently mints a divergent
    identity (breaking account continuity).

    Convergence: when a db handle is available we resolve the person identity
    from the explicit ``lemma_person_id`` OR the wallet's IDV binding, so any
    verified wallet derives via person-root automatically. The wallet-secret
    path is reachable only for ``provisional`` callers (genuinely pre-IDV, where
    no person root exists yet) or when LEMMA_PPID_REQUIRE_PERSON_ROOT is disabled.
    Otherwise we fail closed rather than mint a divergent identity.
    """
    if db is not None:
        if not lemma_person_id:
            lemma_person_id = _resolve_person_id_for_wallet(db, wallet_id)
        if lemma_person_id:
            from api.identity_person import load_person_root_bytes
            from api.ppid import derive_ppid_from_person_root

            person_root = load_person_root_bytes(db, lemma_person_id)
            return derive_ppid_from_person_root(person_root, rp_id)
    elif lemma_person_id:
        # lemma_person_id supplied without a db handle: cannot load the person
        # root, so fall through to the fail-closed / provisional handling below.
        pass

    from api.config import ppid_require_person_root
    from api.ppid import derive_ppid_from_wallet_secret

    if ppid_require_person_root() and not provisional:
        raise ValueError(
            "person-root PPID required but unavailable; refusing legacy "
            "wallet-secret derivation that would mint a divergent identity"
        )
    if not wallet_secret:
        raise ValueError("wallet_secret or lemma_person_id required for PPID derivation")
    logger.warning(
        "Deriving PPID via legacy wallet-secret path for site=%s (provisional=%s); "
        "this yields a different identifier than the canonical person-root PPID "
        "and should only happen pre-IDV",
        rp_id,
        provisional,
    )
    return derive_ppid_from_wallet_secret(wallet_secret, rp_id)


def _derive_master_ppid_for_person(db, lemma_person_id: str) -> str:
    return _derive_ppid_for_site(rp_id="lemma.id", lemma_person_id=lemma_person_id, db=db)


def _complete_verified_ishuman_from_didit(
    db,
    record,
    *,
    wallet_id: str,
    decision: dict,
    workflow_id: Optional[str] = None,
) -> Optional[dict]:
    """Resolve document/person roots from a didit decision and issue the master VC.

    The decision is the (already HMAC-authenticated) didit webhook payload.
    Lemma still signs the credential with its own issuer key.
    Returns the credential dict on success, None on root material failure.
    """
    from api.identity_roots import IdentityRootMaterialError, validate_didit_workflow_id
    from api.identity_person import process_verified_didit_identity
    from api.ppid import derive_ppid_from_person_root_hash

    try:
        validate_didit_workflow_id(workflow_id)
        resolved = process_verified_didit_identity(
            db,
            decision=decision,
            wallet_id=wallet_id,
        )
    except IdentityRootMaterialError as exc:
        logger.error("Identity root material unavailable for didit decision: %s", exc)
        record.status = "failed"
        record.metadata_json = {
            **(record.metadata_json or {}),
            "root_error": str(exc),
        }
        return None
    except Exception as exc:
        from api.identity_person import WalletPersonBindingConflictError

        if isinstance(exc, WalletPersonBindingConflictError):
            logger.warning("Wallet/person binding conflict during didit issuance: %s", exc)
            record.status = "failed"
            record.metadata_json = {
                **(record.metadata_json or {}),
                "binding_error": str(exc),
            }
            return None
        raise

    if resolved.document_attached:
        record.metadata_json = {
            **(record.metadata_json or {}),
            "document_attached": True,
            "document_root_hash": resolved.document_root_hash,
        }

    if resolved.provisional_rebound and resolved.superseded_person_id:
        from api.ppid_convergence import record_person_convergence_event

        record_person_convergence_event(
            db,
            wallet_id=wallet_id,
            superseded_person_id=resolved.superseded_person_id,
            canonical_person_id=resolved.person_id,
            idv_session_id=getattr(record, "session_id", None),
        )

    ppid = derive_ppid_from_person_root_hash(resolved.person_root_hash, "lemma.id")
    record.lemma_person_id = resolved.person_id
    record.document_root_hash = encrypt_column(resolved.document_root_hash)
    record.root_version = resolved.root_version
    record.confidence_level = resolved.confidence_level

    try:
        _maybe_store_seed_envelopes(record, wallet_id, resolved.person_root_hash)
    except Exception:
        logger.exception("Seed-envelope generation failed (non-fatal) for wallet %s", wallet_id)

    credential = _issue_ishuman_credential(
        ppid,
        wallet_id,
        ppid_derivation="person_root_v1",
        verification_method="didit",
        ttl_seconds=_master_credential_ttl_seconds(resolved.document_expiration_date),
    )
    record.ppid = ppid
    _apply_master_expiry_to_record(record, resolved.document_expiration_date)
    return credential


def _maybe_pull_issue_didit(db, record) -> bool:
    """Pull-based issuance fallback for the status-poll endpoint.

    The didit webhook is the fast path, but if it is delayed or never delivered
    the user has completed (often paid for) IDV yet has no credential. Here we
    actively fetch the authenticated decision from didit and run the SAME
    issuance path the webhook uses. Returns True when the record ends up verified
    with a credential. Best-effort: never raises out of the poll handler.
    """
    from api.config import is_ishuman_pull_fallback_enabled

    if record.status == "verified" and record.credential_id:
        return True
    if not is_ishuman_pull_fallback_enabled():
        return False
    if (record.issuer_id or "") != "didit":
        return False
    if not record.provider_session_id or not record.wallet_id:
        return False

    try:
        from billing.didit_manager import DiditManager
        result = DiditManager().retrieve_session_decision(record.provider_session_id)
    except Exception:
        logger.exception(
            "Didit decision pull failed for session %s", record.provider_session_id
        )
        return False

    if not result.get("success") or result.get("status") != "approved":
        return False

    decision = result.get("decision") or {}
    workflow_id = decision.get("workflow_id") or result.get("workflow_id")
    try:
        credential = _complete_verified_ishuman_from_didit(
            db,
            record,
            wallet_id=record.wallet_id,
            decision=decision,
            workflow_id=workflow_id,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Pull-fallback issuance failed for session %s", record.provider_session_id
        )
        return False

    if not credential:
        # _complete_* may have marked the record failed (bad root material).
        db.commit()
        return False

    record.status = "verified"
    record.verified_at = datetime.utcnow()
    record.credential_id = credential.get("id")
    record.issued_at = datetime.utcnow()
    record.metadata_json = {
        **(record.metadata_json or {}),
        "credential_issuer_did": credential.get("issuerInfo", {}).get("did"),
        "ppid_derivation": "person_root_v1",
        "issued_via": "pull_fallback",
    }
    if not record.expires_at:
        _apply_master_expiry_to_record(record, _document_expiration_date_from_record(record, db))
    db.commit()
    logger.info(
        "isHuman credential issued via didit pull-fallback: credential_id=%s session=%s",
        credential.get("id"), record.provider_session_id,
    )
    _purge_didit_session_after_issuance(db, record)
    return True


def _purge_didit_session_after_issuance(db, record) -> None:
    """Best-effort delete of the upstream didit session after a terminal outcome.

    Didit "process-and-purge" data minimization: once Lemma has durably recorded
    the session outcome (credential issued, or declined/expired/abandoned), the
    raw IDV session (document image, liveness, decision) at didit is no longer
    needed, so we delete it from the upstream processor.

    Invariants:
      * Runs only after the caller has committed the terminal record state.
      * Never raises and never affects credentials the caller already issued.
      * Idempotent: skips if already purged; didit 404 counts as success.
    """
    from api.config import is_ishuman_didit_purge_enabled

    if not is_ishuman_didit_purge_enabled():
        return
    if (getattr(record, "issuer_id", "") or "") != "didit":
        return
    session_id = getattr(record, "provider_session_id", "") or ""
    if not session_id:
        return
    meta = record.metadata_json or {}
    if meta.get("didit_purged_at"):
        _scrub_terminal_provider_identifiers(record, session_id)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Failed to scrub provider identifier for already-purged session %s",
                session_id,
            )
        return

    try:
        from billing.didit_manager import DiditManager
        vendor_data = getattr(record, "wallet_id", "") or ""
        result = DiditManager().purge_verification_data(
            session_id,
            vendor_data=vendor_data,
        )
    except Exception:
        logger.exception(
            "Didit session purge raised (non-fatal) for session %s", session_id
        )
        return

    if not result.get("success"):
        logger.warning(
            "Didit session purge unsuccessful for session %s: %s",
            session_id, result.get("error"),
        )
        return

    _scrub_terminal_provider_identifiers(record, session_id)
    record.metadata_json = {
        **meta,
        "didit_purged_at": datetime.utcnow().isoformat() + "Z",
    }
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to persist didit purge marker for session %s", session_id
        )
    logger.info("Purged upstream didit session %s after issuance", session_id)


def _scrub_terminal_provider_identifiers(record, session_id: str) -> None:
    """Keep only a keyed hash of the upstream provider session id."""
    from api.privacy_hashes import hash_provider_identifier

    provider = getattr(record, "issuer_id", None) or "didit"
    if not getattr(record, "provider_session_id_hash", None):
        record.provider_session_id_hash = hash_provider_identifier(
            provider,
            session_id,
            label="session",
        )
    record.provider_session_id = None


def resolve_wallet_id_for_ppid(db, ppid: str) -> Optional[str]:
    """Resolve only a master/lemma.id PPID; site PPIDs are intentionally unlinkable."""
    if not ppid:
        return None

    from api.database import IsHumanVerification

    master = (
        db.query(IsHumanVerification)
        .filter_by(ppid=ppid, status="verified")
        .order_by(IsHumanVerification.verified_at.desc())
        .first()
    )
    if master and master.wallet_id:
        return master.wallet_id

    master_any = (
        db.query(IsHumanVerification)
        .filter_by(ppid=ppid)
        .order_by(IsHumanVerification.created_at.desc())
        .first()
    )
    if master_any and master_any.wallet_id:
        return master_any.wallet_id

    return None


def revoke_wallet_network_wide(
    db,
    *,
    wallet_id: Optional[str] = None,
    master_credential_id: Optional[str] = None,
    reason: str = "network revocation",
    revoked_by: str = "admin",
) -> dict:
    """Revoke a wallet and its master credentials without enumerating sites.

    Shared core for the admin approve-revocation route and the didit risk feed
    (Phase 2 / M3). Creates wallet/credential RevocationList rows, marks rows
    revoked, commits, and publishes events so the Bloom snapshot rebuilds.

    Raises ValueError if the wallet cannot be resolved.
    """
    from api.database import IsHumanVerification, RevocationList

    if not wallet_id and master_credential_id:
        master = db.query(IsHumanVerification).filter_by(
            credential_id=master_credential_id
        ).first()
        if master:
            wallet_id = master.wallet_id
    if not wallet_id:
        raise ValueError("could not resolve wallet_id")

    revoked_ids: list[str] = []

    existing_wallet_revoke = (
        db.query(RevocationList)
        .filter_by(wallet_id=wallet_id, revocation_type="wallet")
        .first()
    )
    if not existing_wallet_revoke:
        db.add(RevocationList(
            lemma_id=f"wallet_revoke_{wallet_id[:32]}_{int(time.time())}",
            credential_id=None,
            lemma_type="ishuman",
            wallet_id=wallet_id,
            revocation_type="wallet",
            revoked_by=revoked_by,
            reason=reason,
        ))
        revoked_ids.append(wallet_id)

    masters = db.query(IsHumanVerification).filter_by(
        wallet_id=wallet_id, status="verified"
    ).all()
    for m in masters:
        if m.credential_id:
            db.add(RevocationList(
                lemma_id=m.credential_id,
                credential_id=m.credential_id,
                lemma_type="ishuman",
                revocation_type="credential",
                revoked_by=revoked_by,
                reason=reason,
            ))
            revoked_ids.append(m.credential_id)
            m.status = "revoked"

    db.commit()

    try:
        from api.revocation_sync import get_event_bus
        bus = get_event_bus()
        for rid in revoked_ids:
            bus.publish_revocation(rid, credential_type="ishuman")
    except Exception as exc:
        logger.warning("Bloom sync publish failed (non-fatal): %s", exc)

    return {
        "wallet_id": wallet_id,
        "revoked_credential_ids": revoked_ids,
        "master_count": len(masters),
        "derived_count": 0,
    }


def _handle_didit_risk_event(webhook_type: str, status: str, body: dict) -> None:
    """Map a didit ongoing risk event to a network revocation (Phase 2 / M3).

    didit's continuous monitoring (block, AML hit, fraud transaction) is an
    authoritative downstream signal: when a previously-verified human is blocked
    or flagged, we revoke their Lemma credential network-wide so every relying
    site enforces it locally via the Bloom snapshot, with no per-request didit
    calls and no PII leaving didit.

    Correlation: didit echoes our ``vendor_data`` (the IsHumanVerification id /
    wallet) on session events; user-entity events carry the consolidated user.
    We resolve the wallet via vendor_data or provider_session_id.
    """
    # Only act on terminal/negative signals. APPROVED transitions are no-ops.
    negative = status in ("blocked", "declined", "rejected", "suspended")
    is_risk_family = webhook_type in (
        "user.status.updated", "user.data.updated", "data.updated",
        "transaction.status.updated", "transaction.created",
    )
    if not (is_risk_family and negative):
        return

    vendor_data = body.get("vendor_data") or ""
    session_id = body.get("session_id") or ""

    from api.database import SessionLocal, IsHumanVerification
    db = SessionLocal()
    try:
        record = None
        if session_id:
            record = db.query(IsHumanVerification).filter_by(
                provider_session_id=session_id
            ).first()
        if not record and vendor_data:
            record = (
                db.query(IsHumanVerification).filter_by(session_id=vendor_data).first()
                or db.query(IsHumanVerification).filter_by(wallet_id=vendor_data).first()
            )
        if not record or not record.wallet_id:
            logger.warning(
                "Didit risk event (%s/%s) could not be correlated to a wallet",
                webhook_type, status,
            )
            return

        result = revoke_wallet_network_wide(
            db,
            wallet_id=record.wallet_id,
            reason=f"didit_risk:{webhook_type}:{status}",
            revoked_by="didit_risk_feed",
        )
        logger.info(
            "Didit risk feed revoked wallet=%s total=%d (%s/%s)",
            record.wallet_id[:20], len(result["revoked_credential_ids"]),
            webhook_type, status,
        )
    finally:
        db.close()


def _maybe_store_seed_envelopes(record, wallet_id: str, person_root_hash: str) -> None:
    """Derive + seal wallet_local_seed and person_root_proxy onto *record*.

    No-op unless LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS is enabled and the wallet
    posted a valid X25519 ``enc_pubkey`` at start-verification.
    """
    from api.seed_envelope import (
        SEED_VERSION,
        derive_person_root_proxy,
        derive_wallet_local_seed,
        seal_envelope,
        use_person_root_seeds_enabled,
    )

    if not use_person_root_seeds_enabled():
        return
    enc_pubkey_b64 = ((record.metadata_json or {}).get("enc_pubkey") or "").strip()
    if not enc_pubkey_b64:
        return
    try:
        recipient_pub = _b64url_decode_32(enc_pubkey_b64)
    except ValueError:
        logger.warning("Invalid enc_pubkey for wallet %s; skipping seed envelopes", wallet_id)
        return

    person_root = bytes.fromhex(person_root_hash)
    wallet_local_seed = derive_wallet_local_seed(person_root, wallet_id)
    person_root_proxy = derive_person_root_proxy(person_root)

    record.wallet_seed_envelope = seal_envelope(recipient_pub, wallet_local_seed)
    record.person_root_proxy_envelope = seal_envelope(recipient_pub, person_root_proxy)
    record.seed_version = SEED_VERSION


def _b64url_decode_32(value: str) -> bytes:
    """Decode a base64url (or standard base64) 32-byte X25519 public key."""
    raw = value.strip()
    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + pad)
    except Exception:
        decoded = base64.b64decode(raw + pad)
    if len(decoded) != 32:
        raise ValueError("encryption pubkey must decode to 32 bytes")
    return decoded


def _append_url_query(url: str, key: str, value: str) -> str:
    """Append or replace a single query parameter on *url*."""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key] = value
    new_query = urlencode(query)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))


def _require_wallet_assertion(body: dict, *, field_names: list[str]) -> tuple:
    """Verify wallet_assertion on protected endpoints; return (error_response, None) or (None, ok)."""
    from api.wallet_authn import assertion_error_response, verify_assertion_from_body

    wallet_id = str(body.get("wallet_id") or "").strip()
    result, _fields = verify_assertion_from_body(
        body,
        wallet_id=wallet_id,
        field_names=field_names,
    )
    if not result.ok:
        return assertion_error_response(result), None
    return None, wallet_id


def _deny_if_derivation_revoked(
    db,
    *,
    master_credential_id: str,
    wallet_id: str,
    target_site: str,
    lemma_person_id: Optional[str] = None,
) -> Optional[str]:
    """Return an error code if derivation must be denied for revocation/block."""
    from api.revocation_verifier import check_revocation_candidate
    from api.site_ppid_revocation import (
        is_site_ppid_blocked,
        is_site_user_ppid_revoked,
        resolve_site_by_domain,
    )

    master_status = check_revocation_candidate(master_credential_id)
    if master_status == "revoked":
        return "master_credential_revoked"
    if master_status == "unavailable":
        return "revocation_unavailable"

    try:
        site_ppid = _derive_ppid_for_site(
            rp_id=target_site,
            wallet_id=wallet_id,
            lemma_person_id=lemma_person_id,
            db=db,
        )
    except ValueError:
        return "ppid_derivation_failed"

    # Site-bound PPID bans are DB-backed (SiteBlock + user RevocationList).
    # Do not deny from Bloom alone: Bloom is append-only and stays poisoned
    # after an authenticated site unban until a process-wide rebuild.
    site = resolve_site_by_domain(db, target_site)
    if site and is_site_ppid_blocked(db, site_id=site.site_id, ppid=site_ppid):
        return "site_ppid_blocked"
    if is_site_user_ppid_revoked(
        db,
        ppid=site_ppid,
        site_id=site.site_id if site else None,
    ):
        return "site_ppid_revoked"

    return None


def _normalize_site_signing_pubkey(pubkey: str) -> str:
    value = str(pubkey or "").strip()
    if not value:
        raise ValueError("site_signing_pubkey required")
    padded = value + ("=" * (-len(value) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise ValueError("site_signing_pubkey invalid") from exc
    if len(decoded) != 32:
        raise ValueError("site_signing_pubkey invalid length")
    return value


# ---------------------------------------------------------------------------
# 1. Start Verification
# ---------------------------------------------------------------------------

_IDV_HANDOFF_MK_FAIL_MAX = 5
_IDV_HANDOFF_CLAIM_IP_LIMIT = 30
_IDV_HANDOFF_CLAIM_IP_WINDOW_SECONDS = 900
_IDV_HANDOFF_CLAIM_HANDOFF_LIMIT = 10


def _idv_handoff_ttl_seconds() -> int:
    from api.config import ishuman_idv_handoff_ttl_seconds

    return ishuman_idv_handoff_ttl_seconds()


def _handoff_mk_fingerprint(mk: str) -> str:
    return hashlib.sha256(str(mk or "").encode("utf-8")).hexdigest()


def _handoff_mk_fail_key(handoff_id: str) -> str:
    return f"ishuman:idv-handoff-mk-fail:{handoff_id}"


def _handoff_mk_fail_count(handoff_id: str) -> int:
    from auth.redis_store import get as redis_get

    entry = redis_get(_handoff_mk_fail_key(handoff_id))
    if not entry:
        return 0
    try:
        return int(entry.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def _increment_handoff_mk_fail(handoff_id: str) -> int:
    from auth.redis_store import store as redis_store

    count = _handoff_mk_fail_count(handoff_id) + 1
    redis_store(
        _handoff_mk_fail_key(handoff_id),
        {"count": count},
        ttl_seconds=_idv_handoff_ttl_seconds(),
    )
    return count


def _client_ip_hash() -> str:
    ip = (request.remote_addr or "").strip()
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def _log_handoff_security_event(event: str, **fields) -> None:
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("handoff_security event=%s %s", event, parts)


def _validate_handoff_mk(mk: str, entry: dict) -> bool:
    stored = str(entry.get("mk_fingerprint") or "").strip()
    if not stored or not mk:
        return False
    return _handoff_mk_fingerprint(mk) == stored


def _validate_handoff_verification_session(session_id: str, entry: dict) -> bool:
    from api.database import SessionLocal, IsHumanVerification

    wallet_id = str(entry.get("wallet_id") or "").strip()
    session_id = (session_id or "").strip()
    if not wallet_id or not session_id:
        return False

    db = SessionLocal()
    try:
        row = (
            db.query(IsHumanVerification)
            .filter(IsHumanVerification.session_id == session_id)
            .first()
        )
        if not row:
            return False
        if str(row.wallet_id or "").strip() != wallet_id:
            return False
        if row.status not in ("pending", "verified"):
            return False

        ttl = _idv_handoff_ttl_seconds()
        now = datetime.now(timezone.utc)
        created_at = row.created_at
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (now - created_at).total_seconds() > ttl:
                return False

        if row.status == "verified" and row.verified_at:
            verified_at = row.verified_at
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=timezone.utc)
            if (now - verified_at).total_seconds() > ttl:
                return False

        return True
    finally:
        db.close()


def _idv_mobile_handoff_key(handoff_id: str) -> str:
    return f"ishuman:idv-handoff:{handoff_id}"


def _idv_mobile_handoff_session_key(session_id: str) -> str:
    return f"ishuman:idv-handoff-session:{session_id}"


def _store_idv_mobile_handoff(
    *,
    handoff_id: str,
    session_id: str,
    wallet_id: str,
    encrypted_blob: str,
    mk_fingerprint: str = "",
) -> None:
    """Persist a one-time mobile handoff under handoff_id and session_id keys."""
    from auth.redis_store import store as redis_store

    ttl_seconds = _idv_handoff_ttl_seconds()
    entry = {
        "handoff_id": handoff_id,
        "wallet_id": wallet_id,
        "session_id": session_id,
        "encrypted_blob": encrypted_blob,
    }
    if mk_fingerprint:
        entry["mk_fingerprint"] = mk_fingerprint
    redis_store(
        _idv_mobile_handoff_key(handoff_id),
        entry,
        ttl_seconds=ttl_seconds,
    )
    redis_store(
        _idv_mobile_handoff_session_key(session_id),
        entry,
        ttl_seconds=ttl_seconds,
    )


def _delete_idv_mobile_handoff_entry(entry: dict) -> bool:
    """Delete both Redis keys for a handoff entry (one-time claim)."""
    from auth.redis_store import delete as redis_delete

    deleted = False
    handoff_id = str(entry.get("handoff_id") or "").strip()
    session_id = str(entry.get("session_id") or "").strip()
    if handoff_id:
        deleted = redis_delete(_idv_mobile_handoff_key(handoff_id)) or deleted
    if session_id:
        deleted = redis_delete(_idv_mobile_handoff_session_key(session_id)) or deleted
    return deleted


def _lookup_idv_mobile_handoff(*, handoff_id: str = "", session_id: str = "") -> Optional[dict]:
    from auth.redis_store import get as redis_get

    handoff_id = (handoff_id or "").strip()
    session_id = (session_id or "").strip()
    if handoff_id:
        entry = redis_get(_idv_mobile_handoff_key(handoff_id))
        if entry:
            return entry
    if session_id:
        return redis_get(_idv_mobile_handoff_session_key(session_id))
    return None


def _resolve_start_verification_session_id(db, wallet_id: str, return_url: str) -> str:
    """Reuse a recent in-flight session when the same return URL is retried."""
    from datetime import timedelta

    from api.database import IsHumanVerification

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    pending_rows = (
        db.query(IsHumanVerification)
        .filter(
            IsHumanVerification.wallet_id == wallet_id,
            IsHumanVerification.status == "pending",
            IsHumanVerification.created_at >= cutoff,
        )
        .order_by(IsHumanVerification.created_at.desc())
        .all()
    )
    for row in pending_rows:
        meta_return = str((row.metadata_json or {}).get("return_url") or "")
        if meta_return == return_url:
            return row.session_id
    return f"ishuman_sess_{secrets.token_urlsafe(16)}"


def start_verification_for_body(body: dict) -> tuple[dict, int]:
    """Run start-verification logic for a JSON body (shared with demo routes)."""
    body = body or {}
    rejected = _reject_wallet_secret_payload(body)
    if rejected:
        return rejected[0].get_json(), rejected[1]

    wallet_id = body.get("wallet_id")
    if not wallet_id:
        return {"success": False, "error": "wallet_id required"}, 400

    return_url = body.get(
        "return_url",
        os.getenv("ISHUMAN_RETURN_URL", "https://lemma.id/app"),
    )
    handoff_id = str(body.get("handoff_id") or "").strip()
    encrypted_blob = str(body.get("encrypted_blob") or "").strip()
    handoff_mk_fingerprint = str(body.get("handoff_mk_fingerprint") or "").strip()
    handoff_requested = bool(handoff_id)
    if handoff_requested and not handoff_id:
        return {"success": False, "error": "missing_handoff_fields"}, 400
    if handoff_id and len(handoff_id) < 16:
        return {"success": False, "error": "weak_handoff_id"}, 400

    if handoff_requested:
        from api.config import (
            is_ishuman_idv_handoff_strict_claim_enabled,
            is_ishuman_idv_mobile_handoff_enabled,
        )
        if not is_ishuman_idv_mobile_handoff_enabled():
            return {"success": False, "error": "mobile_handoff_disabled"}, 404
        if is_ishuman_idv_handoff_strict_claim_enabled() and not handoff_mk_fingerprint:
            return {"success": False, "error": "missing_handoff_mk_fingerprint"}, 400

    purpose = str(body.get("purpose") or "").strip()
    lost_device_recovery = purpose == "lost_device_recovery"
    if lost_device_recovery:
        from api.database import SessionLocal
        from api.wallet_authn import _wallet_has_established_identity

        db = SessionLocal()
        try:
            if not _wallet_has_established_identity(db, str(wallet_id).strip()):
                return {
                    "success": False,
                    "error": "recovery_identity_required",
                    "code": "recovery_identity_required",
                }, 403
        finally:
            db.close()
    else:
        assertion_fields = ["return_url"]
        if handoff_id:
            assertion_fields.append("handoff_id")
        if handoff_mk_fingerprint:
            assertion_fields.append("handoff_mk_fingerprint")
        err, _wid = _require_wallet_assertion(body, field_names=assertion_fields)
        if err:
            return err[0].get_json(), err[1]

    from api.database import SessionLocal, IsHumanVerification
    db = SessionLocal()
    try:
        # Pre-generate (or reuse) the Lemma session id so it can be embedded in
        # the Didit callback URL (mobile browsers lack the popup localStorage key).
        session_id = _resolve_start_verification_session_id(db, wallet_id, return_url)
    finally:
        db.close()

    provider_return_url = _append_url_query(return_url, "ishuman_session", session_id)

    # isHuman IDV runs exclusively on Didit and fails closed if unconfigured.
    provider = (body.get("provider") or "didit").strip().lower()
    if provider != "didit":
        return {"success": False, "error": "unsupported_provider"}, 400
    from api.config import is_ishuman_didit_enabled
    if not is_ishuman_didit_enabled():
        return {"success": False, "error": "didit_not_enabled"}, 400
    from billing.didit_manager import DiditManager
    result = DiditManager().create_identity_verification_session(
        user_id=wallet_id,
        return_url=provider_return_url,
    )
    if not result.get("success"):
        logger.error("Didit session creation failed: %s", result)
        return {"success": False, "error": result.get("error", "didit_error")}, 502

    provider_session_id = result["session_id"]

    db = SessionLocal()
    handoff_stored = False
    try:
        derived_ppid = None
        client_ppid = (body.get("ppid") or "").strip()
        if client_ppid:
            if not _validate_client_ppid(client_ppid):
                return {"success": False, "error": "invalid_ppid"}, 400
            derived_ppid = client_ppid

        # v2 (Phase 1.1): the wallet may post a one-time X25519 encryption
        # pubkey so the server can seal person-root seed envelopes at IDV
        # completion. Stored as metadata; ignored unless the feature is enabled.
        verification_metadata = {"return_url": return_url}
        if lost_device_recovery:
            verification_metadata["purpose"] = "lost_device_recovery"
        return_params = dict(parse_qsl(urlparse(return_url).query, keep_blank_values=True))
        if return_params.get("issue_mode") == "fresh_idv":
            from api.ppid import canonicalize_rp_id

            fresh_site = canonicalize_rp_id(return_params.get("site_id") or "")
            if fresh_site and fresh_site != "unknown":
                verification_metadata["fresh_idv_site"] = fresh_site
                verification_metadata["fresh_idv_consumed"] = False
        enc_pubkey = (body.get("enc_pubkey") or "").strip()
        if enc_pubkey:
            verification_metadata["enc_pubkey"] = enc_pubkey

        # Dedup: the provider can reuse one hosted session across repeated
        # start-verification calls (e.g. the user re-clicks before redirect).
        # Reuse the existing in-flight row for this provider session + wallet so
        # the hosted session maps to exactly ONE local record: otherwise the
        # webhook only flips the first sibling to verified and a client polling
        # the other sibling sees 'pending' forever.
        existing = (
            db.query(IsHumanVerification)
            .filter(
                IsHumanVerification.provider_session_id == provider_session_id,
                IsHumanVerification.wallet_id == wallet_id,
            )
            .order_by(IsHumanVerification.created_at.desc())
            .first()
        )
        if existing and existing.status not in ("verified", "failed", "expired", "canceled"):
            existing.metadata_json = {**(existing.metadata_json or {}), **verification_metadata}
            if derived_ppid and not existing.ppid:
                existing.ppid = derived_ppid
            db.commit()
            session_id = existing.session_id
        else:
            verification = IsHumanVerification(
                session_id=session_id,
                stripe_session_id=None,
                provider_session_id=provider_session_id,
                issuer_id=provider,
                wallet_id=wallet_id,
                ppid=derived_ppid,
                status="pending",
                metadata_json=verification_metadata,
            )
            db.add(verification)
            try:
                db.commit()
            except IntegrityError:
                # Lost a concurrent race to create the row for this
                # (provider_session_id, wallet_id): the unique index
                # (migration 028) rejected the duplicate insert. Recover by
                # reusing the row the winner created so both callers map to the
                # single canonical record instead of erroring out.
                db.rollback()
                winner = (
                    db.query(IsHumanVerification)
                    .filter(
                        IsHumanVerification.provider_session_id == provider_session_id,
                        IsHumanVerification.wallet_id == wallet_id,
                    )
                    .order_by(IsHumanVerification.created_at.desc())
                    .first()
                )
                if not winner:
                    raise
                winner.metadata_json = {**(winner.metadata_json or {}), **verification_metadata}
                if derived_ppid and not winner.ppid:
                    winner.ppid = derived_ppid
                db.commit()
                session_id = winner.session_id

        if handoff_requested and encrypted_blob:
            try:
                _store_idv_mobile_handoff(
                    handoff_id=handoff_id,
                    session_id=session_id,
                    wallet_id=str(wallet_id),
                    encrypted_blob=encrypted_blob,
                    mk_fingerprint=handoff_mk_fingerprint,
                )
                handoff_stored = True
                logger.info(
                    "IDV mobile handoff stored handoff=%s session=%s wallet=%s",
                    handoff_id[:24],
                    session_id[:24],
                    str(wallet_id)[:24],
                )
            except Exception:
                logger.exception("Failed to store IDV mobile handoff during start-verification")
                return {"success": False, "error": "handoff_store_failed"}, 500
    except Exception:
        db.rollback()
        logger.exception("Failed to persist isHuman verification session")
        return {"success": False, "error": "verification_session_persist_failed"}, 500
    finally:
        db.close()

    logger.info(
        "isHuman verification started: %s (provider=%s session=%s handoff=%s)",
        session_id,
        provider,
        provider_session_id,
        handoff_id or "-",
    )

    payload = {
        "success": True,
        "session_id": session_id,
        "provider": provider,
        "provider_session_id": provider_session_id,
        "url": result.get("url"),
    }
    if handoff_requested:
        payload["handoff_stored"] = handoff_stored
        payload["handoff_expires_in"] = _idv_handoff_ttl_seconds()
    return payload, 200


@ishuman_bp.route("/api/ishuman/start-verification", methods=["POST"])
@cross_origin()
def start_verification():
    """Create a Didit hosted IDV session for a new isHuman verification.

    Request body::

        {
            "wallet_id": "...",       // browser wallet id
            "return_url": "..."       // optional, defaults to lemma.id/app
        }

    Returns the hosted verification URL for redirect.
    """
    body = request.get_json(silent=True) or {}
    payload, status = start_verification_for_body(body)
    return jsonify(payload), status


# ---------------------------------------------------------------------------
# 2. Didit Identity Webhook
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/webhooks/didit-identity", methods=["POST"])
def didit_identity_webhook():
    """Receive didit verification webhooks (X-Signature-V2 authenticated).

    On an ``Approved`` ``status.updated`` event we resolve the document/person
    roots from the carried decision and issue a Lemma-signed isHuman credential.
    Ongoing risk events (user.status.updated BLOCKED, data.updated AML) are
    routed to the revocation handler (Phase 2 / M3).
    """
    from api.config import is_ishuman_didit_enabled
    if not is_ishuman_didit_enabled():
        return jsonify({"error": "didit_not_enabled"}), 404

    from billing.didit_manager import DiditManager, DiditWebhookError

    try:
        body = DiditManager().verify_webhook(
            request.data,
            x_signature_v2=request.headers.get("X-Signature-V2"),
            x_timestamp=request.headers.get("X-Timestamp"),
        )
    except DiditWebhookError as exc:
        logger.warning("Didit webhook verification failed: %s", exc)
        return jsonify({"error": "invalid_signature"}), 401

    webhook_type = str(body.get("webhook_type") or "").strip().lower()
    status = str(body.get("status") or "").strip().lower()
    session_id = body.get("session_id") or ""
    event_id = body.get("event_id") or ""

    logger.info(
        "Didit webhook: type=%s status=%s session=%s event=%s",
        webhook_type, status, session_id, event_id,
    )

    # Ongoing risk / monitoring events drive network revocation (M3).
    if webhook_type in ("user.status.updated", "user.data.updated", "data.updated",
                        "transaction.status.updated", "transaction.created"):
        try:
            _handle_didit_risk_event(webhook_type, status, body)
        except Exception:
            logger.exception("Didit risk event handling failed (non-fatal)")
        return jsonify({"received": True}), 200

    if webhook_type and webhook_type != "status.updated":
        # Unhandled event family; acknowledge so didit does not retry.
        return jsonify({"received": True}), 200

    from api.database import SessionLocal, IsHumanVerification
    db = SessionLocal()
    try:
        record = db.query(IsHumanVerification).filter_by(
            provider_session_id=session_id
        ).first()
        if not record:
            logger.warning("No verification record for didit session %s", session_id)
            return jsonify({"received": True}), 200

        # Idempotency: a re-delivered Approved event must not re-issue.
        if status == "approved" and record.status == "verified":
            return jsonify({"received": True}), 200

        if status == "approved":
            decision = body.get("decision") or {}
            wallet_id = record.wallet_id or ""
            credential = _complete_verified_ishuman_from_didit(
                db,
                record,
                wallet_id=wallet_id,
                decision=decision,
                workflow_id=body.get("workflow_id"),
            )
            if not credential:
                db.commit()
                return jsonify({"received": True}), 200

            record.status = "verified"
            record.verified_at = datetime.utcnow()
            record.credential_id = credential.get("id")
            record.issued_at = datetime.utcnow()
            if not record.expires_at:
                _apply_master_expiry_to_record(
                    record,
                    _document_expiration_date_from_record(record, db),
                )
            record.metadata_json = {
                **(record.metadata_json or {}),
                "credential_issuer_did": credential.get("issuerInfo", {}).get("did"),
                "ppid_derivation": "person_root_v1",
            }
            db.commit()

            logger.info(
                "isHuman credential issued via didit: ppid=%s credential_id=%s person=%s",
                (record.ppid or "")[:40], credential.get("id"), record.lemma_person_id,
            )

            try:
                from api.site_ppid_revocation import clear_amnesty_eligible_wallet_revocations
                clear_amnesty_eligible_wallet_revocations(
                    db,
                    wallet_id=wallet_id,
                    new_master_credential_id=credential.get("id") or "",
                    reason="didit_verified",
                )
            except Exception:
                logger.exception(
                    "Failed to clear amnesty-eligible revocations after didit verified for wallet %s",
                    wallet_id,
                )

            _purge_didit_session_after_issuance(db, record)

        elif status in ("declined", "expired", "abandoned"):
            record.status = "failed" if status == "declined" else status
            db.commit()
            _purge_didit_session_after_issuance(db, record)

        return jsonify({"received": True}), 200

    except Exception:
        db.rollback()
        logger.exception("Error processing didit webhook")
        return jsonify({"error": "processing_failed"}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2b. Poll for credential (client polls after IDV completes)
# ---------------------------------------------------------------------------


def _resolve_verification_status_record(db, session_id: str):
    """Resolve the verification row for status polling (with sibling + pull fallback)."""
    from api.database import IsHumanVerification

    record = db.query(IsHumanVerification).filter_by(session_id=session_id).first()
    if not record:
        return None

    if record.status != "verified" or not record.credential_id:
        sibling = None
        if record.provider_session_id:
            sibling = (
                db.query(IsHumanVerification)
                .filter(
                    IsHumanVerification.provider_session_id == record.provider_session_id,
                    IsHumanVerification.status == "verified",
                    IsHumanVerification.credential_id.isnot(None),
                )
                .order_by(IsHumanVerification.verified_at.desc())
                .first()
            )
        if not sibling and record.wallet_id:
            sibling = (
                db.query(IsHumanVerification)
                .filter(
                    IsHumanVerification.wallet_id == record.wallet_id,
                    IsHumanVerification.status == "verified",
                    IsHumanVerification.credential_id.isnot(None),
                )
                .order_by(IsHumanVerification.verified_at.desc())
                .first()
            )
        if sibling:
            record = sibling

    if record.status != "verified" or not record.credential_id:
        try:
            _maybe_pull_issue_didit(db, record)
        except Exception:
            logger.exception("Pull-fallback attempt errored (non-fatal)")

    return record


def _reissue_verification_credential(record, db) -> Optional[dict]:
    """Re-issue the master credential for wallet storage (stable credential id)."""
    if record.status != "verified" or not record.credential_id or not record.ppid:
        return None
    meta = record.metadata_json or {}
    ppid_deriv = meta.get("ppid_derivation") or (
        "person_root_v1" if record.lemma_person_id else None
    )
    credential = _issue_ishuman_credential(
        record.ppid,
        record.wallet_id,
        ppid_derivation=ppid_deriv,
        verification_method=(record.issuer_id or "didit"),
        ttl_seconds=_master_credential_ttl_seconds(
            _document_expiration_date_from_record(record, db),
        ),
    )
    credential["id"] = record.credential_id
    return credential


@ishuman_bp.route("/api/ishuman/verification-status/<session_id>", methods=["GET"])
@cross_origin()
def verification_status(session_id: str):
    """Poll verification status (no credential, use POST .../claim with wallet_assertion).

    Returns ``credential_ready: true`` when verified so the wallet can claim the
    master VC without exposing it to unauthenticated callers.
    """
    from api.database import SessionLocal
    from api.rate_limiter import check_rate_limit

    session_id = (session_id or "").strip()
    if not session_id:
        return jsonify({"success": False, "error": "session_id required"}), 400

    if not check_rate_limit(f"ishuman_status_poll:{session_id}", 120, 3600):
        return jsonify({"success": False, "error": "status_poll_rate_limited"}), 429

    db = SessionLocal()
    try:
        record = _resolve_verification_status_record(db, session_id)
        if not record:
            return jsonify({"success": False, "error": "session_not_found"}), 404

        resp: dict = {
            "success": True,
            "status": record.status,
            "session_id": record.session_id,
            "credential_ready": bool(
                record.status == "verified" and record.credential_id and record.ppid
            ),
        }
        return jsonify(resp)
    finally:
        db.close()


@ishuman_bp.route("/api/ishuman/verification-status/<session_id>/claim", methods=["POST"])
@cross_origin()
def verification_status_claim(session_id: str):
    """Claim the master credential after IDV (wallet_assertion required).

    Body::

        {
            "wallet_id": "...",
            "wallet_assertion": { "nonce": "...", "signature": "..." }
        }

    The assertion must sign ``session_id`` (and ``wallet_id`` must match the row).
    """
    from api.database import SessionLocal
    from api.rate_limiter import check_rate_limit

    session_id = (session_id or "").strip()
    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    if not session_id or not wallet_id:
        return jsonify({"success": False, "error": "session_id and wallet_id required"}), 400

    body["session_id"] = session_id
    err, _wid = _require_wallet_assertion(body, field_names=["session_id"])
    if err:
        return err

    if not check_rate_limit(f"ishuman_status_claim:{wallet_id}", 30, 3600):
        return jsonify({"success": False, "error": "status_claim_rate_limited"}), 429

    db = SessionLocal()
    try:
        record = _resolve_verification_status_record(db, session_id)
        if not record:
            return jsonify({"success": False, "error": "session_not_found"}), 404
        if str(record.wallet_id or "").strip() != wallet_id:
            return jsonify({"success": False, "error": "wallet_session_mismatch"}), 403
        if record.status != "verified" or not record.credential_id:
            return jsonify({
                "success": True,
                "status": record.status,
                "session_id": record.session_id,
                "credential_ready": False,
            })

        try:
            credential = _reissue_verification_credential(record, db)
        except Exception:
            logger.exception("Failed to re-issue credential for claim")
            return jsonify({"success": False, "error": "credential_reissue_failed"}), 500

        if not credential:
            return jsonify({"success": False, "error": "credential_not_ready"}), 404

        resp = {
            "success": True,
            "status": record.status,
            "session_id": record.session_id,
            "credential_id": record.credential_id,
            "ppid": record.ppid,
            "credential": credential,
        }
        if record.lemma_person_id:
            resp["lemma_person_id"] = record.lemma_person_id
        return jsonify(resp)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2c. Right-to-erasure (wallet owner permanently deletes their lemma.id)
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/erase", methods=["POST"])
@cross_origin()
def erase_identity():
    """Permanently erase the caller's lemma.id (right-to-erasure).

    Auth: a fresh wallet_assertion proving control of the wallet's signing key.

    Effect (irreversible):
      * Revokes the wallet's master + derived credentials network-wide so every
        relying site enforces it via the Bloom snapshot.
      * Scrubs and tombstones the wallet's verification rows (drops document /
        person linkage, PPIDs, and sealed seed envelopes).
      * Removes the wallet -> person binding.
      * If no other wallet remains bound to the person, deletes the person root
        and its document-root mappings so the underlying identity anchor, the
        single value from which every site PPID is derivable, is destroyed.

    This is the server-side counterpart to the client 'Clear my lemma.id' (which
    only wipes browser storage) and satisfies erasure obligations for the
    IDV-derived identity data Lemma holds.
    """
    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    err, _wid = _require_wallet_assertion(body, field_names=["wallet_id"])
    if err:
        return err[0].get_json(), err[1]

    from api.database import (
        SessionLocal, IsHumanVerification, LemmaWalletBinding,
        LemmaPerson, LemmaDocumentRoot,
    )

    db = SessionLocal()
    try:
        # 1) Network-wide revocation first (safe direction; continue even if
        #    there is nothing to revoke).
        revoked = {"revoked_credential_ids": []}
        try:
            revoked = revoke_wallet_network_wide(
                db,
                wallet_id=wallet_id,
                reason="user_erasure",
                revoked_by="wallet_owner",
            )
        except ValueError:
            pass

        from api.ppid_convergence import purge_convergence_for_wallet

        purge_convergence_for_wallet(db, wallet_id)

        # 2) Identify every person this wallet is linked to.
        person_ids: set[str] = set()
        for b in db.query(LemmaWalletBinding).filter_by(wallet_id=wallet_id).all():
            if b.lemma_person_id:
                person_ids.add(b.lemma_person_id)
        for v in db.query(IsHumanVerification).filter_by(wallet_id=wallet_id).all():
            if v.lemma_person_id:
                person_ids.add(v.lemma_person_id)

        # 3) Scrub + tombstone the wallet's verification rows.
        scrubbed = 0
        for v in db.query(IsHumanVerification).filter_by(wallet_id=wallet_id).all():
            v.status = "erased"
            v.document_root_hash = None
            v.lemma_person_id = None
            v.ppid = None
            v.credential_id = None
            v.wallet_seed_envelope = None
            v.person_root_proxy_envelope = None
            v.seed_version = None
            if hasattr(v, "provider_session_id_hash"):
                v.provider_session_id_hash = None
            if hasattr(v, "provider_session_id"):
                v.provider_session_id = None
            if hasattr(v, "stripe_session_id"):
                v.stripe_session_id = None
            v.metadata_json = {"erased": True, "erased_at": datetime.utcnow().isoformat()}
            scrubbed += 1

        # 4) Remove the wallet -> person binding.
        db.query(LemmaWalletBinding).filter_by(wallet_id=wallet_id).delete()

        # 5) Destroy the person anchor only when no other wallet still depends
        #    on it (a person may legitimately have multiple devices/wallets).
        persons_deleted = 0
        for pid in person_ids:
            remaining = (
                db.query(LemmaWalletBinding)
                .filter(LemmaWalletBinding.lemma_person_id == pid)
                .count()
            )
            if remaining == 0:
                db.query(LemmaDocumentRoot).filter_by(lemma_person_id=pid).delete()
                db.query(LemmaPerson).filter_by(person_id=pid).delete()
                persons_deleted += 1

        db.commit()

        logger.info(
            "isHuman erasure complete for wallet=%s (scrubbed=%d persons_deleted=%d revoked=%d)",
            wallet_id[:20], scrubbed, persons_deleted,
            len(revoked.get("revoked_credential_ids", [])),
        )
        return jsonify({
            "success": True,
            "wallet_id": wallet_id,
            "revoked_credential_ids": revoked.get("revoked_credential_ids", []),
            "verifications_scrubbed": scrubbed,
            "persons_deleted": persons_deleted,
        })
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("isHuman erasure failed for wallet %s", wallet_id)
        return jsonify({"success": False, "error": f"erase_failed:{exc}"}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3. Site-Block (first tier revocation)
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/site-block", methods=["POST"])
@cross_origin()
def site_block():
    """Block a PPID on a specific site.

    Requires the site's API key.  The block is immediate and site-scoped.
    The PPID is unaffected on all other sites.

    Request body::

        {
            "ppid": "did:lemma:ppid_...",
            "reason": "Terms violation, automated activity detected"
        }
    """
    site = _require_site_api_key()
    if not site:
        return jsonify({"success": False, "error": "valid API key required"}), 401

    body = request.get_json(silent=True) or {}
    ppid = body.get("ppid")
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    reason = body.get("reason", "")

    from api.database import SessionLocal
    from api.site_ppid_revocation import revoke_site_bound_ppid

    db = SessionLocal()
    try:
        result = revoke_site_bound_ppid(
            db,
            site_id=site.site_id,
            ppid=ppid,
            reason=reason,
            revoked_by=site.admin_email or "site_api",
            site_domain=getattr(site, "site_domain", None),
            blocked_by=site.admin_email,
        )

        logger.info(
            "Site block created: site=%s ppid=%s reason=%s",
            site.site_id, ppid[:40], reason[:80],
        )

        message = "PPID blocked on this site"
        if not result.get("block_created") and not result.get("revocation_created"):
            message = "PPID already blocked on this site"

        return jsonify({
            "success": True,
            "message": message,
            "block_id": result.get("block_id"),
            "site_id": site.site_id,
            "ppid": ppid,
            "revocation_synced": result.get("event_published", False),
        })
    except Exception:
        db.rollback()
        logger.exception("Failed to create site block")
        return jsonify({"success": False, "error": "block_creation_failed"}), 500
    finally:
        db.close()


@ishuman_bp.route("/api/ishuman/site-unblock", methods=["POST"])
@cross_origin()
def site_unblock():
    """Remove a site-scoped PPID block.

    Request body::

        { "ppid": "did:lemma:ppid_..." }
    """
    site = _require_site_api_key()
    if not site:
        return jsonify({"success": False, "error": "valid API key required"}), 401

    body = request.get_json(silent=True) or {}
    ppid = body.get("ppid")
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    from api.database import SessionLocal
    from api.site_ppid_revocation import clear_site_bound_ppid
    db = SessionLocal()
    try:
        result = clear_site_bound_ppid(
            db, site_id=site.site_id, ppid=ppid,
            cleared_by=site.admin_email or "site_api",
        )
        if not result.get("lifted"):
            return jsonify({"success": False, "error": "no active block found"}), 404
        return jsonify({"success": True, "message": "Block removed"})
    except Exception:
        db.rollback()
        logger.exception("Failed to remove site block")
        return jsonify({"success": False, "error": "unblock_failed"}), 500
    finally:
        db.close()


@ishuman_bp.route("/api/ishuman/site-doubt", methods=["POST"])
@cross_origin()
def site_doubt():
    """Require a fresh IDV for one site PPID without banning it."""
    site = _require_site_api_key()
    if not site:
        return jsonify({"success": False, "error": "valid API key required"}), 401
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    from api.database import SessionLocal, SiteDoubt
    db = SessionLocal()
    try:
        row = db.query(SiteDoubt).filter_by(site_id=site.site_id, ppid=ppid).first()
        if not row:
            row = SiteDoubt(site_id=site.site_id, ppid=ppid)
            db.add(row)
        row.reason = (body.get("reason") or "").strip()
        row.requested_by = site.admin_email or "site_api"
        row.requested_at = datetime.utcnow()
        row.is_active = True
        row.cleared_at = None
        row.cleared_by = None
        db.commit()
        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "ppid": ppid,
            "doubt_required": True,
            "requested_at": row.requested_at.isoformat(),
        })
    finally:
        db.close()


@ishuman_bp.route("/api/ishuman/site-doubt-clear", methods=["POST"])
@cross_origin()
def site_doubt_clear():
    """Explicitly clear a temporary doubt; site blocks are untouched."""
    site = _require_site_api_key()
    if not site:
        return jsonify({"success": False, "error": "valid API key required"}), 401
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400
    from api.database import SessionLocal, SiteDoubt
    db = SessionLocal()
    try:
        row = db.query(SiteDoubt).filter_by(site_id=site.site_id, ppid=ppid, is_active=True).first()
        if not row:
            return jsonify({"success": False, "error": "no active doubt found"}), 404
        row.is_active = False
        row.cleared_at = datetime.utcnow()
        row.cleared_by = site.admin_email or "site_api"
        db.commit()
        return jsonify({"success": True, "doubt_required": False})
    finally:
        db.close()


@ishuman_bp.route("/api/ishuman/site-doubts", methods=["GET"])
@cross_origin()
def site_doubts():
    """List active doubt requirements for the authenticated site."""
    site = _require_site_api_key()
    if not site:
        return jsonify({"success": False, "error": "valid API key required"}), 401
    from api.database import SessionLocal, SiteDoubt
    db = SessionLocal()
    try:
        rows = db.query(SiteDoubt).filter_by(site_id=site.site_id, is_active=True).order_by(
            SiteDoubt.requested_at.desc()
        ).all()
        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "doubts": [{
                "ppid": row.ppid,
                "reason": row.reason,
                "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            } for row in rows],
            "count": len(rows),
        })
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Network Revocation (second tier: evidence required)
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/network-revoke", methods=["POST"])
@cross_origin()
def network_revoke():
    """Request network-wide revocation of an isHuman credential.

    This queues the request for review.  The credential is NOT revoked
    immediately, only the site block (tier 1) takes effect right away.

    Request body::

        {
            "ppid": "did:lemma:ppid_...",
            "credential_id": "ishuman_...",
            "reason": "Confirmed bot, scripted form submissions",
            "evidence_url": "https://..."
        }
    """
    return jsonify({
        "success": False,
        "error": "network_revocation_retired",
        "message": "Use site-block for persistent site-scoped enforcement.",
    }), 410


# ---------------------------------------------------------------------------
# 5. Check: is a PPID blocked on a site?
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/check", methods=["GET"])
@cross_origin()
def check_ppid():
    """Check if a PPID is blocked on a specific site (site API key required).

    Query params::

        ?ppid=did:lemma:ppid_...&site_id=site_...

    Enforcement uses site-scoped database policy only: ``SiteBlock``,
    ``SiteDoubt``, and site-bound ``RevocationList`` rows. The Bloom filter is
    not consulted for site-block decisions on this endpoint.
    """
    from api.rate_limiter import check_rate_limit

    site = _require_site_api_key()
    if not site:
        return jsonify({"success": False, "error": "valid API key required"}), 401

    ppid = request.args.get("ppid")
    requested_site_id = (request.args.get("site_id") or "").strip()
    if requested_site_id and requested_site_id != site.site_id:
        return jsonify({"success": False, "error": "site_id_mismatch"}), 403
    site_id = site.site_id

    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    ip_hash = _client_ip_hash()
    if not check_rate_limit(f"ishuman_check:{site.site_id}:{ip_hash}", 120, 3600):
        return jsonify({"success": False, "error": "check_rate_limited"}), 429

    result = {
        "success": True, "ppid": ppid, "blocked": False,
        "doubt_required": False, "reason": None,
    }

    # Check site-specific block
    if site_id:
        from api.database import SessionLocal, SiteBlock, SiteDoubt
        db = SessionLocal()
        try:
            block = (
                db.query(SiteBlock)
                .filter_by(site_id=site_id, ppid=ppid, is_active=True)
                .first()
            )
            if block:
                result["blocked"] = True
                result["reason"] = "site_block"
                result["blocked_at"] = block.blocked_at.isoformat() if block.blocked_at else None
            doubt = db.query(SiteDoubt).filter_by(
                site_id=site_id, ppid=ppid, is_active=True,
            ).first()
            if doubt:
                result["doubt_required"] = True
                result["doubt_reason"] = doubt.reason
        finally:
            db.close()

    # Canonical site-user revocation rows (DB source of truth; complements Bloom)
    if not result["blocked"]:
        from api.database import SessionLocal, RevocationList
        db = SessionLocal()
        try:
            revoke_query = db.query(RevocationList).filter_by(
                ppid=ppid,
                revocation_type="user",
            )
            if site_id:
                revoke_query = revoke_query.filter_by(site_id=site_id)
            user_revoke = revoke_query.first()
            if user_revoke:
                result["blocked"] = True
                result["reason"] = "site_ppid_revoked"
        finally:
            db.close()

    return jsonify(result)


# ---------------------------------------------------------------------------
# 6. Site block list: sites can fetch their full block list
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/site-blocks", methods=["GET"])
@cross_origin()
def list_site_blocks():
    """Return all active PPID blocks for the authenticated site."""
    site = _require_site_api_key()
    if not site:
        return jsonify({"success": False, "error": "valid API key required"}), 401

    from api.database import SessionLocal, SiteBlock
    db = SessionLocal()
    try:
        blocks = (
            db.query(SiteBlock)
            .filter_by(site_id=site.site_id, is_active=True)
            .order_by(SiteBlock.blocked_at.desc())
            .all()
        )

        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "blocks": [
                {
                    "ppid": b.ppid,
                    "reason": b.reason,
                    "blocked_at": b.blocked_at.isoformat() if b.blocked_at else None,
                }
                for b in blocks
            ],
            "count": len(blocks),
        })
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 7. Platform stats (public)
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/stats", methods=["GET"])
@cross_origin()
def ishuman_stats():
    """Public platform statistics for isHuman."""
    from api.database import SessionLocal, IsHumanVerification, SiteBlock
    db = SessionLocal()
    try:
        total_verifications = db.query(IsHumanVerification).filter_by(status="verified").count()
        active_blocks = db.query(SiteBlock).filter_by(is_active=True).count()
        return jsonify({
            "success": True,
            "network": "isHuman",
            "total_verifications": total_verifications,
            "active_site_blocks": active_blocks,
            "credential_ttl_days": ISHUMAN_CREDENTIAL_TTL_DAYS,
            "verification_cost_usd": STRIPE_IDENTITY_COST_CENTS / 100,
        })
    except Exception as exc:
        logger.warning("Stats query failed: %s", exc)
        return jsonify({"success": True, "network": "isHuman", "total_verifications": 0})
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 8. Derive per-site proof (called by the wallet bridge on first visit)
# ---------------------------------------------------------------------------


def _bill_site_credential_event(
    db,
    *,
    target_site: str,
    ppid: str,
    credential_id: str,
    issue_mode: Optional[str] = None,
    is_cached_reissue: bool = False,
) -> None:
    """Classify and record a billable site-credential event (issuance / MAU / doubt)."""
    if not ppid or not credential_id:
        return
    from billing.credential_billing import record_credential_billing_event

    record_credential_billing_event(
        db,
        target_site=target_site,
        ppid=ppid,
        credential_id=credential_id,
        issue_mode=issue_mode,
        is_cached_reissue=is_cached_reissue,
    )


def _jsonify_site_proof(
    *,
    credential: dict,
    cached: bool,
    ppid_convergence: Optional[dict] = None,
) -> "flask.Response":
    body = {"success": True, "credential": credential, "cached": cached}
    if ppid_convergence:
        body["ppid_convergence"] = ppid_convergence
    return jsonify(body)


def _finalize_site_proof_response(
    db,
    *,
    credential: dict,
    cached: bool,
    wallet_id: str,
    target_site: str,
    canonical_person_id: Optional[str],
) -> "flask.Response":
    ppid_convergence = None
    if canonical_person_id:
        from api.ppid_convergence import issue_ppid_convergence_for_site

        ppid_convergence = issue_ppid_convergence_for_site(
            db,
            wallet_id=wallet_id,
            target_site=target_site,
            canonical_ppid=credential.get("subject") or "",
            canonical_person_id=canonical_person_id,
        )
    db.commit()
    return _jsonify_site_proof(
        credential=credential,
        cached=cached,
        ppid_convergence=ppid_convergence,
    )


@ishuman_bp.route("/api/ishuman/derive-site-proof", methods=["POST"])
@cross_origin()
def derive_site_proof():
    """Derive a per-site isHuman credential from the master proof.

    Called by the wallet bridge when a site requests an isHuman
    credential and no per-site derivation exists yet.

    Request body::

        {
            "master_credential_id": "ishuman_master_...",
            "wallet_id": "...",
            "target_site": "example.com"
        }

    The server:
    1. Verifies the master credential is valid (exists, not revoked, not expired)
    2. Derives the site-specific PPID
    3. Issues a new credential signed by the platform issuer
    4. Returns the per-site credential for the bridge to store
    """
    body = request.get_json(silent=True) or {}
    rejected = _reject_wallet_secret_payload(body)
    if rejected:
        return rejected

    # v2 (Phase 1.2): master_credential_id is now an OPTIONAL hint. When absent
    # we fall back to the wallet's latest verified record, so a wallet that lost
    # its local master copy can still derive site proofs.
    master_credential_id = (body.get("master_credential_id") or "").strip()
    wallet_id = body.get("wallet_id")
    target_site = body.get("target_site")
    site_signing_pubkey_raw = (body.get("site_signing_pubkey") or "").strip()
    issue_mode = (body.get("issue_mode") or "site_proof").strip().lower()
    if issue_mode not in {"site_proof", "fresh_idv"}:
        return jsonify({"success": False, "error": "invalid_issue_mode"}), 400
    body["issue_mode"] = issue_mode

    required_assurance = (body.get("required_assurance") or "ishuman").strip().lower()
    if required_assurance not in {"passkey", "ishuman"}:
        return jsonify({"success": False, "error": "invalid_required_assurance"}), 400
    if issue_mode == "fresh_idv":
        required_assurance = "ishuman"
    body["required_assurance"] = required_assurance

    if not wallet_id or not target_site:
        return jsonify({
            "success": False,
            "error": "wallet_id and target_site required",
        }), 400
    try:
        site_signing_pubkey = _normalize_site_signing_pubkey(site_signing_pubkey_raw)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    # Bind master_credential_id into the signed assertion only when supplied so
    # the wallet and server agree on the signed field set in both modes.
    assertion_fields = ["target_site", "site_signing_pubkey", "issue_mode"]
    if required_assurance == "passkey":
        assertion_fields.append("required_assurance")
    if master_credential_id:
        assertion_fields = ["master_credential_id"] + assertion_fields
    err, _wid = _require_wallet_assertion(
        body,
        field_names=assertion_fields,
    )
    if err:
        return err

    from api.ppid import canonicalize_rp_id
    target_site = canonicalize_rp_id(target_site)

    if not target_site or target_site == "unknown":
        return jsonify({"success": False, "error": "invalid target_site"}), 400

    from api.rate_limiter import check_rate_limit

    ip_hash = _client_ip_hash()
    if not check_rate_limit(f"derive_site_proof:wallet:{wallet_id}", 10, 60):
        return jsonify({"success": False, "error": "derive_site_proof_rate_limited"}), 429
    if not check_rate_limit(f"derive_site_proof:ip_host:{ip_hash}:{target_site}", 60, 60):
        return jsonify({"success": False, "error": "derive_site_proof_rate_limited"}), 429

    from api.database import SessionLocal, IsHumanVerification, RevocationList
    db = SessionLocal()
    try:
        # 1. Resolve the master credential. Prefer the body's hint; otherwise
        #    fall back to the wallet's latest verified record (Phase 1.2).
        master = None
        if master_credential_id:
            master_query = (
                db.query(IsHumanVerification)
                .filter_by(credential_id=master_credential_id, wallet_id=wallet_id, status="verified")
            )
            if issue_mode == "fresh_idv" and hasattr(master_query, "with_for_update"):
                master_query = master_query.with_for_update()
            master = master_query.first()
        if not master:
            master_query = (
                db.query(IsHumanVerification)
                .filter_by(wallet_id=wallet_id, status="verified")
                .order_by(IsHumanVerification.verified_at.desc())
            )
            if issue_mode == "fresh_idv" and hasattr(master_query, "with_for_update"):
                master_query = master_query.with_for_update()
            master = master_query.first()
        if not master:
            from api.config import passkey_assurance_enabled

            if passkey_assurance_enabled():
                person_id = _resolve_person_id_for_wallet(db, wallet_id)
                if not person_id:
                    try:
                        from api.identity_person import ensure_provisional_person_for_wallet

                        person_id = ensure_provisional_person_for_wallet(db, wallet_id=wallet_id)
                        db.commit()
                    except Exception as exc:
                        db.rollback()
                        logger.exception("Failed to ensure provisional person for passkey proof")
                        return jsonify({
                            "success": False,
                            "error": "provisional_person_failed",
                            "message": str(exc),
                        }), 500
                deny_reason = _deny_if_derivation_revoked(
                    db,
                    master_credential_id="",
                    wallet_id=wallet_id,
                    target_site=target_site,
                    lemma_person_id=person_id,
                )
                if deny_reason:
                    return jsonify({"success": False, "error": deny_reason}), 403

                from billing.billing_access import check_site_billing_allows_issuance

                billing_deny = check_site_billing_allows_issuance(db, target_site)
                if billing_deny:
                    return jsonify({
                        "success": False,
                        "error": billing_deny,
                        "message": "Site billing is inactive. Update payment method in developer billing.",
                    }), 402

                site_ppid = _derive_ppid_for_site(
                    rp_id=target_site,
                    wallet_id=wallet_id,
                    lemma_person_id=person_id,
                    db=db,
                )
                credential = _issue_ishuman_credential(
                    site_ppid,
                    wallet_id,
                    site_id=target_site,
                    site_signing_pubkey=site_signing_pubkey or None,
                    ppid_derivation="person_root_v1",
                    verification_method="passkey",
                    assurance="passkey",
                )
                _bill_site_credential_event(
                    db,
                    target_site=target_site,
                    ppid=site_ppid,
                    credential_id=credential["id"],
                    issue_mode=issue_mode,
                    is_cached_reissue=False,
                )
                return _finalize_site_proof_response(
                    db,
                    credential=credential,
                    cached=False,
                    wallet_id=wallet_id,
                    target_site=target_site,
                    canonical_person_id=person_id,
                )

            return jsonify({"success": False, "error": "wallet_not_verified"}), 403

        # A client label alone must never clear a doubt. Fresh mode is accepted
        # only immediately after a server-recorded successful IDV ceremony.
        if issue_mode == "fresh_idv":
            verified_at = getattr(master, "verified_at", None)
            master_metadata = dict(getattr(master, "metadata_json", None) or {})
            if (
                not verified_at
                or datetime.utcnow() - verified_at > timedelta(minutes=15)
                or master_metadata.get("fresh_idv_site") != target_site
                or master_metadata.get("fresh_idv_consumed") is True
            ):
                return jsonify({"success": False, "error": "fresh_idv_required"}), 403

        # Bind the resolved credential id for the rest of the flow (revocation
        # checks, derived-credential mapping) regardless of how it was found.
        master_credential_id = master.credential_id

        if master.expires_at and master.expires_at < datetime.utcnow():
            return jsonify({"success": False, "error": "master_credential_expired"}), 403

        # Check wallet-level revocation
        wallet_revoked = (
            db.query(RevocationList)
            .filter_by(wallet_id=wallet_id, revocation_type="wallet")
            .first()
        )
        if wallet_revoked:
            return jsonify({"success": False, "error": "wallet_revoked"}), 403

        person_id = getattr(master, "lemma_person_id", None)
        if not person_id:
            # Legacy masters may predate the person_id column; resolve the
            # canonical identity from the wallet binding so derivation stays on
            # the person-root path instead of falling back to wallet-secret.
            person_id = _resolve_person_id_for_wallet(db, wallet_id)

        deny_reason = _deny_if_derivation_revoked(
            db,
            master_credential_id=master_credential_id,
            wallet_id=wallet_id,
            target_site=target_site,
            lemma_person_id=person_id,
        )
        if deny_reason:
            return jsonify({"success": False, "error": deny_reason}), 403

        from billing.billing_access import check_site_billing_allows_issuance

        billing_deny = check_site_billing_allows_issuance(db, target_site)
        if billing_deny:
            return jsonify({
                "success": False,
                "error": billing_deny,
                "message": "Site billing is inactive. Update payment method in developer billing.",
            }), 402

        ppid_derivation = "person_root_v1" if person_id else None

        # Derive the deterministic site PPID.  No person/wallet-to-site row is
        # stored; every renewal receives a fresh random credential id.
        site_ppid = _derive_ppid_for_site(
            rp_id=target_site,
            wallet_id=wallet_id,
            lemma_person_id=person_id,
            db=db,
        )

        # Issue the short-lived per-site credential. Passkey-only policy must not
        # disclose latent IDV even when a verified master exists.
        if required_assurance == "passkey":
            from api.config import passkey_assurance_enabled

            if not passkey_assurance_enabled():
                return jsonify({"success": False, "error": "passkey_assurance_disabled"}), 403
            credential = _issue_ishuman_credential(
                site_ppid,
                wallet_id,
                site_id=target_site,
                site_signing_pubkey=site_signing_pubkey or None,
                ppid_derivation=ppid_derivation,
                verification_method="passkey",
                assurance="passkey",
            )
            logger.info("Issued passkey-tier site proof (minimum disclosure)")
        else:
            credential = _issue_ishuman_credential(
                site_ppid,
                wallet_id,
                site_id=target_site,
                site_signing_pubkey=site_signing_pubkey or None,
                ppid_derivation=ppid_derivation,
                verification_method=(getattr(master, "issuer_id", None) or "didit"),
                assurance="ishuman",
            )
            logger.info("Issued privacy-minimized site proof")

        if issue_mode == "fresh_idv":
            master_metadata["fresh_idv_consumed"] = True
            master.metadata_json = master_metadata

        _bill_site_credential_event(
            db,
            target_site=target_site,
            ppid=site_ppid,
            credential_id=credential["id"],
            issue_mode=issue_mode,
            is_cached_reissue=False,
        )
        return _finalize_site_proof_response(
            db,
            credential=credential,
            cached=False,
            wallet_id=wallet_id,
            target_site=target_site,
            canonical_person_id=person_id,
        )

    except Exception:
        db.rollback()
        logger.exception("Failed to derive site proof")
        return jsonify({"success": False, "error": "derivation_failed"}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 8a. Reissue a fresh master credential for an already-verified wallet
# ---------------------------------------------------------------------------


def _reissue_limit_per_day() -> int:
    try:
        return max(1, int(os.getenv("LEMMA_ISHUMAN_REISSUE_LIMIT_PER_DAY", "5")))
    except (TypeError, ValueError):
        return 5


@ishuman_bp.route("/api/ishuman/reissue-master", methods=["POST"])
@cross_origin()
def reissue_master_credential():
    """Reissue a fresh master credential for an already-verified wallet.

    Auth: a wallet_assertion proving possession of the wallet's signing key.
    No fresh IDV required, the wallet was already verified, we just hand back
    a freshly signed master. The previously issued master id is revoked so a
    leaked local copy cannot be replayed.

    Body: ``{ wallet_id, wallet_assertion: { nonce, signature } }``
    Returns: ``{ success: true, credential: <new master VC>, old_credential_id }``
    """
    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    err, _wid = _require_wallet_assertion(body, field_names=["wallet_id"])
    if err:
        return err

    from api.wallet_authn import count_active_wallet_devices

    primary_assertion = body.get("wallet_assertion") if isinstance(body.get("wallet_assertion"), dict) else {}
    primary_device_id = str(body.get("device_id") or primary_assertion.get("device_id") or "").strip()
    if count_active_wallet_devices(wallet_id) > 1:
        second_assertion = body.get("second_factor_assertion")
        if not isinstance(second_assertion, dict):
            return jsonify({
                "success": False,
                "error": "second_factor_required",
                "code": "second_factor_required",
            }), 403
        second_body = {
            "wallet_id": wallet_id,
            "device_id": str(body.get("second_device_id") or second_assertion.get("device_id") or "").strip(),
            "wallet_assertion": second_assertion,
        }
        err2, _ = _require_wallet_assertion(second_body, field_names=["wallet_id"])
        if err2:
            return err2
        second_device_id = str(second_body.get("device_id") or second_assertion.get("device_id") or "").strip()
        if second_device_id and primary_device_id and second_device_id == primary_device_id:
            return jsonify({
                "success": False,
                "error": "second_factor_same_device",
                "code": "second_factor_same_device",
            }), 403

    # Per-wallet/day rate limit (env-tunable). Checked at call time so the
    # limit can be tuned per deploy and exercised deterministically in tests.
    from api.rate_limiter import check_rate_limit

    if not check_rate_limit(f"ishuman_reissue:{wallet_id}", _reissue_limit_per_day(), 86400):
        return jsonify({"success": False, "error": "reissue_rate_limited"}), 429

    from api.database import SessionLocal, IsHumanVerification, RevocationList
    from api.bloom_snapshot import invalidate_bloom_filter_cache

    db = SessionLocal()
    try:
        verified = (
            db.query(IsHumanVerification)
            .filter_by(wallet_id=wallet_id, status="verified")
            .order_by(IsHumanVerification.verified_at.desc())
            .first()
        )
        if not verified:
            return jsonify({"success": False, "error": "wallet_not_verified"}), 404

        old_id = verified.credential_id
        ppid_derivation = (verified.metadata_json or {}).get("ppid_derivation")
        new_credential = _issue_ishuman_credential(
            verified.ppid,
            wallet_id,
            ppid_derivation=ppid_derivation,
            verification_method=(verified.issuer_id or "didit"),
            ttl_seconds=_master_credential_ttl_seconds(
                _document_expiration_date_from_record(verified, db),
            ),
        )
        verified.credential_id = new_credential["id"]
        verified.metadata_json = {
            **(verified.metadata_json or {}),
            "reissued_from": old_id,
            "reissued_at": int(time.time()),
        }

        # Revoke the superseded master id so leaked copies cannot be replayed.
        if old_id and old_id != new_credential["id"]:
            db.add(RevocationList(
                lemma_id=old_id,
                credential_id=old_id,
                lemma_type="ishuman",
                revocation_type="credential",
                revoked_by="reissue_master",
                reason="superseded by reissue",
            ))
        db.commit()
        invalidate_bloom_filter_cache()

        logger.info("Reissued master for wallet=%s old=%s new=%s",
                    wallet_id, str(old_id)[:30], str(new_credential["id"])[:30])
        return jsonify({
            "success": True,
            "credential": new_credential,
            "old_credential_id": old_id,
        })
    except Exception:
        db.rollback()
        logger.exception("Failed to reissue master credential")
        return jsonify({"success": False, "error": "reissue_failed"}), 500
    finally:
        db.close()


@ishuman_bp.route("/api/ishuman/seed-envelope", methods=["POST"])
@cross_origin()
def get_seed_envelope():
    """Return the wallet's sealed person-root seed envelopes (Phase 1.1).

    Auth: a wallet_assertion proving possession of the wallet's signing key.
    The envelopes are sealed to the X25519 pubkey the wallet posted at IDV
    start; only that wallet can open them. Returns base64url ciphertext only.

    Body: ``{ wallet_id, wallet_assertion: { nonce, signature } }``
    """
    from api.seed_envelope import use_person_root_seeds_enabled

    if not use_person_root_seeds_enabled():
        return jsonify({"success": False, "error": "seed_envelopes_disabled"}), 404

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    err, _wid = _require_wallet_assertion(body, field_names=["wallet_id"])
    if err:
        return err

    from api.database import SessionLocal, IsHumanVerification

    db = SessionLocal()
    try:
        verified = (
            db.query(IsHumanVerification)
            .filter_by(wallet_id=wallet_id, status="verified")
            .order_by(IsHumanVerification.verified_at.desc())
            .first()
        )
        if not verified:
            return jsonify({"success": False, "error": "wallet_not_verified"}), 404
        if not verified.wallet_seed_envelope or not verified.person_root_proxy_envelope:
            return jsonify({"success": False, "error": "seed_envelope_unavailable"}), 404

        def _b64(blob) -> str:
            return base64.urlsafe_b64encode(bytes(blob)).decode("ascii").rstrip("=")

        return jsonify({
            "success": True,
            "seed_version": verified.seed_version or "v1",
            "wallet_seed_envelope": _b64(verified.wallet_seed_envelope),
            "person_root_proxy_envelope": _b64(verified.person_root_proxy_envelope),
        })
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 8a. QR-based cross-device wallet transfer relay (Phase 4.2)
# ---------------------------------------------------------------------------

_DEVICE_TRANSFER_TTL_SECONDS = 60


def _device_transfer_key(transfer_id: str) -> str:
    return f"wallet:device-transfer:{transfer_id}"


@ishuman_bp.route("/api/wallet/sync-device", methods=["POST"])
@cross_origin()
def wallet_sync_device():
    """QR-based cross-device wallet transfer relay (Phase 4.2).

    The server never holds plaintext person-root seeds, so it cannot reseal
    envelopes itself. Instead this is a short-lived (60s), one-time *relay*
    keyed by a random ``transfer_id`` that the NEW device proposes, together
    with a transient X25519 public key, in its QR code:

      * ``deposit`` (old device): scans the new device's QR, opens its own
        Phase 1.1 seed envelopes, reseals them to ``new_device_enc_pubkey``,
        and proves wallet ownership with a wallet_assertion signed over both
        ``transfer_id`` and ``new_device_enc_pubkey`` (binding the authorization
        to that specific target key). The server stores only the opaque,
        already-encrypted bundle.
      * ``claim`` (new device): redeems ``transfer_id`` exactly once and opens
        the bundle with its transient private key.

    Body (deposit): ``{ action, wallet_id, transfer_id, new_device_enc_pubkey,
    bundle, wallet_assertion }``
    Body (claim):   ``{ action, transfer_id }``
    """
    from auth.redis_store import consume as redis_consume
    from auth.redis_store import get as redis_get
    from auth.redis_store import store as redis_store

    body = request.get_json(silent=True) or {}
    action = (body.get("action") or "").strip().lower()

    if action == "deposit":
        wallet_id = (body.get("wallet_id") or "").strip()
        transfer_id = (body.get("transfer_id") or "").strip()
        new_device_enc_pubkey = (body.get("new_device_enc_pubkey") or "").strip()
        if not wallet_id or not transfer_id or not new_device_enc_pubkey:
            return jsonify({"success": False, "error": "missing_transfer_fields"}), 400
        if len(transfer_id) < 16:
            return jsonify({"success": False, "error": "weak_transfer_id"}), 400

        # The old device authorizes resealing to THIS new-device key.
        err, _wid = _require_wallet_assertion(
            body, field_names=["transfer_id", "new_device_enc_pubkey"]
        )
        if err:
            return err

        bundle = body.get("bundle")
        if not isinstance(bundle, dict) or not bundle:
            return jsonify({"success": False, "error": "bundle_required"}), 400

        redis_store(
            _device_transfer_key(transfer_id),
            {
                "wallet_id": wallet_id,
                "new_device_enc_pubkey": new_device_enc_pubkey,
                "bundle": bundle,
            },
            ttl_seconds=_DEVICE_TRANSFER_TTL_SECONDS,
        )
        return jsonify({"success": True, "expires_in": _DEVICE_TRANSFER_TTL_SECONDS})

    if action == "claim":
        transfer_id = (body.get("transfer_id") or "").strip()
        if not transfer_id:
            return jsonify({"success": False, "error": "transfer_id required"}), 400
        entry = redis_consume(_device_transfer_key(transfer_id))
        if not entry:
            return jsonify({"success": False, "error": "transfer_not_found"}), 404
        from api.wallet_authn import issue_device_enrollment_grant

        enrollment_grant = issue_device_enrollment_grant(
            wallet_id=entry.get("wallet_id"),
            source="device_transfer_claim",
        )
        return jsonify({
            "success": True,
            "wallet_id": entry.get("wallet_id"),
            "bundle": entry.get("bundle"),
            "enrollment_grant": enrollment_grant,
        })

    return jsonify({"success": False, "error": "unknown_action"}), 400


# ---------------------------------------------------------------------------
# 8a-i. Pull-based device link: receiver shows QR, phone scans & sends
# ---------------------------------------------------------------------------

_LINK_RECEIVE_TTL_SECONDS = 300


def _link_receive_key(transfer_id: str) -> str:
    return f"wallet:link-receive:{transfer_id}"


@ishuman_bp.route("/api/wallet/link-receive", methods=["POST"])
@cross_origin()
def wallet_link_receive():
    """Short-lived relay for device linking (pull and push).

    Pull (empty device shows QR):
      Receiver displays ``/link/send#…`` with a transient X25519 public key.
      Sender deposits a sealed person-root bundle; receiver claims once.

    Push (manager creates QR / transfer link):
      ``offer``, unlocked wallet creates a transfer slot + confirm code
        (QR/link carry only ``transfer_id``, never secrets).
      ``register``, empty device binds its ephemeral pubkey (first writer wins).
      ``status``, sender polls until register, then confirms codes match.
      ``deposit`` / ``claim``, same sealed-bundle handoff as pull.

    Body (deposit): ``{ action, wallet_id, transfer_id, recv_pubkey, bundle,
    wallet_assertion }``
    Body (claim):   ``{ action, transfer_id }``
    """
    from auth.redis_store import consume as redis_consume
    from auth.redis_store import get as redis_get
    from auth.redis_store import store as redis_store

    body = request.get_json(silent=True) or {}
    action = (body.get("action") or "").strip().lower()

    if action == "offer":
        wallet_id = (body.get("wallet_id") or "").strip()
        transfer_id = (body.get("transfer_id") or "").strip()
        confirm_code = (body.get("confirm_code") or "").strip()
        if not wallet_id or not transfer_id or not confirm_code:
            return jsonify({"success": False, "error": "missing_transfer_fields"}), 400
        if len(transfer_id) < 16:
            return jsonify({"success": False, "error": "weak_transfer_id"}), 400
        if not confirm_code.isdigit() or len(confirm_code) != 6:
            return jsonify({"success": False, "error": "invalid_confirm_code"}), 400
        if redis_get(_link_receive_key(transfer_id)):
            return jsonify({"success": False, "error": "transfer_exists"}), 409

        err, _wid = _require_wallet_assertion(
            body, field_names=["transfer_id", "confirm_code"]
        )
        if err:
            return err

        redis_store(
            _link_receive_key(transfer_id),
            {
                "mode": "push",
                "status": "waiting",
                "wallet_id": wallet_id,
                "confirm_code": confirm_code,
            },
            ttl_seconds=_LINK_RECEIVE_TTL_SECONDS,
        )
        return jsonify({"success": True, "expires_in": _LINK_RECEIVE_TTL_SECONDS})

    if action == "register":
        transfer_id = (body.get("transfer_id") or "").strip()
        recv_pubkey = (body.get("recv_pubkey") or "").strip()
        if not transfer_id or not recv_pubkey:
            return jsonify({"success": False, "error": "missing_transfer_fields"}), 400
        if len(transfer_id) < 16:
            return jsonify({"success": False, "error": "weak_transfer_id"}), 400

        entry = redis_get(_link_receive_key(transfer_id))
        if not entry:
            return jsonify({"success": False, "error": "transfer_not_found"}), 404
        if entry.get("bundle"):
            return jsonify({"success": False, "error": "transfer_already_deposited"}), 409
        existing_pub = (entry.get("recv_pubkey") or "").strip()
        if existing_pub:
            if existing_pub == recv_pubkey:
                return jsonify({
                    "success": True,
                    "confirm_code": entry.get("confirm_code"),
                    "status": "registered",
                    "expires_in": _LINK_RECEIVE_TTL_SECONDS,
                })
            return jsonify({"success": False, "error": "transfer_already_registered"}), 409
        if entry.get("mode") != "push" or entry.get("status") != "waiting":
            return jsonify({"success": False, "error": "transfer_not_offer"}), 409

        entry["recv_pubkey"] = recv_pubkey
        entry["status"] = "registered"
        redis_store(
            _link_receive_key(transfer_id),
            entry,
            ttl_seconds=_LINK_RECEIVE_TTL_SECONDS,
        )
        return jsonify({
            "success": True,
            "confirm_code": entry.get("confirm_code"),
            "status": "registered",
            "expires_in": _LINK_RECEIVE_TTL_SECONDS,
        })

    if action == "status":
        transfer_id = (body.get("transfer_id") or "").strip()
        if not transfer_id:
            return jsonify({"success": False, "error": "transfer_id required"}), 400
        entry = redis_get(_link_receive_key(transfer_id))
        if not entry:
            return jsonify({"success": False, "error": "transfer_not_found"}), 404
        return jsonify({
            "success": True,
            "status": entry.get("status") or ("deposited" if entry.get("bundle") else "waiting"),
            "confirm_code": entry.get("confirm_code"),
            "recv_pubkey": entry.get("recv_pubkey") or None,
            "has_bundle": bool(entry.get("bundle")),
        })

    if action == "deposit":
        wallet_id = (body.get("wallet_id") or "").strip()
        transfer_id = (body.get("transfer_id") or "").strip()
        recv_pubkey = (body.get("recv_pubkey") or "").strip()
        if not wallet_id or not transfer_id or not recv_pubkey:
            return jsonify({"success": False, "error": "missing_transfer_fields"}), 400
        if len(transfer_id) < 16:
            return jsonify({"success": False, "error": "weak_transfer_id"}), 400

        err, _wid = _require_wallet_assertion(
            body, field_names=["transfer_id", "recv_pubkey"]
        )
        if err:
            return err

        bundle = body.get("bundle")
        if not isinstance(bundle, dict):
            return jsonify({"success": False, "error": "bundle_required"}), 400
        has_person_root = bool(
            bundle.get("sealed_wallet_seed") and bundle.get("sealed_person_root_proxy")
        )
        if not bundle.get("sealed_link_payload") and not has_person_root:
            return jsonify({"success": False, "error": "bundle_required"}), 400

        existing = redis_get(_link_receive_key(transfer_id))
        if existing:
            if existing.get("bundle"):
                return jsonify({"success": False, "error": "transfer_already_deposited"}), 409
            if existing.get("mode") == "push":
                if existing.get("wallet_id") and existing.get("wallet_id") != wallet_id:
                    return jsonify({"success": False, "error": "wallet_mismatch"}), 403
                offered_pub = (existing.get("recv_pubkey") or "").strip()
                if not offered_pub:
                    return jsonify({"success": False, "error": "receiver_not_registered"}), 409
                if offered_pub != recv_pubkey:
                    return jsonify({"success": False, "error": "pubkey_mismatch"}), 409

        redis_store(
            _link_receive_key(transfer_id),
            {
                "mode": (existing or {}).get("mode") or "pull",
                "status": "deposited",
                "wallet_id": wallet_id,
                "recv_pubkey": recv_pubkey,
                "confirm_code": (existing or {}).get("confirm_code"),
                "bundle": bundle,
            },
            ttl_seconds=_LINK_RECEIVE_TTL_SECONDS,
        )
        return jsonify({"success": True, "expires_in": _LINK_RECEIVE_TTL_SECONDS})

    if action == "claim":
        transfer_id = (body.get("transfer_id") or "").strip()
        if not transfer_id:
            return jsonify({"success": False, "error": "transfer_id required"}), 400
        entry = redis_consume(_link_receive_key(transfer_id))
        if not entry or not entry.get("bundle"):
            return jsonify({"success": False, "error": "transfer_not_found"}), 404
        from api.wallet_authn import issue_device_enrollment_grant

        enrollment_grant = issue_device_enrollment_grant(
            wallet_id=entry.get("wallet_id"),
            source="link_receive_claim",
        )
        return jsonify({
            "success": True,
            "wallet_id": entry.get("wallet_id"),
            "bundle": entry.get("bundle"),
            "enrollment_grant": enrollment_grant,
        })

    return jsonify({"success": False, "error": "unknown_action"}), 400


# ---------------------------------------------------------------------------
# 8a-ii. Silent mobile wallet handoff during Didit IDV return
# ---------------------------------------------------------------------------


@ishuman_bp.route("/api/ishuman/idv-mobile-handoff/deposit", methods=["POST"])
@cross_origin()
def idv_mobile_handoff_deposit():
    """Store an opaque encrypted wallet handoff blob for mobile Didit return.

    Prefer passing ``handoff_id`` + ``encrypted_blob`` to ``start-verification``
    so the handoff is stored atomically with session creation. This endpoint
    remains for backwards-compatible clients.
    """
    from api.config import is_ishuman_idv_mobile_handoff_enabled

    if not is_ishuman_idv_mobile_handoff_enabled():
        return jsonify({"success": False, "error": "mobile_handoff_disabled"}), 404

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    handoff_id = (body.get("handoff_id") or "").strip()
    session_id = (body.get("session_id") or "").strip()
    encrypted_blob = (body.get("encrypted_blob") or "").strip()
    handoff_mk_fingerprint = (body.get("handoff_mk_fingerprint") or "").strip()

    if not wallet_id or not handoff_id or not session_id or not encrypted_blob:
        return jsonify({"success": False, "error": "missing_handoff_fields"}), 400
    if len(handoff_id) < 16:
        return jsonify({"success": False, "error": "weak_handoff_id"}), 400

    from api.config import is_ishuman_idv_handoff_strict_claim_enabled

    if is_ishuman_idv_handoff_strict_claim_enabled() and not handoff_mk_fingerprint:
        return jsonify({"success": False, "error": "missing_handoff_mk_fingerprint"}), 400

    assertion_fields = ["handoff_id", "session_id"]
    if handoff_mk_fingerprint:
        assertion_fields.append("handoff_mk_fingerprint")
    err, _wid = _require_wallet_assertion(
        body, field_names=assertion_fields
    )
    if err:
        return err

    _store_idv_mobile_handoff(
        handoff_id=handoff_id,
        session_id=session_id,
        wallet_id=wallet_id,
        encrypted_blob=encrypted_blob,
        mk_fingerprint=handoff_mk_fingerprint,
    )
    return jsonify({
        "success": True,
        "expires_in": _idv_handoff_ttl_seconds(),
    })


@ishuman_bp.route("/api/ishuman/idv-mobile-handoff/claim", methods=["POST"])
@cross_origin()
def idv_mobile_handoff_claim():
    """One-time claim of a mobile IDV handoff blob (target device has no wallet)."""
    from api.config import (
        is_ishuman_idv_handoff_strict_claim_enabled,
        is_ishuman_idv_mobile_handoff_enabled,
    )
    from api.rate_limiter import check_rate_limit

    if not is_ishuman_idv_mobile_handoff_enabled():
        return jsonify({"success": False, "error": "mobile_handoff_disabled"}), 404

    body = request.get_json(silent=True) or {}
    handoff_id = (body.get("handoff_id") or "").strip()
    session_id = (body.get("session_id") or "").strip()
    mk = str(body.get("mk") or "").strip()
    strict_claim = is_ishuman_idv_handoff_strict_claim_enabled()
    ip_hash = _client_ip_hash()

    if strict_claim:
        if not handoff_id or not session_id or not mk:
            return jsonify({"success": False, "error": "handoff_id_session_id_mk_required"}), 400

        if not check_rate_limit(
            f"ishuman_handoff_claim_ip:{ip_hash}",
            _IDV_HANDOFF_CLAIM_IP_LIMIT,
            _IDV_HANDOFF_CLAIM_IP_WINDOW_SECONDS,
        ):
            _log_handoff_security_event(
                "handoff_claim_rate_limited",
                ip=ip_hash,
                handoff=handoff_id[:24],
            )
            return jsonify({"success": False, "error": "handoff_claim_rate_limited"}), 429

        if _handoff_mk_fail_count(handoff_id) >= _IDV_HANDOFF_MK_FAIL_MAX:
            _log_handoff_security_event(
                "handoff_claim_mk_locked",
                ip=ip_hash,
                handoff=handoff_id[:24],
            )
            return jsonify({"success": False, "error": "handoff_claim_rate_limited"}), 429

        if not check_rate_limit(
            f"ishuman_handoff_claim_id:{handoff_id}",
            _IDV_HANDOFF_CLAIM_HANDOFF_LIMIT,
            _idv_handoff_ttl_seconds(),
        ):
            _log_handoff_security_event(
                "handoff_claim_rate_limited",
                ip=ip_hash,
                handoff=handoff_id[:24],
            )
            return jsonify({"success": False, "error": "handoff_claim_rate_limited"}), 429

        entry = _lookup_idv_mobile_handoff(handoff_id=handoff_id)
    else:
        logger.warning(
            "IDV mobile handoff legacy claim path used handoff=%s session=%s",
            (handoff_id or "")[:24],
            (session_id or "")[:24],
        )
        if not handoff_id and not session_id:
            return jsonify({"success": False, "error": "handoff_id or session_id required"}), 400
        entry = _lookup_idv_mobile_handoff(handoff_id=handoff_id, session_id=session_id)

    if not entry:
        _log_handoff_security_event(
            "handoff_claim_miss",
            ip=ip_hash,
            handoff=(handoff_id or "")[:24],
            session=(session_id or "")[:24],
        )
        return jsonify({"success": False, "error": "handoff_not_found"}), 404

    if strict_claim:
        entry_session_id = str(entry.get("session_id") or "").strip()
        if session_id != entry_session_id:
            _log_handoff_security_event(
                "handoff_claim_session_reconciled",
                ip=ip_hash,
                handoff=(handoff_id or "")[:24],
                session=(session_id or "")[:24],
                entry_session=entry_session_id[:24],
            )
            session_id = entry_session_id

        if not _validate_handoff_mk(mk, entry):
            fail_count = _increment_handoff_mk_fail(handoff_id)
            _log_handoff_security_event(
                "handoff_claim_mk_fail",
                ip=ip_hash,
                handoff=handoff_id[:24],
                fails=fail_count,
            )
            return jsonify({"success": False, "error": "handoff_mk_mismatch"}), 403

        if not _validate_handoff_verification_session(session_id, entry):
            _log_handoff_security_event(
                "handoff_claim_session_invalid",
                ip=ip_hash,
                handoff=handoff_id[:24],
                session=session_id[:24],
            )
            return jsonify({"success": False, "error": "handoff_session_invalid"}), 403

        try:
            from api.ishuman_demo import complete_skeleton_handoff_after_claim

            complete_skeleton_handoff_after_claim(session_id)
        except Exception:
            logger.exception("Skeleton handoff auto-complete failed session=%s", session_id[:24])

    if not _delete_idv_mobile_handoff_entry(entry):
        _log_handoff_security_event(
            "handoff_claim_race",
            ip=ip_hash,
            handoff=(entry.get("handoff_id") or "")[:24],
            session=(entry.get("session_id") or "")[:24],
        )
        return jsonify({"success": False, "error": "handoff_already_claimed"}), 409

    _log_handoff_security_event(
        "handoff_claim_ok",
        ip=ip_hash,
        handoff=(entry.get("handoff_id") or "")[:24],
        session=(entry.get("session_id") or "")[:24],
        wallet=str(entry.get("wallet_id") or "")[:24],
    )

    return jsonify({
        "success": True,
        "wallet_id": entry.get("wallet_id"),
        "session_id": entry.get("session_id"),
        "encrypted_blob": entry.get("encrypted_blob"),
    })


_SITE_PROOF_REDIRECT_TTL_SECONDS = 900


def _site_proof_redirect_key(request_nonce: str) -> str:
    return f"ishuman:site-proof-redirect:{request_nonce}"


def _action_sign_redirect_key(request_nonce: str) -> str:
    return f"ishuman:action-sign-redirect:{request_nonce}"


@ishuman_bp.route("/api/ishuman/site-proof-redirect/deposit", methods=["POST"])
@cross_origin()
def site_proof_redirect_deposit():
    """Store a site-proof bundle for same-tab mobile redirect return."""
    from auth.redis_store import store as redis_store

    body = request.get_json(silent=True) or {}
    request_nonce = (body.get("request_nonce") or "").strip()
    site_id = (body.get("site_id") or "").strip()
    wallet_id = (body.get("wallet_id") or "").strip()
    credential = body.get("credential")
    session_assertion = body.get("session_assertion")
    session_signature = (body.get("session_signature") or "").strip()
    session_nonce = (body.get("session_nonce") or "").strip()

    if not request_nonce or len(request_nonce) < 8:
        return jsonify({"success": False, "error": "request_nonce required"}), 400
    if not site_id or not wallet_id or not isinstance(credential, dict) or not isinstance(session_assertion, dict):
        return jsonify({"success": False, "error": "missing_site_proof_fields"}), 400
    if not session_signature:
        return jsonify({"success": False, "error": "session_signature required"}), 400

    body["request_nonce"] = request_nonce
    body["site_id"] = site_id
    err, _wid = _require_wallet_assertion(
        body,
        field_names=["request_nonce", "site_id"],
    )
    if err:
        return err

    redis_store(
        _site_proof_redirect_key(request_nonce),
        {
            "site_id": site_id,
            "wallet_id": wallet_id,
            "credential": credential,
            "session_assertion": session_assertion,
            "session_signature": session_signature,
            "session_nonce": session_nonce,
        },
        ttl_seconds=_SITE_PROOF_REDIRECT_TTL_SECONDS,
    )
    return jsonify({"success": True, "expires_in": _SITE_PROOF_REDIRECT_TTL_SECONDS})


@ishuman_bp.route("/api/ishuman/site-proof-redirect/claim", methods=["POST"])
@cross_origin()
def site_proof_redirect_claim():
    """One-time claim of a redirect-deposited site proof bundle."""
    from auth.redis_store import delete as redis_delete
    from auth.redis_store import get as redis_get

    body = request.get_json(silent=True) or {}
    request_nonce = (body.get("request_nonce") or "").strip()
    if not request_nonce:
        return jsonify({"success": False, "error": "request_nonce required"}), 400

    entry = redis_get(_site_proof_redirect_key(request_nonce))
    if not entry:
        return jsonify({"success": False, "error": "redirect_proof_not_found"}), 404
    if not redis_delete(_site_proof_redirect_key(request_nonce)):
        return jsonify({"success": False, "error": "redirect_proof_already_claimed"}), 409

    return jsonify({
        "success": True,
        "site_id": entry.get("site_id"),
        "credential": entry.get("credential"),
        "session_assertion": entry.get("session_assertion"),
        "session_signature": entry.get("session_signature"),
        "session_nonce": entry.get("session_nonce"),
    })


@ishuman_bp.route("/api/ishuman/action-sign-redirect/deposit", methods=["POST"])
@cross_origin()
def action_sign_redirect_deposit():
    """Store an action-sign bundle for same-tab mobile redirect return."""
    from auth.redis_store import store as redis_store

    body = request.get_json(silent=True) or {}
    request_nonce = (body.get("request_nonce") or "").strip()
    site_id = (body.get("site_id") or "").strip()
    wallet_id = (body.get("wallet_id") or "").strip()
    sign_result = body.get("sign_result")

    if not request_nonce or len(request_nonce) < 8:
        return jsonify({"success": False, "error": "request_nonce required"}), 400
    if not site_id or not wallet_id or not isinstance(sign_result, dict):
        return jsonify({"success": False, "error": "missing_action_sign_fields"}), 400
    if not sign_result.get("action_assertion") or not sign_result.get("action_signature"):
        return jsonify({"success": False, "error": "action_sign_incomplete"}), 400

    body["request_nonce"] = request_nonce
    body["site_id"] = site_id
    err, _wid = _require_wallet_assertion(
        body,
        field_names=["request_nonce", "site_id"],
    )
    if err:
        return err

    redis_store(
        _action_sign_redirect_key(request_nonce),
        {
            "site_id": site_id,
            "wallet_id": wallet_id,
            "sign_result": sign_result,
        },
        ttl_seconds=_SITE_PROOF_REDIRECT_TTL_SECONDS,
    )
    return jsonify({"success": True, "expires_in": _SITE_PROOF_REDIRECT_TTL_SECONDS})


@ishuman_bp.route("/api/ishuman/action-sign-redirect/claim", methods=["POST"])
@cross_origin()
def action_sign_redirect_claim():
    """One-time claim of a redirect-deposited action-sign bundle."""
    from auth.redis_store import delete as redis_delete
    from auth.redis_store import get as redis_get

    body = request.get_json(silent=True) or {}
    request_nonce = (body.get("request_nonce") or "").strip()
    if not request_nonce:
        return jsonify({"success": False, "error": "request_nonce required"}), 400

    entry = redis_get(_action_sign_redirect_key(request_nonce))
    if not entry:
        return jsonify({"success": False, "error": "redirect_action_sign_not_found"}), 404
    if not redis_delete(_action_sign_redirect_key(request_nonce)):
        return jsonify({"success": False, "error": "redirect_action_sign_already_claimed"}), 409

    return jsonify({
        "success": True,
        "site_id": entry.get("site_id"),
        "sign_result": entry.get("sign_result"),
    })


# ---------------------------------------------------------------------------
# 8b. Re-verify a presentation bundle (relying-site backend helper)
# ---------------------------------------------------------------------------


def _verify_session_assertion_server(
    assertion: dict,
    signature_b64url: str,
    site_pubkey_b64url: str,
    expected_site_id: str,
    expected_bloom_sequence: Optional[int],
) -> tuple[bool, str]:
    """Verify the site-bound session assertion (mirrors verifySessionAssertion in JS)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature

    required = (
        "session_id",
        "site_id",
        "credential_id",
        "subject",
        "session_nonce",
        "bloom_sequence",
        "issued_at_unix",
        "expires_at_unix",
    )
    for key in required:
        value = assertion.get(key)
        if value in (None, ""):
            return False, f"session_{key}_missing"

    try:
        expires_at = int(assertion["expires_at_unix"])
    except (TypeError, ValueError):
        return False, "session_expires_at_invalid"
    if int(time.time()) >= expires_at - 5:
        return False, "session_expired"

    if expected_site_id and str(assertion["site_id"]) != str(expected_site_id):
        return False, "session_site_id_mismatch"

    if expected_bloom_sequence is not None:
        try:
            if int(assertion["bloom_sequence"]) != int(expected_bloom_sequence):
                return False, "session_bloom_sequence_mismatch"
        except (TypeError, ValueError):
            return False, "session_bloom_sequence_invalid"

    SESSION_PRESENTATION_PREFIX = "lemma:site-session-presentation:v1"
    payload_lines = [
        SESSION_PRESENTATION_PREFIX,
        str(assertion["session_id"]).strip(),
        str(assertion["site_id"]).strip(),
        str(assertion["credential_id"]).strip(),
        str(assertion["subject"]).strip(),
        str(assertion["session_nonce"]).strip(),
        str(assertion["bloom_sequence"]),
        str(assertion["issued_at_unix"]),
        str(assertion["expires_at_unix"]),
    ]
    message = "\n".join(payload_lines).encode("utf-8")

    try:
        pubkey_bytes = base64.urlsafe_b64decode(
            site_pubkey_b64url + "=" * ((4 - len(site_pubkey_b64url) % 4) % 4)
        )
        signature_bytes = base64.urlsafe_b64decode(
            signature_b64url + "=" * ((4 - len(signature_b64url) % 4) % 4)
        )
        digest = hashlib.sha256(message).digest()
        Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(signature_bytes, digest)
    except InvalidSignature:
        return False, "invalid_session_signature"
    except Exception as exc:  # noqa: BLE001
        return False, f"session_verify_error:{exc}"

    return True, "ok"


@ishuman_bp.route("/api/ishuman/verify-presentation", methods=["POST"])
@cross_origin()
def verify_presentation():
    """OPTIONAL convenience endpoint, re-verify a presentation bundle server-side.

    Relying sites do **not** need to call this endpoint. The recommended path is
    purely local verification on the relying site's own backend using the
    signed trust list + Bloom snapshot from ``GET /api/revocation/bloom-filter``
    (cached for up to ``max_bloom_staleness_seconds``). See
    ``examples/proof-verifier.py`` for a drop-in implementation.

    Privacy / cost trade-off when this endpoint IS called:
      * lemma.id observes the PPID, site_id, and timing for every request.
      * Calls scale linearly with the relying site's traffic.
      * Local verification leaks none of this and incurs zero per-request cost.

    What gets re-checked when this endpoint is called:
      1. The credential's browser-canonical Ed25519 signature was produced by a
         trusted issuer (against the live trust list)
      2. The credential is bound to the expected site_id
      3. The credential is not expired and not revoked (server-side Bloom check)
      4. The site-bound session assertion is signed by the credential's site key

    Request body::

        {
            "site_id": "tickets-demo.lemma.id",          # expected site binding
            "credential": { ... },                        # full VC with proof.signatureValueWeb
            "session_assertion": { ... },                 # optional
            "session_signature": "<base64url>",           # optional
            "session_nonce": "<base64url>",               # optional
            "bloom_sequence": 0                           # optional, snapshot binding
        }
    """
    body = request.get_json(silent=True) or {}
    payload, status = verify_presentation_payload(body)
    return jsonify(payload), status


def verify_presentation_payload(body: dict) -> tuple[dict, int]:
    """Core server-side presentation verification, callable without HTTP.

    Used by the /api/ishuman/verify-presentation endpoint above and by the
    platform's own sign-in session endpoint (api/lemma_session_auth.py).
    Returns (payload, http_status); payload["success"] is the verdict.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature

    credential = body.get("credential")
    if not isinstance(credential, dict):
        return {"success": False, "error": "credential_required"}, 400

    expected_site_id = (body.get("site_id") or "").strip()
    proof = credential.get("proof") or {}
    sig_hex = (proof.get("signatureValueWeb") or proof.get("signatureValue") or "").strip()
    if not sig_hex:
        return {"success": False, "error": "missing_signature"}, 400

    issuer_did = (credential.get("issuer") or (credential.get("issuerInfo") or {}).get("did") or "").strip()
    client_supplied_pubkey_hex = ((credential.get("issuerInfo") or {}).get("publicKey") or "").strip().lower()
    if not issuer_did:
        return {"success": False, "error": "missing_issuer"}, 400

    try:
        from api.trusted_issuers import is_trusted_issuer
        if not is_trusted_issuer(issuer_did):
            return {"success": False, "error": "untrusted_issuer"}, 403
    except Exception as exc:
        logger.warning("Trust list check unavailable: %s", exc)
        return {"success": False, "error": "trust_list_unavailable"}, 503

    # SECURITY: derive the verification key from the TRUSTED issuer DID, NEVER
    # from the client-supplied issuerInfo.publicKey. Lemma issuer DIDs embed the
    # Ed25519 public key (did:lemma:<pubkey_hex>). Trusting issuerInfo.publicKey
    # would let an attacker pair any trusted DID with their own keypair and forge
    # a valid-looking "human: true" presentation for an arbitrary PPID/site.
    issuer_pubkey_hex = ""
    if issuer_did.startswith("did:lemma:"):
        issuer_pubkey_hex = issuer_did.split(":", 2)[2].split("#", 1)[0].split("?", 1)[0].strip()
    if not issuer_pubkey_hex:
        # Non-did:lemma trusted issuers do not embed a key here; refuse rather
        # than trust a client-provided key.
        return {"success": False, "error": "issuer_pubkey_unresolvable"}, 400
    # If the credential also carries issuerInfo.publicKey, it must match the
    # DID-bound key exactly (no silent override).
    if client_supplied_pubkey_hex and client_supplied_pubkey_hex != issuer_pubkey_hex.lower():
        return {"success": False, "error": "issuer_pubkey_mismatch"}, 400

    try:
        pubkey_bytes = bytes.fromhex(issuer_pubkey_hex)
        signature_bytes = bytes.fromhex(sig_hex)
    except ValueError:
        return {"success": False, "error": "malformed_signature"}, 400

    try:
        message = _browser_canonical_message(credential)
        digest = hashlib.sha256(message).digest()
        Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(signature_bytes, digest)
    except InvalidSignature:
        return {"success": False, "error": "invalid_signature"}, 400
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"verify_error:{exc}"}, 400

    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    assurance = str(claims.get("assurance") or "").strip().lower()
    if not assurance and claims.get("isHuman") in (True, "true", "True", 1, "1"):
        assurance = "ishuman"
    if assurance not in ("passkey", "ishuman"):
        return {"success": False, "error": "not_ishuman"}, 400

    required_assurance = (body.get("required_assurance") or "ishuman").strip().lower()
    if not _assurance_meets_policy(assurance, required_assurance):
        return {"success": False, "error": "assurance_insufficient"}, 400
    from api.site_hostname import normalize_runtime_site_binding

    bound_site_raw = (
        claims.get("siteDomain")
        or claims.get("site_domain")
        or claims.get("siteId")
        or claims.get("site_id")
        or claims.get("site")
        or ""
    )
    bound_site = normalize_runtime_site_binding(bound_site_raw)
    expected_site = normalize_runtime_site_binding(expected_site_id) if expected_site_id else None
    if expected_site and bound_site and bound_site != expected_site:
        return {"success": False, "error": "site_id_mismatch", "bound_site": bound_site}, 400

    try:
        expires_at = int(claims.get("expiresAt") or 0)
        if expires_at and expires_at < int(time.time()):
            return {"success": False, "error": "expired"}, 400
    except (TypeError, ValueError):
        pass

    credential_id = credential.get("id") or ""
    from api.revocation_verifier import check_credential_revocation

    revocation_status = check_credential_revocation(credential)
    if revocation_status == "revoked":
        return {"success": False, "error": "revoked"}, 400
    if revocation_status == "unavailable":
        return {"success": False, "error": "revocation_unavailable"}, 503

    session_assertion = body.get("session_assertion") or None
    session_signature = (body.get("session_signature") or "").strip()
    session_status = "absent"
    session_reason = "ok"
    if session_assertion and session_signature:
        site_pubkey = claims.get("site_signing_pubkey") or claims.get("siteSigningPubkey") or ""
        if not site_pubkey:
            session_status = "skipped"
            session_reason = "credential_missing_site_signing_pubkey"
        else:
            ok, reason = _verify_session_assertion_server(
                assertion=session_assertion,
                signature_b64url=session_signature,
                site_pubkey_b64url=site_pubkey,
                expected_site_id=expected_site_id or bound_site,
                expected_bloom_sequence=body.get("bloom_sequence"),
            )
            session_status = "valid" if ok else "invalid"
            session_reason = reason
            if not ok:
                return {
                    "success": False,
                    "error": session_reason,
                    "session_status": session_status,
                }, 400

    return {
        "success": True,
        "human": True,
        "assurance": assurance,
        "ppid": credential.get("subject"),
        "credential_id": credential_id,
        "site_id": bound_site,
        "issuer": issuer_did,
        "session_status": session_status,
        "session_reason": session_reason,
    }, 200


# ---------------------------------------------------------------------------
# 9. Approve network revocation (admin action)
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/approve-revocation", methods=["POST"])
@cross_origin()
def approve_network_revocation():
    """Retired: cross-site credential enumeration is no longer retained."""
    return jsonify({"success": False, "error": "network_revocation_retired"}), 410
