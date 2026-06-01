"""
isHuman Network API
===================

Core product endpoints for the Lemma isHuman proof-of-humanity network.

Flows
-----
1. **Start verification** — create a Stripe Identity session, return client
   secret so the browser can embed the Stripe Identity modal.
2. **Stripe webhook** — receive ``identity.verification_session.verified``
   (or failed/canceled), issue an Ed25519-signed isHuman credential on success.
3. **Site-block** — a site immediately blocks a PPID on its own domain
   (first tier of two-tier revocation).
4. **Network revocation** — a site submits evidence for network-wide
   credential revocation (second tier, queued for review).
5. **Check** — quick lookup: is a PPID blocked for a given site?
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

import stripe
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin

logger = logging.getLogger(__name__)

ishuman_bp = Blueprint("ishuman", __name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ISHUMAN_CREDENTIAL_TTL_DAYS = int(os.getenv("ISHUMAN_CREDENTIAL_TTL_DAYS", "365"))
STRIPE_IDENTITY_COST_CENTS = 200  # $2.00 per verification


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
    JSON.stringify({issuer, subject, claims: sorted, issuedAt, expiresAt})
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
    # JS canonicalMessage references credential.issuedAt / credential.expiresAt
    # (top-level). The Rust serializer renames these to issuanceDate /
    # expirationDate, so the legacy JS keys are typically absent and omitted
    # by JSON.stringify. Match that behaviour: only include when present.
    if credential.get("issuedAt") is not None:
        payload["issuedAt"] = credential["issuedAt"]
    if credential.get("expiresAt") is not None:
        payload["expiresAt"] = credential["expiresAt"]

    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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
) -> dict:
    """Sign and return a new isHuman credential for *ppid*.

    If *site_id* is provided, the credential is bound to that site
    (per-site derived proof).  Otherwise it is the master proof bound
    to ``lemma.id``.

    *verification_method* records which IDV rail established the underlying
    proof of personhood (``didit`` is the standard rail; ``stripe_identity``
    is retained only for legacy records). It is derived from the verification
    record's ``issuer_id`` so derived/reissued credentials stay consistent
    with how the human was originally verified.
    """
    issuer = _get_ishuman_issuer()
    now = int(time.time())
    prefix = "ishuman_site" if site_id else "ishuman_master"
    credential_id = f"{prefix}_{secrets.token_urlsafe(24)}"

    claims: dict = {
        "isHuman": True,
        "verificationMethod": (verification_method or "didit"),
        "packageType": "identity",
        "siteId": site_id or "lemma.id",
        "issuedAt": str(now),
        "expiresAt": str(now + ISHUMAN_CREDENTIAL_TTL_DAYS * 86400),
    }
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
    except Exception as exc:  # noqa: BLE001 — non-fatal: server still has Rust sig
        logger.warning("Failed to add browser-format signature to credential: %s", exc)

    return credential


def _require_site_api_key():
    """Validate the API key in the request and return the site row, or None."""
    api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
    if not api_key:
        return None

    from api.database import SessionLocal, Site
    db = SessionLocal()
    try:
        site = db.query(Site).filter_by(api_key=api_key).first()
        return site
    finally:
        db.close()


def _derive_ppid_for_site(
    *,
    rp_id: str,
    wallet_secret: Optional[str] = None,
    wallet_id: Optional[str] = None,
    lemma_person_id: Optional[str] = None,
    db=None,
) -> str:
    """Derive site PPID from person-root (preferred) or wallet_secret (legacy)."""
    if lemma_person_id and db is not None:
        from api.identity_person import load_person_root_bytes
        from api.ppid import derive_ppid_from_person_root

        person_root = load_person_root_bytes(db, lemma_person_id)
        return derive_ppid_from_person_root(person_root, rp_id)

    from api.ppid import derive_ppid_from_wallet_secret

    if not wallet_secret:
        raise ValueError("wallet_secret or lemma_person_id required for PPID derivation")
    return derive_ppid_from_wallet_secret(wallet_secret, rp_id)


def _derive_master_ppid_for_person(db, lemma_person_id: str) -> str:
    return _derive_ppid_for_site(rp_id="lemma.id", lemma_person_id=lemma_person_id, db=db)


def _complete_verified_ishuman_from_stripe(
    db,
    record,
    *,
    wallet_id: str,
    stripe_session_id: str,
) -> Optional[dict]:
    """
    Resolve document/person roots from Stripe and issue master isHuman credential.

    Returns credential dict on success, None on root material failure.
    """
    from api.identity_roots import IdentityRootMaterialError
    from api.identity_person import process_verified_stripe_identity
    from api.ppid import derive_ppid_from_person_root_hash

    try:
        resolved, _session = process_verified_stripe_identity(
            db,
            stripe_session_id=stripe_session_id,
            wallet_id=wallet_id,
        )
    except IdentityRootMaterialError as exc:
        logger.error(
            "Identity root material unavailable for stripe session %s: %s",
            stripe_session_id,
            exc,
        )
        record.status = "failed"
        record.metadata_json = {
            **(record.metadata_json or {}),
            "root_error": str(exc),
        }
        return None

    from api.identity_roots import active_root_version

    ppid = derive_ppid_from_person_root_hash(resolved.person_root_hash, "lemma.id")
    record.lemma_person_id = resolved.person_id
    record.document_root_hash = resolved.document_root_hash
    record.root_version = active_root_version()
    record.confidence_level = resolved.confidence_level

    # v2 (Phase 1.1): seal person-root seed envelopes for the wallet, if it
    # posted an encryption pubkey at IDV start. Best-effort and feature-flagged;
    # a failure here must never block credential issuance.
    try:
        _maybe_store_seed_envelopes(record, wallet_id, resolved.person_root_hash)
    except Exception:
        logger.exception("Seed-envelope generation failed (non-fatal) for wallet %s", wallet_id)

    credential = _issue_ishuman_credential(
        ppid,
        wallet_id,
        ppid_derivation="person_root_v1",
        verification_method="stripe_identity",
    )
    record.ppid = ppid
    return credential


def _complete_verified_ishuman_from_didit(
    db,
    record,
    *,
    wallet_id: str,
    decision: dict,
) -> Optional[dict]:
    """Resolve document/person roots from a didit decision and issue the master VC.

    Parallel to _complete_verified_ishuman_from_stripe, but the decision is the
    (already HMAC-authenticated) didit webhook payload rather than a re-fetched
    Stripe session. Lemma still signs the credential with its own issuer key.
    Returns the credential dict on success, None on root material failure.
    """
    from api.identity_roots import IdentityRootMaterialError, active_root_version
    from api.identity_person import process_verified_didit_identity
    from api.ppid import derive_ppid_from_person_root_hash

    try:
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

    ppid = derive_ppid_from_person_root_hash(resolved.person_root_hash, "lemma.id")
    record.lemma_person_id = resolved.person_id
    record.document_root_hash = resolved.document_root_hash
    record.root_version = active_root_version()
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
    )
    record.ppid = ppid
    return credential


def revoke_wallet_network_wide(
    db,
    *,
    wallet_id: Optional[str] = None,
    master_credential_id: Optional[str] = None,
    reason: str = "network revocation",
    revoked_by: str = "admin",
) -> dict:
    """Revoke a wallet's master + derived isHuman credentials network-wide.

    Shared core for the admin approve-revocation route and the didit risk feed
    (Phase 2 / M3). Creates wallet/credential RevocationList rows, marks rows
    revoked, commits, and publishes events so the Bloom snapshot rebuilds.

    Raises ValueError if the wallet cannot be resolved.
    """
    from api.database import (
        DerivedCredential, IsHumanVerification, RevocationList, SiteBlock,
    )

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

    derived_rows = db.query(DerivedCredential).filter_by(
        wallet_id=wallet_id, is_active=True
    ).all()
    for d in derived_rows:
        db.add(RevocationList(
            lemma_id=d.derived_credential_id,
            credential_id=d.derived_credential_id,
            lemma_type="ishuman",
            revocation_type="credential",
            revoked_by=revoked_by,
            reason=reason,
        ))
        revoked_ids.append(d.derived_credential_id)
        d.is_active = False
        d.revoked_at = datetime.utcnow()

    pending_blocks = (
        db.query(SiteBlock)
        .filter_by(network_revocation_status="pending_review")
        .filter(
            SiteBlock.ppid.in_(
                [d.derived_ppid for d in derived_rows] +
                [m.ppid for m in masters if m.ppid]
            )
        )
        .all()
    )
    for b in pending_blocks:
        b.network_revocation_status = "approved"

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
        "derived_count": len(derived_rows),
    }


def _handle_didit_risk_event(webhook_type: str, status: str, body: dict) -> None:
    """Map a didit ongoing risk event to a network revocation (Phase 2 / M3).

    didit's continuous monitoring (block, AML hit, fraud transaction) is an
    authoritative downstream signal: when a previously-verified human is blocked
    or flagged, we revoke their Lemma credential network-wide so every relying
    site enforces it locally via the Bloom snapshot — with no per-request didit
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
    wallet_secret: Optional[str],
    target_site: str,
    lemma_person_id: Optional[str] = None,
) -> Optional[str]:
    """Return an error code if derivation must be denied for revocation/block."""
    from api.revocation_verifier import is_credential_revoked
    from api.site_ppid_revocation import is_site_ppid_blocked, resolve_site_by_domain

    if is_credential_revoked(master_credential_id):
        return "master_credential_revoked"

    try:
        site_ppid = _derive_ppid_for_site(
            rp_id=target_site,
            wallet_secret=wallet_secret,
            wallet_id=wallet_id,
            lemma_person_id=lemma_person_id,
            db=db,
        )
    except ValueError:
        return "ppid_derivation_failed"

    if is_credential_revoked(site_ppid):
        return "site_ppid_revoked"

    site = resolve_site_by_domain(db, target_site)
    if site and is_site_ppid_blocked(db, site_id=site.site_id, ppid=site_ppid):
        return "site_ppid_blocked"

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

