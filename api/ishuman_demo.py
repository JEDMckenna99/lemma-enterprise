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


@ishuman_demo_bp.route("/demo/ishuman")
def ishuman_demo_page():
    """Guided public demo for reusable proof-of-humanity."""
    return render_template(
        "demo/ishuman.html",
        demo_sites=list(DEMO_SITES.values()),
        network_revoke_configured=bool(os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")),
    )


@ishuman_demo_bp.route("/api/demo/ishuman/config", methods=["GET"])
def ishuman_demo_config():
    sites = ensure_demo_sites()
    return jsonify({
        "success": True,
        "sites": sites,
        "stripe_demo_rail": True,
        "network_revoke_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")),
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
    if os.getenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "").lower() != "true":
        return jsonify({"success": False, "error": "test_verify_disabled"}), 403

    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not stripe_key.startswith("sk_test_"):
        return jsonify({"success": False, "error": "stripe_test_key_required"}), 403

    expected = os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN")
    provided = request.headers.get("X-Demo-Test-Token") or ""
    if not expected or provided != expected:
        return jsonify({"success": False, "error": "demo_test_token_required"}), 403

    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    stripe_session_id = (body.get("stripe_session_id") or "").strip()
    if not session_id and not stripe_session_id:
        return jsonify({"success": False, "error": "session_id or stripe_session_id required"}), 400

    from api.database import IsHumanVerification, SessionLocal
    from api.ishuman import _derive_ppid_for_site, _issue_ishuman_credential

    db = SessionLocal()
    try:
        query = db.query(IsHumanVerification)
        record = (
            query.filter_by(session_id=session_id).first()
            if session_id
            else query.filter_by(stripe_session_id=stripe_session_id).first()
        )
        if not record:
            return jsonify({"success": False, "error": "session_not_found"}), 404

        wallet_id = record.wallet_id
        if not wallet_id:
            return jsonify({"success": False, "error": "wallet_id_missing"}), 400

        wallet_secret = (body.get("wallet_secret") or "").strip() or os.getenv(
            "LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET", ""
        )
        if record.ppid:
            ppid = record.ppid
        elif wallet_secret:
            ppid = _derive_ppid_for_site(
                rp_id="lemma.id",
                wallet_secret=wallet_secret,
                wallet_id=wallet_id,
            )
        else:
            ppid = _derive_ppid_for_site(rp_id="lemma.id", wallet_id=wallet_id)
        credential = _issue_ishuman_credential(ppid, wallet_id)

        record.status = "verified"
        record.verified_at = datetime.utcnow()
        record.ppid = ppid
        record.credential_id = credential.get("id")
        record.issued_at = datetime.utcnow()
        record.expires_at = datetime.utcfromtimestamp(int((credential.get("claims") or {}).get("expiresAt", int(time.time()))))
        record.metadata_json = {
            **(record.metadata_json or {}),
            "credential_issuer_did": credential.get("issuerInfo", {}).get("did"),
            "demo_test_completed": True,
        }
        db.commit()

        return jsonify({
            "success": True,
            "session_id": record.session_id,
            "stripe_session_id": record.stripe_session_id,
            "credential_id": record.credential_id,
            "ppid": record.ppid,
            "credential": credential,
            "mode": "stripe_test_demo_completion",
        })
    except Exception:
        db.rollback()
        raise
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
            ))
            revoked_ids.append(wallet_id)

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
            ))
            revoked_ids.append(row.derived_credential_id)
            row.is_active = False
            row.revoked_at = datetime.utcnow()

        demo_site_ids = [spec["site_id"] for spec in DEMO_SITES.values()]
        demo_ppids = [row.derived_ppid for row in derived_rows]
        for block in db.query(SiteBlock).filter_by(network_revocation_status="pending_review").all():
            if block.site_id in demo_site_ids and block.ppid in demo_ppids:
                block.network_revocation_status = "approved"

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
