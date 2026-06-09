"""
Public isHuman demo orchestration.

This blueprint keeps the investor/customer demo thin: it reuses the production
isHuman APIs and data models, while wrapping demo site operations so API keys
and admin-only revocation controls are not exposed in browser JavaScript.
"""

from __future__ import annotations

import os
import secrets
import time
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request


ishuman_demo_bp = Blueprint("ishuman_demo", __name__)

DEMO_SITES = {
    "tickets": {
        "site_id": "site_demo_tickets",
        "site_domain": "tickets-demo.lemma.id",
        "company_name": "Ticketing Demo",
        "admin_email": "demo+tickets@lemma.id",
    },
    "trials": {
        "site_id": "site_demo_trials",
        "site_domain": "trials-demo.lemma.id",
        "company_name": "Free Trial Demo",
        "admin_email": "demo+trials@lemma.id",
    },
}


def _demo_api_key(site_id: str) -> str:
    env_name = f"LEMMA_ISHUMAN_DEMO_API_KEY_{site_id.upper()}"
    configured = os.getenv(env_name)
    if configured:
        return configured
    return f"lm_demo_{site_id}_{secrets.token_urlsafe(18)}"


def _demo_enabled() -> bool:
    """Single source of truth for whether demo affordances are active.

    Demo endpoints, demo tokens, and test-verify rails are enabled on every
    environment EXCEPT production. The intended v2 topology runs the demo on a
    dedicated staging app (``ENVIRONMENT=staging``) while ``lemma-enterprise``
    stays on ``ENVIRONMENT=production`` and serves real customers only.

    See docs/operations/ENVIRONMENT_CONFIG.md for the full env-var contract.
    """
    return os.getenv("ENVIRONMENT", "").strip().lower() != "production"


def ensure_demo_sites() -> list[dict]:
    """Create or refresh demo relying-site records."""
    from api.database import SessionLocal, Site

    db = SessionLocal()
    seeded: list[dict] = []
    try:
        for slug, spec in DEMO_SITES.items():
            site = db.query(Site).filter_by(site_id=spec["site_id"]).first()
            if not site:
                site = Site(
                    site_id=spec["site_id"],
                    site_domain=spec["site_domain"],
                    company_name=spec["company_name"],
                    admin_email=spec["admin_email"],
                    api_key=_demo_api_key(spec["site_id"]),
                    oauth_client_id=f"client_demo_{slug}",
                    oauth_client_secret=secrets.token_urlsafe(24),
                    plan="demo",
                )
                db.add(site)
            else:
                site.site_domain = spec["site_domain"]
                site.company_name = spec["company_name"]
                site.admin_email = spec["admin_email"]
                if not site.api_key:
                    site.api_key = _demo_api_key(spec["site_id"])
                if not site.oauth_client_id:
                    site.oauth_client_id = f"client_demo_{slug}"
                if not site.oauth_client_secret:
                    site.oauth_client_secret = secrets.token_urlsafe(24)
                site.plan = site.plan or "demo"

            seeded.append({
                "slug": slug,
                "site_id": spec["site_id"],
                "site_domain": spec["site_domain"],
                "company_name": spec["company_name"],
            })

        db.commit()
        return seeded
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _site_for_slug(slug: str):
    slug = (slug or "").strip().lower()
    spec = DEMO_SITES.get(slug)
    if not spec:
        return None, None

    ensure_demo_sites()
    from api.database import SessionLocal, Site

    db = SessionLocal()
    try:
        site = db.query(Site).filter_by(site_id=spec["site_id"]).first()
        return spec, site
    finally:
        db.close()


def _public_record(record) -> dict:
    if not record:
        return {}
    return {
        "session_id": record.session_id,
        "wallet_id": record.wallet_id,
        "ppid": record.ppid,
        "credential_id": record.credential_id,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "verified_at": record.verified_at.isoformat() if record.verified_at else None,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
    }


def _demo_page_context() -> dict:
    """Server-only demo tokens for /demo/ishuman (never exposed on other routes)."""
    demo_enabled = _demo_enabled()
    return {
        "demo_sites": list(DEMO_SITES.values()),
        "network_revoke_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")),
        "demo_test_verify_enabled": os.getenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "").lower() == "true",
        "demo_test_token_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN")),
        "demo_admin_token_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")),
        "demo_test_token": os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "") if demo_enabled else "",
        "demo_admin_token": os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN", "") if demo_enabled else "",
    }