def start_verification_for_body(body: dict) -> tuple[dict, int]:
    """Run start-verification logic for a JSON body (shared with demo routes)."""
    body = body or {}
    wallet_id = body.get("wallet_id")
    wallet_secret = body.get("wallet_secret")
    if not wallet_id:
        return {"success": False, "error": "wallet_id required"}, 400

    err, _wid = _require_wallet_assertion(body, field_names=["return_url"])
    if err:
        return err[0].get_json(), err[1]

    return_url = body.get(
        "return_url",
        os.getenv("ISHUMAN_RETURN_URL", "https://lemma.id/app"),
    )

    # Provider routing. isHuman verification runs on Didit, which replaced
    # Stripe Identity as the IDV rail. Didit is the default and fails closed if
    # unconfigured (never silently substitutes another provider). Stripe Identity
    # is retained only as an explicit, opt-in legacy escape hatch
    # (provider="stripe_identity") and is no longer the default path.
    provider = (body.get("provider") or "didit").strip().lower()
    if provider == "stripe_identity":
        from billing.stripe_manager import StripeManager
        mgr = StripeManager()
        result = mgr.create_identity_verification_session(
            user_id=wallet_id,
            return_url=return_url,
        )
        if not result.get("success"):
            logger.error("Stripe Identity session creation failed: %s", result)
            return {"success": False, "error": result.get("error", "stripe_error")}, 502
    else:
        provider = "didit"
        from api.config import is_ishuman_didit_enabled
        if not is_ishuman_didit_enabled():
            return {"success": False, "error": "didit_not_enabled"}, 400
        from billing.didit_manager import DiditManager
        result = DiditManager().create_identity_verification_session(
            user_id=wallet_id,
            return_url=return_url,
        )
        if not result.get("success"):
            logger.error("Didit session creation failed: %s", result)
            return {"success": False, "error": result.get("error", "didit_error")}, 502

    provider_session_id = result["session_id"]
    session_id = f"ishuman_sess_{secrets.token_urlsafe(16)}"

    from api.database import SessionLocal, IsHumanVerification
    db = SessionLocal()
    try:
        derived_ppid = None
        if wallet_secret:
            try:
                derived_ppid = _derive_ppid_for_site(
                    rp_id="lemma.id",
                    wallet_secret=wallet_secret,
                    wallet_id=wallet_id,
                )
            except Exception:
                logger.exception("Failed pre-deriving PPID during isHuman start-verification")

        # v2 (Phase 1.1): the wallet may post a one-time X25519 encryption
        # pubkey so the server can seal person-root seed envelopes at IDV
        # completion. Stored as metadata; ignored unless the feature is enabled.
        verification_metadata = {"return_url": return_url}
        enc_pubkey = (body.get("enc_pubkey") or "").strip()
        if enc_pubkey:
            verification_metadata["enc_pubkey"] = enc_pubkey

        # Dedup: the provider can reuse one hosted session across repeated
        # start-verification calls (e.g. the user re-clicks before redirect).
        # Reuse the existing in-flight row for this provider session + wallet so
        # the hosted session maps to exactly ONE local record — otherwise the
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
                # Stripe keeps its dedicated column for back-compat; all providers
                # also populate the generic provider_session_id used for lookups.
                stripe_session_id=provider_session_id if provider == "stripe_identity" else None,
                provider_session_id=provider_session_id,
                issuer_id=provider,
                wallet_id=wallet_id,
                ppid=derived_ppid,
                status="pending",
                metadata_json=verification_metadata,
            )
            db.add(verification)
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist isHuman verification session")
        return {"success": False, "error": "verification_session_persist_failed"}, 500
    finally:
        db.close()

    logger.info(
        "isHuman verification started: %s (provider=%s session=%s)",
        session_id,
        provider,
        provider_session_id,
    )

    response: dict = {
        "success": True,
        "session_id": session_id,
        "provider": provider,
        "provider_session_id": provider_session_id,
        "url": result.get("url"),
    }
    # Preserve the Stripe response shape (client_secret + stripe_session_id) so
    # existing Stripe Identity frontends keep working unchanged.
    if provider == "stripe_identity":
        response["stripe_session_id"] = provider_session_id
        response["client_secret"] = result.get("client_secret")
    return response, 200


