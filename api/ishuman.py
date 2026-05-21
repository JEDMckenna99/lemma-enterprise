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


def _issue_ishuman_credential(
    ppid: str,
    wallet_id: Optional[str] = None,
    site_id: Optional[str] = None,
    site_signing_pubkey: Optional[str] = None,
) -> dict:
    """Sign and return a new isHuman credential for *ppid*.

    If *site_id* is provided, the credential is bound to that site
    (per-site derived proof).  Otherwise it is the master proof bound
    to ``lemma.id``.
    """
    issuer = _get_ishuman_issuer()
    now = int(time.time())
    prefix = "ishuman_site" if site_id else "ishuman_master"
    credential_id = f"{prefix}_{secrets.token_urlsafe(24)}"

    claims: dict = {
        "isHuman": True,
        "verificationMethod": "stripe_identity",
        "packageType": "identity",
        "siteId": site_id or "lemma.id",
        "issuedAt": str(now),
        "expiresAt": str(now + ISHUMAN_CREDENTIAL_TTL_DAYS * 86400),
    }
    if site_signing_pubkey:
        claims["site_signing_pubkey"] = site_signing_pubkey

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
) -> str:
    """Derive PPID from wallet_secret + normalized site binding only."""
    from api.ppid import derive_ppid_from_wallet_secret

    if not wallet_secret:
        raise ValueError("wallet_secret required for canonical PPID derivation")
    return derive_ppid_from_wallet_secret(wallet_secret, rp_id)


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
        )
    except ValueError:
        return "ppid_derivation_failed"

    if is_credential_revoked(site_ppid):
        return "site_ppid_revoked"

    site = resolve_site_by_domain(db, target_site)
    if site and is_site_ppid_blocked(db, site_id=site.site_id, ppid=site_ppid):
        return "site_ppid_blocked"

    return None


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

    from billing.stripe_manager import StripeManager
    mgr = StripeManager()
    result = mgr.create_identity_verification_session(
        user_id=wallet_id,
        return_url=return_url,
    )

    if not result.get("success"):
        logger.error("Stripe Identity session creation failed: %s", result)
        return {"success": False, "error": result.get("error", "stripe_error")}, 502

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

        verification = IsHumanVerification(
            session_id=session_id,
            stripe_session_id=result["session_id"],
            wallet_id=wallet_id,
            ppid=derived_ppid,
            status="pending",
            metadata_json={"return_url": return_url},
        )
        db.add(verification)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist isHuman verification session")
        return {"success": False, "error": "verification_session_persist_failed"}, 500
    finally:
        db.close()

    logger.info("isHuman verification started: %s (stripe=%s)", session_id, result["session_id"])

    return {
        "success": True,
        "session_id": session_id,
        "stripe_session_id": result["session_id"],
        "client_secret": result["client_secret"],
        "url": result.get("url"),
    }, 200


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
            ppid = record.ppid or _derive_ppid_for_site(rp_id="lemma.id", wallet_id=wallet_id)

            credential = _issue_ishuman_credential(ppid, wallet_id)

            record.status = "verified"
            record.verified_at = datetime.utcnow()
            record.ppid = ppid
            record.credential_id = credential.get("id")
            record.issued_at = datetime.utcnow()
            record.expires_at = datetime.utcnow() + timedelta(days=ISHUMAN_CREDENTIAL_TTL_DAYS)
            record.metadata_json = {
                **(record.metadata_json or {}),
                "credential_issuer_did": credential.get("issuerInfo", {}).get("did"),
            }
            db.commit()

            logger.info(
                "isHuman credential issued: ppid=%s credential_id=%s",
                ppid[:40], credential.get("id"),
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
                credential = _issue_ishuman_credential(record.ppid, record.wallet_id)
                credential["id"] = record.credential_id
                resp["credential"] = credential
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
    master_credential_id = body.get("master_credential_id")
    wallet_id = body.get("wallet_id")
    wallet_secret = body.get("wallet_secret")
    target_site = body.get("target_site")
    site_signing_pubkey = (body.get("site_signing_pubkey") or "").strip()

    if not master_credential_id or not wallet_id or not target_site:
        return jsonify({
            "success": False,
            "error": "master_credential_id, wallet_id, and target_site required",
        }), 400

    if not wallet_secret:
        return jsonify({"success": False, "error": "wallet_secret required"}), 400

    err, _wid = _require_wallet_assertion(
        body,
        field_names=["master_credential_id", "target_site", "site_signing_pubkey"],
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
        # 1. Verify master credential is valid
        master = (
            db.query(IsHumanVerification)
            .filter_by(credential_id=master_credential_id, wallet_id=wallet_id, status="verified")
            .first()
        )
        if not master:
            return jsonify({"success": False, "error": "master_credential_not_found"}), 404

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

        deny_reason = _deny_if_derivation_revoked(
            db,
            master_credential_id=master_credential_id,
            wallet_id=wallet_id,
            wallet_secret=wallet_secret,
            target_site=target_site,
        )
        if deny_reason:
            return jsonify({"success": False, "error": deny_reason}), 403

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
            )
            credential = _issue_ishuman_credential(
                ppid,
                wallet_id,
                site_id=target_site,
                site_signing_pubkey=site_signing_pubkey or None,
            )
            credential["id"] = existing.derived_credential_id
            return jsonify({"success": True, "credential": credential, "cached": True})

        # 3. Derive site-specific PPID
        site_ppid = _derive_ppid_for_site(
            rp_id=target_site,
            wallet_secret=wallet_secret,
            wallet_id=wallet_id,
        )

        # 4. Issue per-site credential
        credential = _issue_ishuman_credential(
            site_ppid,
            wallet_id,
            site_id=target_site,
            site_signing_pubkey=site_signing_pubkey or None,
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

    from api.database import (
        SessionLocal, DerivedCredential, RevocationList, SiteBlock,
        IsHumanVerification,
    )
    db = SessionLocal()
    try:
        revoked_ids = []

        # Resolve wallet_id from master if only master_credential_id provided
        if not wallet_id and master_credential_id:
            master = db.query(IsHumanVerification).filter_by(
                credential_id=master_credential_id
            ).first()
            if master:
                wallet_id = master.wallet_id

        if not wallet_id:
            return jsonify({"success": False, "error": "could not resolve wallet_id"}), 400

        # Step 1: Wallet-level revocation (bridge enforcement)
        existing_wallet_revoke = (
            db.query(RevocationList)
            .filter_by(wallet_id=wallet_id, revocation_type="wallet")
            .first()
        )
        if not existing_wallet_revoke:
            wallet_revoke = RevocationList(
                lemma_id=f"wallet_revoke_{wallet_id[:32]}_{int(time.time())}",
                credential_id=None,
                lemma_type="ishuman",
                wallet_id=wallet_id,
                revocation_type="wallet",
                revoked_by="admin",
                reason=reason,
            )
            db.add(wallet_revoke)
            revoked_ids.append(wallet_id)

        # Step 2: Revoke master credential(s)
        masters = db.query(IsHumanVerification).filter_by(
            wallet_id=wallet_id, status="verified"
        ).all()
        for m in masters:
            if m.credential_id:
                master_revoke = RevocationList(
                    lemma_id=m.credential_id,
                    credential_id=m.credential_id,
                    lemma_type="ishuman",
                    revocation_type="credential",
                    revoked_by="admin",
                    reason=reason,
                )
                db.add(master_revoke)
                revoked_ids.append(m.credential_id)
                m.status = "revoked"

        # Step 3: Revoke ALL derived per-site credentials
        derived_rows = db.query(DerivedCredential).filter_by(
            wallet_id=wallet_id, is_active=True
        ).all()
        for d in derived_rows:
            derived_revoke = RevocationList(
                lemma_id=d.derived_credential_id,
                credential_id=d.derived_credential_id,
                lemma_type="ishuman",
                revocation_type="credential",
                revoked_by="admin",
                reason=reason,
            )
            db.add(derived_revoke)
            revoked_ids.append(d.derived_credential_id)
            d.is_active = False
            d.revoked_at = datetime.utcnow()

        # Step 4: Update any pending site-block network revocation requests
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

        # Step 5: Publish revocation event to rebuild Bloom filter
        try:
            from api.revocation_sync import get_event_bus
            bus = get_event_bus()
            for rid in revoked_ids:
                bus.publish_revocation(rid, reason=reason)
        except Exception as exc:
            logger.warning("Bloom sync publish failed (non-fatal): %s", exc)

        logger.info(
            "Network revocation approved: wallet=%s master_count=%d derived_count=%d total_revoked=%d",
            wallet_id[:20], len(masters), len(derived_rows), len(revoked_ids),
        )

        return jsonify({
            "success": True,
            "wallet_id": wallet_id,
            "revoked_credential_ids": revoked_ids,
            "total_revoked": len(revoked_ids),
        })

    except Exception:
        db.rollback()
        logger.exception("Failed to approve network revocation")
        return jsonify({"success": False, "error": "revocation_failed"}), 500
    finally:
        db.close()