@ishuman_demo_bp.route("/demo/ishuman")
def ishuman_demo_page():
    """Guided public demo for reusable proof-of-humanity."""
    return render_template("demo/ishuman.html", **_demo_page_context())


@ishuman_demo_bp.route("/wallet/ishuman-idv")
def ishuman_idv_popup():
    """Popup flow: unlock wallet + complete IDV when a customer site has no master proof."""
    ctx = _demo_page_context()
    return render_template(
        "wallet_ishuman_idv.html",
        demo_test_verify_enabled=ctx["demo_test_verify_enabled"],
        demo_test_token=ctx["demo_test_token"],
    ), 200, {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }


@ishuman_demo_bp.route("/api/demo/ishuman/config", methods=["GET"])
def ishuman_demo_config():
    sites = ensure_demo_sites()
    return jsonify({
        "success": True,
        "sites": sites,
        "stripe_demo_rail": True,
        "network_revoke_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")),
        "test_verify_enabled": os.getenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "").lower() == "true",
        "server_test_token_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN")),
        "server_admin_token_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")),
        "customer_site_urls": {
            "tickets": "https://lemma-demo-tickets-1d3d7411af33.herokuapp.com",
            "trials": "https://lemma-demo-trials-7090f46cae0d.herokuapp.com",
        },
        "copy": {
            "stripe_notice": (
                "This demo uses Stripe Identity as the prototype IDV rail. "
                "Commercial deployment requires an approved IDV-provider path."
            )
        },
    })


@ishuman_demo_bp.route("/api/demo/ishuman/status", methods=["GET"])
def ishuman_demo_status():
    from api.database import DerivedCredential, IsHumanVerification, SessionLocal, SiteBlock

    wallet_id = (request.args.get("wallet_id") or "").strip()
    master_credential_id = (request.args.get("master_credential_id") or "").strip()
    ensure_demo_sites()

    db = SessionLocal()
    try:
        master = None
        if master_credential_id:
            master = db.query(IsHumanVerification).filter_by(credential_id=master_credential_id).first()
        elif wallet_id:
            masters = (
                db.query(IsHumanVerification)
                .filter_by(wallet_id=wallet_id, status="verified")
                .all()
            )
            master = masters[-1] if masters else None

        derived_rows = []
        if master and master.credential_id:
            derived_rows = (
                db.query(DerivedCredential)
                .filter_by(master_credential_id=master.credential_id)
                .all()
            )

        site_blocks = []
        demo_site_ids = [spec["site_id"] for spec in DEMO_SITES.values()]
        for row in derived_rows:
            for block in db.query(SiteBlock).filter_by(ppid=row.derived_ppid, is_active=True).all():
                if block.site_id in demo_site_ids:
                    site_blocks.append({
                        "site_id": block.site_id,
                        "ppid": block.ppid,
                        "reason": block.reason,
                        "network_revocation_requested": block.network_revocation_requested,
                        "network_revocation_status": block.network_revocation_status,
                    })

        return jsonify({
            "success": True,
            "master": _public_record(master),
            "derived": [
                {
                    "master_credential_id": row.master_credential_id,
                    "derived_credential_id": row.derived_credential_id,
                    "target_site": row.target_site,
                    "derived_ppid": row.derived_ppid,
                    "is_active": row.is_active,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                }
                for row in derived_rows
            ],
            "site_blocks": site_blocks,
        })
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/site-block", methods=["POST"])
def ishuman_demo_site_block():
    from api.database import SessionLocal
    from api.site_ppid_revocation import revoke_site_bound_ppid

    body = request.get_json(silent=True) or {}
    slug = body.get("site_slug", "tickets")
    ppid = (body.get("ppid") or "").strip()
    reason = (body.get("reason") or "Demo site block: suspected automated activity").strip()
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    _spec, site = _site_for_slug(slug)
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    db = SessionLocal()
    try:
        from api.database import SiteBlock

        result = revoke_site_bound_ppid(
            db,
            site_id=site.site_id,
            ppid=ppid,
            reason=reason,
            revoked_by=site.admin_email or "demo",
            site_domain=site.site_domain,
            blocked_by=site.admin_email,
        )
        block = db.query(SiteBlock).filter_by(site_id=site.site_id, ppid=ppid, is_active=True).first()
        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "site_domain": site.site_domain,
            "ppid": ppid,
            "reason": getattr(block, "reason", reason),
            "blocked_at": block.blocked_at.isoformat() if block and block.blocked_at else None,
            "revocation_synced": result.get("event_published", False),
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/site-unblock", methods=["POST"])
def ishuman_demo_site_unblock():
    from api.database import SessionLocal, SiteBlock

    body = request.get_json(silent=True) or {}
    slug = body.get("site_slug", "tickets")
    ppid = (body.get("ppid") or "").strip()
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    _spec, site = _site_for_slug(slug)
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    db = SessionLocal()
    try:
        block = db.query(SiteBlock).filter_by(site_id=site.site_id, ppid=ppid, is_active=True).first()
        if not block:
            return jsonify({"success": True, "unblocked": False})
        block.is_active = False
        db.commit()
        return jsonify({"success": True, "unblocked": True, "site_id": site.site_id, "ppid": ppid})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/network-revoke-request", methods=["POST"])