@ishuman_bp.route("/api/ishuman/start-verification", methods=["POST"])
@cross_origin()
def start_verification():
    """Create a Stripe Identity session for a new isHuman verification.

    Request body::

        {
            "wallet_id": "...",       // browser wallet id
            "return_url": "..."       // optional, defaults to lemma.id/app
        }

    Returns ``client_secret`` that the frontend uses to mount the Stripe
    Identity modal.
    """
    body = request.get_json(silent=True) or {}
    payload, status = start_verification_for_body(body)
    return jsonify(payload), status


# ---------------------------------------------------------------------------
# 2. Stripe Identity Webhook
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/webhooks/stripe-identity", methods=["POST"])
def stripe_identity_webhook():
    """Receive Stripe Identity webhook events.

    On ``identity.verification_session.verified`` we issue an isHuman
    credential and store it against the verification record so the client
    can poll for it.
    """
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_IDENTITY_WEBHOOK_SECRET") or os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        logger.error("No Stripe webhook secret configured")
        return jsonify({"error": "webhook_not_configured"}), 500

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning("Stripe webhook signature verification failed: %s", exc)
        return jsonify({"error": "invalid_signature"}), 400

    event_type = event["type"]
    session_obj = event["data"]["object"]
    stripe_session_id = session_obj["id"]

    logger.info("Stripe Identity webhook: type=%s session=%s", event_type, stripe_session_id)

    from api.database import SessionLocal, IsHumanVerification
    db = SessionLocal()
    try:
        record = db.query(IsHumanVerification).filter_by(
            stripe_session_id=stripe_session_id
        ).first()

        if not record:
            logger.warning("No verification record for stripe session %s", stripe_session_id)
            return jsonify({"received": True}), 200

        if event_type == "identity.verification_session.verified":
            wallet_id = record.wallet_id or session_obj.get("metadata", {}).get("user_id", "")

            credential = _complete_verified_ishuman_from_stripe(
                db,
                record,
                wallet_id=wallet_id,
                stripe_session_id=stripe_session_id,
            )
            if not credential:
                db.commit()
                return jsonify({"received": True}), 200

            record.status = "verified"
            record.verified_at = datetime.utcnow()
            record.credential_id = credential.get("id")
            record.issued_at = datetime.utcnow()
            record.expires_at = datetime.utcnow() + timedelta(days=ISHUMAN_CREDENTIAL_TTL_DAYS)
            record.metadata_json = {
                **(record.metadata_json or {}),
                "credential_issuer_did": credential.get("issuerInfo", {}).get("did"),
                "ppid_derivation": "person_root_v1",
            }
            db.commit()

            logger.info(
                "isHuman credential issued: ppid=%s credential_id=%s person=%s",
                (record.ppid or "")[:40],
                credential.get("id"),
                record.lemma_person_id,
            )

            # Successful real IDV is the network's amnesty signal: lift any
            # prior amnesty-eligible revocations for this wallet so the user
            # can rejoin sites that previously blocked them. The IDV cost
            # (Stripe Identity + real document) is the deterrent; refusing
            # to ever let a human back in is not.
            try:
                from api.site_ppid_revocation import clear_amnesty_eligible_wallet_revocations
                clear_amnesty_eligible_wallet_revocations(
                    db,
                    wallet_id=wallet_id,
                    new_master_credential_id=credential.get("id") or "",
                    reason="stripe_identity_verified",
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to clear amnesty-eligible revocations after Stripe Identity verified for wallet %s",
                    wallet_id,
                )

        elif event_type in (
            "identity.verification_session.requires_input",
            "identity.verification_session.canceled",
        ):
            record.status = "failed" if "requires_input" in event_type else "canceled"
            db.commit()

        return jsonify({"received": True}), 200

    except Exception:
        db.rollback()
        logger.exception("Error processing Stripe Identity webhook")
        return jsonify({"error": "processing_failed"}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2a. Didit Identity Webhook (Phase 3.2 second IDV rail)
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
                db, record, wallet_id=wallet_id, decision=decision,
            )
            if not credential:
                db.commit()
                return jsonify({"received": True}), 200

            record.status = "verified"
            record.verified_at = datetime.utcnow()
            record.credential_id = credential.get("id")
            record.issued_at = datetime.utcnow()
            record.expires_at = datetime.utcnow() + timedelta(days=ISHUMAN_CREDENTIAL_TTL_DAYS)
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

        elif status in ("declined", "expired", "abandoned"):
            record.status = "failed" if status == "declined" else status
            db.commit()

        return jsonify({"received": True}), 200

    except Exception:
        db.rollback()
        logger.exception("Error processing didit webhook")
        return jsonify({"error": "processing_failed"}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2b. Poll for credential (client polls after Stripe modal closes)
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/verification-status/<session_id>", methods=["GET"])
@cross_origin()
def verification_status(session_id: str):
    """Poll the status of an isHuman verification.

    After the Stripe Identity modal closes, the client polls this endpoint
    until status becomes ``verified`` (and the credential is ready) or a
    terminal failure state.
    """
    from api.database import SessionLocal, IsHumanVerification
    db = SessionLocal()
    try:
        record = db.query(IsHumanVerification).filter_by(session_id=session_id).first()
        if not record:
            return jsonify({"success": False, "error": "session_not_found"}), 404

        # Duplicate-session resolution. The same provider (Didit) hosted session
        # can map to more than one local verification row — e.g. when
        # start-verification is called twice for one hosted flow, both rows share
        # the same provider_session_id. The webhook only flips the FIRST matching
        # row to verified, so a client polling a sibling row would see 'pending'
        # forever even though the master credential was already issued. If the
        # polled row isn't verified yet, fall back to any verified sibling for the
        # same provider session (then the same wallet) and serve its credential.
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

        resp: dict = {
            "success": True,
            "status": record.status,
            "session_id": record.session_id,
        }

        if record.status == "verified" and record.credential_id:
            resp["credential_id"] = record.credential_id
            resp["ppid"] = record.ppid

            # Re-issue the credential so the client can store it
            try:
                meta = record.metadata_json or {}
                ppid_deriv = meta.get("ppid_derivation") or (
                    "person_root_v1" if record.lemma_person_id else None
                )
                credential = _issue_ishuman_credential(
                    record.ppid,
                    record.wallet_id,
                    ppid_derivation=ppid_deriv,
                    verification_method=(record.issuer_id or "didit"),
                )
                credential["id"] = record.credential_id
                resp["credential"] = credential
                if record.lemma_person_id:
                    resp["lemma_person_id"] = record.lemma_person_id
            except Exception:
                logger.exception("Failed to re-issue credential for polling")

        return jsonify(resp)
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
            "reason": "Terms violation — automated activity detected"
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

    from api.database import SessionLocal, SiteBlock
    db = SessionLocal()
    try:
        block = (
            db.query(SiteBlock)
            .filter_by(site_id=site.site_id, ppid=ppid, is_active=True)
            .first()
        )
        if not block:
            return jsonify({"success": False, "error": "no active block found"}), 404

        block.is_active = False
        db.commit()

        logger.info("Site block removed: site=%s ppid=%s", site.site_id, ppid[:40])
        return jsonify({"success": True, "message": "Block removed"})
    except Exception:
        db.rollback()
        logger.exception("Failed to remove site block")
        return jsonify({"success": False, "error": "unblock_failed"}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Network Revocation (second tier — evidence required)
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/network-revoke", methods=["POST"])
@cross_origin()
def network_revoke():
    """Request network-wide revocation of an isHuman credential.

    This queues the request for review.  The credential is NOT revoked
    immediately — only the site block (tier 1) takes effect right away.

    Request body::

        {
            "ppid": "did:lemma:ppid_...",
            "credential_id": "ishuman_...",
            "reason": "Confirmed bot — scripted form submissions",
            "evidence_url": "https://..."
        }
    """
    site = _require_site_api_key()
    if not site:
        return jsonify({"success": False, "error": "valid API key required"}), 401

    body = request.get_json(silent=True) or {}
    ppid = body.get("ppid")
    credential_id = body.get("credential_id")
    reason = body.get("reason", "")
    evidence_url = body.get("evidence_url", "")

    if not ppid and not credential_id:
        return jsonify({"success": False, "error": "ppid or credential_id required"}), 400

    from api.database import SessionLocal
    from api.site_ppid_revocation import revoke_site_bound_ppid

    db = SessionLocal()
    try:
        if ppid:
            revoke_site_bound_ppid(
                db,
                site_id=site.site_id,
                ppid=ppid,
                reason=reason,
                revoked_by=site.admin_email or "site_api",
                site_domain=getattr(site, "site_domain", None),
                blocked_by=site.admin_email,
                evidence_url=evidence_url,
                network_revocation_requested=True,
                network_revocation_status="pending_review",
            )

        logger.info(
            "Network revocation requested: site=%s ppid=%s credential=%s",
            site.site_id, (ppid or "")[:40], (credential_id or "")[:40],
        )

        return jsonify({
            "success": True,
            "message": "Network revocation request submitted for review",
            "status": "pending_review",
            "site_block_active": True,
        })
    except Exception:
        db.rollback()
        logger.exception("Failed to submit network revocation request")
        return jsonify({"success": False, "error": "revocation_request_failed"}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 5. Check — is a PPID blocked on a site?
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/check", methods=["GET"])
@cross_origin()
def check_ppid():
    """Check if a PPID is blocked on a specific site.

    Query params::

        ?ppid=did:lemma:ppid_...&site_id=site_...

    Also checks network-wide revocation via the Bloom filter.
    """
    ppid = request.args.get("ppid")
    site_id = request.args.get("site_id")

    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    result = {"success": True, "ppid": ppid, "blocked": False, "reason": None}

    # Check site-specific block
    if site_id:
        from api.database import SessionLocal, SiteBlock
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

    # Network-wide / Bloom revocation (credential, PPID, wallet_id)
    if not result["blocked"]:
        try:
            from api.revocation_verifier import is_credential_revoked
            if is_credential_revoked(ppid):
                result["blocked"] = True
                result["reason"] = "network_revocation"
        except Exception as exc:
            logger.debug("Bloom revocation check failed for %s: %s", ppid[:30], exc)

    return jsonify(result)


# ---------------------------------------------------------------------------
# 6. Site block list — sites can fetch their full block list
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
                    "network_revocation_requested": b.network_revocation_requested,
                    "network_revocation_status": b.network_revocation_status,
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
    """Public platform statistics for the isHuman network."""
    from api.database import SessionLocal, IsHumanVerification, SiteBlock, RevocationList
    db = SessionLocal()
    try:
        total_verifications = db.query(IsHumanVerification).filter_by(status="verified").count()
        active_blocks = db.query(SiteBlock).filter_by(is_active=True).count()
        network_revocations = db.query(RevocationList).filter_by(lemma_type="ishuman").count()

        return jsonify({
            "success": True,
            "network": "isHuman",
            "total_verifications": total_verifications,
            "active_site_blocks": active_blocks,
            "network_revocations": network_revocations,
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
    4. Records the master → derived mapping for revocation
    5. Returns the per-site credential for the bridge to store
    """
    body = request.get_json(silent=True) or {}
    # v2 (Phase 1.2): master_credential_id is now an OPTIONAL hint. When absent
    # we fall back to the wallet's latest verified record, so a wallet that lost
    # its local master copy can still derive site proofs.
    master_credential_id = (body.get("master_credential_id") or "").strip()
    wallet_id = body.get("wallet_id")
    wallet_secret = body.get("wallet_secret")
    target_site = body.get("target_site")
    site_signing_pubkey_raw = (body.get("site_signing_pubkey") or "").strip()

    if not wallet_id or not target_site:
        return jsonify({
            "success": False,
            "error": "wallet_id and target_site required",
        }), 400

    if not wallet_secret:
        return jsonify({"success": False, "error": "wallet_secret required"}), 400
    try:
        site_signing_pubkey = _normalize_site_signing_pubkey(site_signing_pubkey_raw)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    # Bind master_credential_id into the signed assertion only when supplied so
    # the wallet and server agree on the signed field set in both modes.
    assertion_fields = ["target_site", "site_signing_pubkey"]
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

    from api.database import (
        SessionLocal, IsHumanVerification, DerivedCredential, RevocationList,
    )
    db = SessionLocal()
    try:
        # 1. Resolve the master credential. Prefer the body's hint; otherwise
        #    fall back to the wallet's latest verified record (Phase 1.2).
        master = None
        if master_credential_id:
            master = (
                db.query(IsHumanVerification)
                .filter_by(credential_id=master_credential_id, wallet_id=wallet_id, status="verified")
                .first()
            )
        if not master:
            master = (
                db.query(IsHumanVerification)
                .filter_by(wallet_id=wallet_id, status="verified")
                .order_by(IsHumanVerification.verified_at.desc())
                .first()
            )
        if not master:
            return jsonify({"success": False, "error": "wallet_not_verified"}), 403

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

        deny_reason = _deny_if_derivation_revoked(
            db,
            master_credential_id=master_credential_id,
            wallet_id=wallet_id,
            wallet_secret=wallet_secret,
            target_site=target_site,
            lemma_person_id=person_id,
        )
        if deny_reason:
            return jsonify({"success": False, "error": deny_reason}), 403

        ppid_derivation = "person_root_v1" if person_id else None

        # 2. Check if derivation already exists
        existing = (
            db.query(DerivedCredential)
            .filter_by(
                master_credential_id=master_credential_id,
                target_site=target_site,
                is_active=True,
            )
            .first()
        )
        if existing:
            # Re-issue the credential (same ID) so the caller can store it
            ppid = _derive_ppid_for_site(
                rp_id=target_site,
                wallet_secret=wallet_secret,
                wallet_id=wallet_id,
                lemma_person_id=person_id,
                db=db,
            )
            credential = _issue_ishuman_credential(
                ppid,
                wallet_id,
                site_id=target_site,
                site_signing_pubkey=site_signing_pubkey or None,
                ppid_derivation=ppid_derivation,
                verification_method=(getattr(master, "issuer_id", None) or "didit"),
            )
            credential["id"] = existing.derived_credential_id
            return jsonify({"success": True, "credential": credential, "cached": True})

        # 3. Derive site-specific PPID
        site_ppid = _derive_ppid_for_site(
            rp_id=target_site,
            wallet_secret=wallet_secret,
            wallet_id=wallet_id,
            lemma_person_id=person_id,
            db=db,
        )

        # 4. Issue per-site credential
        credential = _issue_ishuman_credential(
            site_ppid,
            wallet_id,
            site_id=target_site,
            site_signing_pubkey=site_signing_pubkey or None,
            ppid_derivation=ppid_derivation,
            verification_method=(getattr(master, "issuer_id", None) or "didit"),
        )

        # 5. Record the mapping
        derived = DerivedCredential(
            master_credential_id=master_credential_id,
            derived_credential_id=credential["id"],
            wallet_id=wallet_id,
            target_site=target_site,
            derived_ppid=site_ppid,
        )
        db.add(derived)
        db.commit()

        logger.info(
            "Derived site proof: master=%s site=%s derived=%s",
            master_credential_id[:30], target_site, credential["id"][:30],
        )

        return jsonify({"success": True, "credential": credential, "cached": False})

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
    No fresh IDV required — the wallet was already verified, we just hand back
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
    keyed by a random ``transfer_id`` that the NEW device proposes — together
    with a transient X25519 public key — in its QR code:

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
    from auth.redis_store import delete as redis_delete
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
        entry = redis_get(_device_transfer_key(transfer_id))
        if not entry:
            return jsonify({"success": False, "error": "transfer_not_found"}), 404
        # One-time: burn before returning so a replay cannot re-claim.
        if not redis_delete(_device_transfer_key(transfer_id)):
            return jsonify({"success": False, "error": "transfer_already_claimed"}), 409
        return jsonify({
            "success": True,
            "wallet_id": entry.get("wallet_id"),
            "bundle": entry.get("bundle"),
        })

    return jsonify({"success": False, "error": "unknown_action"}), 400


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
        Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(signature_bytes, message)
    except InvalidSignature:
        return False, "invalid_session_signature"
    except Exception as exc:  # noqa: BLE001
        return False, f"session_verify_error:{exc}"

    return True, "ok"


@ishuman_bp.route("/api/ishuman/verify-presentation", methods=["POST"])
@cross_origin()
def verify_presentation():
    """OPTIONAL convenience endpoint — re-verify a presentation bundle server-side.

    Relying sites do **not** need to call this endpoint. The recommended path is
    purely local verification on the relying site's own backend using the
    signed trust list + Bloom snapshot from ``GET /api/revocation/bloom-filter``
    (cached for up to ``max_bloom_staleness_seconds``). See
    ``examples/relying_site_offline_verify.py`` for a drop-in implementation.

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
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature

    body = request.get_json(silent=True) or {}
    credential = body.get("credential")
    if not isinstance(credential, dict):
        return jsonify({"success": False, "error": "credential_required"}), 400

    expected_site_id = (body.get("site_id") or "").strip()
    proof = credential.get("proof") or {}
    sig_hex = (proof.get("signatureValueWeb") or proof.get("signatureValue") or "").strip()
    if not sig_hex:
        return jsonify({"success": False, "error": "missing_signature"}), 400

    issuer_did = (credential.get("issuer") or (credential.get("issuerInfo") or {}).get("did") or "").strip()
    issuer_pubkey_hex = ((credential.get("issuerInfo") or {}).get("publicKey") or "").strip()
    if not issuer_did:
        return jsonify({"success": False, "error": "missing_issuer"}), 400

    try:
        from api.trusted_issuers import is_trusted_issuer
        if not is_trusted_issuer(issuer_did):
            return jsonify({"success": False, "error": "untrusted_issuer"}), 403
    except Exception:
        logger.warning("Trust list check unavailable; proceeding with embedded pubkey")

    if not issuer_pubkey_hex and issuer_did.startswith("did:lemma:"):
        issuer_pubkey_hex = issuer_did.split(":", 2)[2]
    if not issuer_pubkey_hex:
        return jsonify({"success": False, "error": "issuer_pubkey_missing"}), 400

    try:
        pubkey_bytes = bytes.fromhex(issuer_pubkey_hex)
        signature_bytes = bytes.fromhex(sig_hex)
    except ValueError:
        return jsonify({"success": False, "error": "malformed_signature"}), 400

    try:
        message = _browser_canonical_message(credential)
        digest = hashlib.sha256(message).digest()
        Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(signature_bytes, digest)
    except InvalidSignature:
        return jsonify({"success": False, "error": "invalid_signature"}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": f"verify_error:{exc}"}), 400

    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    if not claims.get("isHuman"):
        return jsonify({"success": False, "error": "not_ishuman"}), 400
    bound_site = claims.get("siteId") or claims.get("site_id") or claims.get("siteDomain") or ""
    if expected_site_id and bound_site and bound_site != expected_site_id:
        return jsonify({"success": False, "error": "site_id_mismatch", "bound_site": bound_site}), 400

    try:
        expires_at = int(claims.get("expiresAt") or 0)
        if expires_at and expires_at < int(time.time()):
            return jsonify({"success": False, "error": "expired"}), 400
    except (TypeError, ValueError):
        pass

    credential_id = credential.get("id") or ""
    if credential_id:
        try:
            from api.revocation_verifier import is_credential_revoked
            if is_credential_revoked(credential_id):
                return jsonify({"success": False, "error": "revoked"}), 400
        except Exception as exc:  # noqa: BLE001
            logger.warning("Revocation check unavailable: %s", exc)

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
                return jsonify({
                    "success": False,
                    "error": session_reason,
                    "session_status": session_status,
                }), 400

    return jsonify({
        "success": True,
        "human": True,
        "ppid": credential.get("subject"),
        "credential_id": credential_id,
        "site_id": bound_site,
        "issuer": issuer_did,
        "session_status": session_status,
        "session_reason": session_reason,
    })


# ---------------------------------------------------------------------------
# 9. Approve network revocation (admin action)
# ---------------------------------------------------------------------------

@ishuman_bp.route("/api/ishuman/approve-revocation", methods=["POST"])
@cross_origin()
def approve_network_revocation():
    """Approve a network-wide revocation after evidence review.

    This is an **admin** action.  It:
    1. Marks the wallet as revoked (wallet-level kill via Bloom filter)
    2. Revokes the master credential
    3. Revokes ALL per-site derived credentials
    4. Publishes revocation events so the Bloom filter rebuilds

    Request body::

        {
            "wallet_id": "...",
            "master_credential_id": "ishuman_master_...",
            "reason": "Confirmed non-human activity"
        }
    """
    from auth.decorators import require_credential
    from api.authz_engine import extract_user_lemma_principal

    # Require admin credential for this action
    principal, error = extract_user_lemma_principal(request.headers)
    if not principal or not (
        principal.permission_id in ("admin_access", "super_admin")
        or "admin" in (principal.scope or [])
    ):
        return jsonify({"success": False, "error": "admin_required"}), 403

    body = request.get_json(silent=True) or {}
    wallet_id = body.get("wallet_id")
    master_credential_id = body.get("master_credential_id")
    reason = body.get("reason", "Network revocation approved after evidence review")

    if not wallet_id and not master_credential_id:
        return jsonify({"success": False, "error": "wallet_id or master_credential_id required"}), 400

    from api.database import SessionLocal
    db = SessionLocal()
    try:
        try:
            result = revoke_wallet_network_wide(
                db,
                wallet_id=wallet_id,
                master_credential_id=master_credential_id,
                reason=reason,
                revoked_by="admin",
            )
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        logger.info(
            "Network revocation approved: wallet=%s master_count=%d derived_count=%d total_revoked=%d",
            result["wallet_id"][:20], result["master_count"], result["derived_count"],
            len(result["revoked_credential_ids"]),
        )

        return jsonify({
            "success": True,
            "wallet_id": result["wallet_id"],
            "revoked_credential_ids": result["revoked_credential_ids"],
            "total_revoked": len(result["revoked_credential_ids"]),
        })

    except Exception:
        db.rollback()
        logger.exception("Failed to approve network revocation")
        return jsonify({"success": False, "error": "revocation_failed"}), 500
    finally:
        db.close()