def ishuman_demo_network_revoke_request():
    from api.database import SessionLocal
    from api.site_ppid_revocation import revoke_site_bound_ppid

    body = request.get_json(silent=True) or {}
    slug = body.get("site_slug", "tickets")
    ppid = (body.get("ppid") or "").strip()
    reason = (body.get("reason") or "Demo evidence package: repeated automated activity").strip()
    evidence_url = (body.get("evidence_url") or "https://lemma.id/demo/ishuman#evidence").strip()
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    _spec, site = _site_for_slug(slug)
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    db = SessionLocal()
    try:
        revoke_site_bound_ppid(
            db,
            site_id=site.site_id,
            ppid=ppid,
            reason=reason,
            revoked_by=site.admin_email or "demo",
            site_domain=site.site_domain,
            blocked_by=site.admin_email,
            evidence_url=evidence_url,
            network_revocation_requested=True,
            network_revocation_status="pending_review",
        )
        return jsonify({
            "success": True,
            "status": "pending_review",
            "site_block_active": True,
            "site_id": site.site_id,
            "ppid": ppid,
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _require_demo_test_verify(*, require_token_header: bool = True) -> tuple[dict | None, tuple | None]:
    """Return (None, error_response) when test-verify guards pass."""
    if not _demo_enabled():
        return None, (jsonify({"success": False, "error": "prod_test_verify_forbidden"}), 403)
    if os.getenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "").lower() != "true":
        return None, (jsonify({"success": False, "error": "test_verify_disabled"}), 403)
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not stripe_key.startswith("sk_test_"):
        return None, (jsonify({"success": False, "error": "stripe_test_key_required"}), 403)
    if require_token_header:
        expected = os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN")
        provided = request.headers.get("X-Demo-Test-Token") or ""
        if not expected or provided != expected:
            return None, (jsonify({"success": False, "error": "demo_test_token_required"}), 403)
    return {}, None


def _complete_demo_test_session(
    *,
    session_id: str = "",
    stripe_session_id: str = "",
    wallet_secret: str = "",
) -> tuple[dict, int]:
    """Shared test-complete logic for demo endpoints."""
    from api.database import IsHumanVerification, SessionLocal
    from api.ishuman import _derive_ppid_for_site, _issue_ishuman_credential
    from api.identity_person import material_from_test_fixture, resolve_or_create_person_from_material
    from api.ppid import derive_ppid_from_person_root_hash

    if not session_id and not stripe_session_id:
        return {"success": False, "error": "session_id or stripe_session_id required"}, 400

    db = SessionLocal()
    try:
        query = db.query(IsHumanVerification)
        record = (
            query.filter_by(session_id=session_id).first()
            if session_id
            else query.filter_by(stripe_session_id=stripe_session_id).first()
        )
        if not record:
            return {"success": False, "error": "session_not_found"}, 404

        wallet_id = record.wallet_id
        if not wallet_id:
            return {"success": False, "error": "wallet_id_missing"}, 400

        secret = (wallet_secret or "").strip() or os.getenv("LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET", "")
        ppid = None
        ppid_derivation = None
        if record.ppid:
            ppid = record.ppid
            ppid_derivation = (record.metadata_json or {}).get("ppid_derivation") or (
                "person_root_v1" if record.lemma_person_id else None
            )
        else:
            material = material_from_test_fixture(
                stripe_session_id=record.stripe_session_id,
                document_number=f"demo_{wallet_id[-8:]}",
            )
            resolved = resolve_or_create_person_from_material(db, material=material, wallet_id=wallet_id)
            ppid = derive_ppid_from_person_root_hash(resolved.person_root_hash, "lemma.id")
            from api.column_crypto import encrypt_column

            record.lemma_person_id = resolved.person_id
            record.document_root_hash = encrypt_column(resolved.document_root_hash)
            record.root_version = "v1"
            record.confidence_level = resolved.confidence_level
            ppid_derivation = "person_root_v1"
        if ppid is None and secret:
            ppid = _derive_ppid_for_site(
                rp_id="lemma.id",
                wallet_secret=secret,
                wallet_id=wallet_id,
                provisional=True,
            )
        if ppid is None:
            return {"success": False, "error": "ppid_derivation_failed"}, 500
        credential = _issue_ishuman_credential(
            ppid,
            wallet_id,
            ppid_derivation=ppid_derivation,
        )

        record.status = "verified"
        record.verified_at = datetime.utcnow()
        record.ppid = ppid
        record.credential_id = credential.get("id")
        record.issued_at = datetime.utcnow()
        record.expires_at = datetime.utcfromtimestamp(
            int((credential.get("claims") or {}).get("expiresAt", int(time.time())))
        )
        record.metadata_json = {
            **(record.metadata_json or {}),
            "credential_issuer_did": credential.get("issuerInfo", {}).get("did"),
            "demo_test_completed": True,
            "ppid_derivation": ppid_derivation or (record.metadata_json or {}).get("ppid_derivation"),
        }
        db.commit()

        return {
            "success": True,
            "session_id": record.session_id,
            "stripe_session_id": record.stripe_session_id,
            "credential_id": record.credential_id,
            "ppid": record.ppid,
            "credential": credential,
            "mode": "stripe_test_demo_completion",
        }, 200
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/test-complete-verification", methods=["POST"])
def ishuman_demo_test_complete_verification():
    """Complete a Stripe test-mode isHuman session for automated demos.

    This does not run in normal production mode. It requires:
    - LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true
    - STRIPE_SECRET_KEY beginning with sk_test_
    - X-Demo-Test-Token matching LEMMA_ISHUMAN_DEMO_TEST_TOKEN

    The endpoint intentionally lives under the demo namespace and mirrors the
    verified webhook state transition so test-mode demos can run end-to-end
    without manual document upload.
    """
    _guards, err = _require_demo_test_verify()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    stripe_session_id = (body.get("stripe_session_id") or "").strip()
    wallet_secret = (body.get("wallet_secret") or "").strip()
    payload, status = _complete_demo_test_session(
        session_id=session_id,
        stripe_session_id=stripe_session_id,
        wallet_secret=wallet_secret,
    )
    return jsonify(payload), status


def _clear_wallet_revocations_for_demo(
    db,
    *,
    wallet_id: str,
    new_master_credential_id: str,
    reason: str = "demo_fresh_idv_reset",
) -> dict:
    """Demo-only thin wrapper preserved for backward compatibility.

    Delegates to the shared production helper now used by both the Stripe
    Identity webhook and the demo test-mode IDV endpoint.
    """
    from api.site_ppid_revocation import clear_amnesty_eligible_wallet_revocations
    return clear_amnesty_eligible_wallet_revocations(
        db,
        wallet_id=wallet_id,
        new_master_credential_id=new_master_credential_id,
        reason=reason,
    )


@ishuman_demo_bp.route("/api/demo/ishuman/verify-once-test-mode", methods=["POST"])
def ishuman_demo_verify_once_test_mode():
    """Chain start-verification + test-complete using server-side demo token only.

    In demo, this is also the entry point for the "fresh IDV" re-entry flow
    after a revocation. When the request includes ``reset_revocations: true``
    the endpoint additionally clears any prior wallet-level revocations and
    site blocks for the wallet, so the user can rejoin sites that previously
    blocked them. Production would gate the reset behind governance.
    """
    _guards, err = _require_demo_test_verify(require_token_header=True)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip() or os.getenv("LEMMA_ISHUMAN_PROD_TEST_WALLET_ID", "")
    wallet_secret = (body.get("wallet_secret") or "").strip() or os.getenv(
        "LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET", ""
    )
    return_url = (body.get("return_url") or "").strip()
    reset_revocations = bool(body.get("reset_revocations", True))

    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    from api.ishuman import start_verification_for_body

    start_body = dict(body)
    start_body.setdefault("wallet_id", wallet_id)
    if wallet_secret and not start_body.get("ppid"):
        from api.ppid import derive_ppid_from_wallet_secret

        start_body["ppid"] = derive_ppid_from_wallet_secret(wallet_secret, "lemma.id")
    start_body.pop("wallet_secret", None)
    if return_url:
        start_body["return_url"] = return_url
    start_payload, start_status = start_verification_for_body(start_body)
    if start_status != 200:
        return jsonify(start_payload), start_status

    complete_payload, complete_status = _complete_demo_test_session(
        session_id=start_payload["session_id"],
        wallet_secret=wallet_secret,
    )
    if complete_status != 200:
        return jsonify(complete_payload), complete_status

    reset_summary = None
    if reset_revocations:
        from api.database import SessionLocal
        db = SessionLocal()
        try:
            reset_summary = _clear_wallet_revocations_for_demo(
                db,
                wallet_id=wallet_id,
                new_master_credential_id=complete_payload["credential_id"],
                reason="demo_fresh_idv_reset",
            )
        except Exception:
            db.rollback()
            logger.exception("Demo revocation reset failed")
        finally:
            db.close()

    return jsonify({
        "success": True,
        "session_id": complete_payload["session_id"],
        "credential_id": complete_payload["credential_id"],
        "credential": complete_payload["credential"],
        "ppid": complete_payload["ppid"],
        "stripe_session_id": complete_payload.get("stripe_session_id"),
        "mode": "verify_once_test_mode",
        "revocation_reset": reset_summary,
    })


@ishuman_demo_bp.route("/api/demo/ishuman/probe-derive", methods=["POST"])
def ishuman_demo_probe_derive():
    """Server-side derive probe — proves enforcement is not UI-only."""
    from api.database import IsHumanVerification, SessionLocal
    from api.ishuman import _deny_if_derivation_revoked, _require_wallet_assertion

    body = request.get_json(silent=True) or {}
    err, _wid = _require_wallet_assertion(
        body,
        field_names=["site_slug", "master_credential_id"],
    )
    if err:
        return err

    slug = (body.get("site_slug") or "tickets").strip().lower()
    spec, site = _site_for_slug(slug)
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    wallet_id = (body.get("wallet_id") or "").strip() or os.getenv("LEMMA_ISHUMAN_PROD_TEST_WALLET_ID", "")
    wallet_secret = (body.get("wallet_secret") or "").strip() or os.getenv(
        "LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET", ""
    )
    master_credential_id = (body.get("master_credential_id") or "").strip() or os.getenv(
        "LEMMA_ISHUMAN_PROD_TEST_MASTER_CREDENTIAL_ID", ""
    )

    if not wallet_id or not master_credential_id:
        return jsonify({
            "success": False,
            "error": "wallet_id and master_credential_id required (or set prod test env)",
        }), 400

    target_site = spec["site_domain"]
    db = SessionLocal()
    try:
        master = (
            db.query(IsHumanVerification)
            .filter_by(credential_id=master_credential_id, wallet_id=wallet_id, status="verified")
            .first()
        )
        if not master:
            return jsonify({
                "success": True,
                "allowed": False,
                "http_status": 404,
                "error": "master_credential_not_found",
            })

        deny_reason = _deny_if_derivation_revoked(
            db,
            master_credential_id=master_credential_id,
            wallet_id=wallet_id,
            wallet_secret=wallet_secret or None,
            target_site=target_site,
        )
        if deny_reason:
            return jsonify({
                "success": True,
                "allowed": False,
                "http_status": 403,
                "error": deny_reason,
                "site_domain": target_site,
            })

        return jsonify({
            "success": True,
            "allowed": True,
            "http_status": 200,
            "error": None,
            "site_domain": target_site,
        })
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/force-reverify", methods=["POST"])
def ishuman_demo_force_reverify():
    """Demo-only: block ticketing PPID and clear derived credential for fresh IDV."""
    from api.database import DerivedCredential, SessionLocal
    from api.ishuman import _require_wallet_assertion
    from api.site_ppid_revocation import revoke_site_bound_ppid

    body = request.get_json(silent=True) or {}
    err, _wid = _require_wallet_assertion(
        body,
        field_names=["ppid", "master_credential_id"],
    )
    if err:
        return err

    ppid = (body.get("ppid") or "").strip()
    master_credential_id = (body.get("master_credential_id") or "").strip()
    wallet_id = (body.get("wallet_id") or "").strip()

    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    _spec, site = _site_for_slug("tickets")
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    db = SessionLocal()
    try:
        result = revoke_site_bound_ppid(
            db,
            site_id=site.site_id,
            ppid=ppid,
            reason=(body.get("reason") or "Demo: force fresh IDV on ticketing").strip(),
            revoked_by=site.admin_email or "demo",
            site_domain=site.site_domain,
            blocked_by=site.admin_email,
        )

        cleared_derived_ids = []
        if master_credential_id:
            derived_rows = (
                db.query(DerivedCredential)
                .filter_by(
                    master_credential_id=master_credential_id,
                    target_site=site.site_domain,
                    is_active=True,
                )
                .all()
            )
            for row in derived_rows:
                row.is_active = False
                row.revoked_at = datetime.utcnow()
                cleared_derived_ids.append(row.derived_credential_id)
            db.commit()

        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "site_domain": site.site_domain,
            "ppid": ppid,
            "revocation_synced": result.get("event_published", False),
            "cleared_derived_credential_ids": cleared_derived_ids,
            "reverify_required": True,
            "wallet_id": wallet_id,
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/self-reset", methods=["POST"])
def ishuman_demo_self_reset():
    """A wallet owner clears their OWN amnesty-eligible revocation state.

    Auth: a fresh wallet_assertion proving possession of the wallet's signing
    key. No admin / demo token required.

    Policy rationale:
      Revocation is not meant to permanently bar real humans who were wrongly
      flagged. The economic deterrent against repeat abuse is the cost of
      fresh IDV ($1-3 + a real document) plus the audit trail every fresh
      verification leaves under the same person_root. Allowing a wallet owner
      to clear their own amnesty-eligible revocations is therefore safe in
      production — they still have to complete a real IDV (or pay the IDV
      cost) on the next issuance, and the network sees each attempt.

    What still requires governance:
      Wallet-level kills approved by Lemma.id governance for confirmed
      coordinated fraud are stored as RevocationList rows with
      revocation_type='wallet' AND are_amnesty_eligible=False (or similar).
      Those stay sticky until the network explicitly reinstates the wallet.
      The helper `_clear_wallet_revocations_for_demo` currently clears every
      row for the wallet; a production hardening pass will filter on an
      amnesty flag so governance-locked rows survive.
    """
    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    from api.ishuman import _require_wallet_assertion
    err, _wid = _require_wallet_assertion(body, field_names=["wallet_id"])
    if err:
        return err

    from api.database import SessionLocal, IsHumanVerification

    db = SessionLocal()
    try:
        latest_master = (
            db.query(IsHumanVerification)
            .filter_by(wallet_id=wallet_id, status="verified")
            .order_by(IsHumanVerification.verified_at.desc())
            .first()
        )
        latest_master_id = latest_master.credential_id if latest_master else ""
        summary = _clear_wallet_revocations_for_demo(
            db,
            wallet_id=wallet_id,
            new_master_credential_id=latest_master_id,
            reason="demo_self_reset",
        )
        return jsonify({"success": True, **summary})
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Demo self-reset failed for %s", wallet_id)
        return jsonify({"success": False, "error": f"reset_failed:{exc}"}), 500
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/reset-wallet", methods=["POST"])
def ishuman_demo_reset_wallet():
    """Demo-only manual escape hatch: clear all revocation state for a wallet
    without requiring a fresh IDV cycle. Lets a demo operator unstick the
    system when the popup loop didn't reach `_clear_wallet_revocations_for_demo`
    cleanly.

    Token-gated by LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN (X-Demo-Admin-Token). Returns
    counts of rows cleared so the caller can confirm the reset landed.
    """
    expected = os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")
    provided = request.headers.get("X-Demo-Admin-Token") or ""
    if not expected or provided != expected:
        return jsonify({
            "success": False,
            "error": "demo_admin_token_required",
            "message": "Set LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN and pass X-Demo-Admin-Token.",
        }), 403

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    from api.database import SessionLocal, IsHumanVerification

    db = SessionLocal()
    try:
        latest_master = (
            db.query(IsHumanVerification)
            .filter_by(wallet_id=wallet_id, status="verified")
            .order_by(IsHumanVerification.verified_at.desc())
            .first()
        )
        latest_master_id = latest_master.credential_id if latest_master else ""
        summary = _clear_wallet_revocations_for_demo(
            db,
            wallet_id=wallet_id,
            new_master_credential_id=latest_master_id,
            reason="demo_manual_reset",
        )
        return jsonify({"success": True, **summary})
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Demo reset-wallet failed for %s", wallet_id)
        return jsonify({"success": False, "error": f"reset_failed:{exc}"}), 500
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/approve-network-revocation", methods=["POST"])
def ishuman_demo_approve_network_revocation():
    """Token-gated demo-only network revocation drill."""
    expected = os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")
    provided = request.headers.get("X-Demo-Admin-Token") or ""
    if not expected or provided != expected:
        return jsonify({
            "success": False,
            "error": "demo_admin_token_required",
            "message": "Set LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN and pass X-Demo-Admin-Token to run the live revocation drill.",
        }), 403

    from api.database import DerivedCredential, IsHumanVerification, RevocationList, SessionLocal, SiteBlock

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    master_credential_id = (body.get("master_credential_id") or "").strip()
    reason = (body.get("reason") or "Demo network revocation approved").strip()
    if not wallet_id and not master_credential_id:
        return jsonify({"success": False, "error": "wallet_id or master_credential_id required"}), 400

    db = SessionLocal()
    try:
        if not wallet_id and master_credential_id:
            master = db.query(IsHumanVerification).filter_by(credential_id=master_credential_id).first()
            wallet_id = master.wallet_id if master else ""
        if not wallet_id:
            return jsonify({"success": False, "error": "could not resolve wallet_id"}), 400

        revoked_ids = []
        # Governance-approved coordinated-fraud kill: mark every row sticky
        # (is_amnesty_eligible=False) so a subsequent fresh IDV cannot self-lift
        # it. Ordinary site self-blocks stay eligible (default True).
        existing_wallet_revoke = db.query(RevocationList).filter_by(wallet_id=wallet_id, revocation_type="wallet").first()
        if not existing_wallet_revoke:
            db.add(RevocationList(
                lemma_id=f"wallet_revoke_demo_{wallet_id[:32]}_{int(time.time())}",
                credential_id=None,
                lemma_type="ishuman",
                wallet_id=wallet_id,
                revocation_type="wallet",
                revoked_by="demo_admin",
                reason=reason,
                is_amnesty_eligible=False,
            ))
            revoked_ids.append(wallet_id)
        elif existing_wallet_revoke.is_amnesty_eligible is not False:
            existing_wallet_revoke.is_amnesty_eligible = False

        masters = db.query(IsHumanVerification).filter_by(wallet_id=wallet_id, status="verified").all()
        for master in masters:
            if master.credential_id:
                db.add(RevocationList(
                    lemma_id=master.credential_id,
                    credential_id=master.credential_id,
                    lemma_type="ishuman",
                    revocation_type="credential",
                    revoked_by="demo_admin",
                    reason=reason,
                    is_amnesty_eligible=False,
                ))
                revoked_ids.append(master.credential_id)
                master.status = "revoked"

        derived_rows = db.query(DerivedCredential).filter_by(wallet_id=wallet_id, is_active=True).all()
        for row in derived_rows:
            db.add(RevocationList(
                lemma_id=row.derived_credential_id,
                credential_id=row.derived_credential_id,
                lemma_type="ishuman",
                revocation_type="credential",
                revoked_by="demo_admin",
                reason=reason,
                is_amnesty_eligible=False,
            ))
            revoked_ids.append(row.derived_credential_id)
            row.is_active = False
            row.revoked_at = datetime.utcnow()

        demo_site_ids = [spec["site_id"] for spec in DEMO_SITES.values()]
        demo_ppids = [row.derived_ppid for row in derived_rows]
        for block in db.query(SiteBlock).filter_by(network_revocation_status="pending_review").all():
            if block.site_id in demo_site_ids and block.ppid in demo_ppids:
                block.network_revocation_status = "approved"
                block.is_amnesty_eligible = False

        db.commit()

        try:
            from api.revocation_sync import get_event_bus
            bus = get_event_bus()
            for revoked_id in revoked_ids:
                bus.publish_revocation(revoked_id, reason=reason)
        except Exception:
            pass

        return jsonify({
            "success": True,
            "wallet_id": wallet_id,
            "revoked_credential_ids": revoked_ids,
            "total_revoked": len(revoked_ids),
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
