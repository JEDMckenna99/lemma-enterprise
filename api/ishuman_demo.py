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
import logging
from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request

logger = logging.getLogger(__name__)


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
                    oauth_client_id=f"client_demo_{slug}",
                    oauth_client_secret=secrets.token_urlsafe(24),
                    plan="demo",
                )
                db.add(site)
            else:
                site.site_domain = spec["site_domain"]
                site.company_name = spec["company_name"]
                site.admin_email = spec["admin_email"]
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


def _assurance_demo_config() -> dict:
    from api.config import one_ppid_assurance_model_enabled, passkey_assurance_enabled

    one_ppid = one_ppid_assurance_model_enabled()
    passkey = passkey_assurance_enabled()
    return {
        "one_ppid_enabled": one_ppid,
        "passkey_assurance_enabled": passkey,
        "assurance_demo_mode": one_ppid and passkey,
        "default_site_assurance": "passkey",
    }


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


def _demo_exposes_test_token() -> bool:
    # SECURITY: never embed the demo test token in a production page. In
    # production the token is the ONLY guard on no-IDV credential minting
    # (/api/demo/ishuman/qr-demo-idv-flow and the skeleton/test-verify rails).
    # Rendering it into the public /demo/ishuman page let any visitor read it
    # and mint real, network-trusted "verified human" master credentials with
    # no IDV (and unlimited synthetic person-roots). Operators running the
    # public QR demo on production must paste the token via the in-page override
    # field; it is auto-exposed only on non-production deploys.
    return _demo_enabled()


def _demo_page_context() -> dict:
    """Server-only demo tokens for /demo/ishuman (never exposed on other routes)."""
    from api.config import (
        is_ishuman_demo_qr_idv_enabled,
        is_ishuman_skeleton_idv_enabled,
    )

    demo_enabled = _demo_enabled()
    expose_token = _demo_exposes_test_token()
    return {
        "demo_sites": list(DEMO_SITES.values()),
        "demo_test_verify_enabled": (
            demo_enabled
            and os.getenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "").lower() == "true"
        ),
        "demo_test_token_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN")),
        "demo_admin_token_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")),
        "demo_test_token": os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "") if expose_token else "",
        "demo_admin_token": os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN", "") if demo_enabled else "",
        "skeleton_idv_enabled": demo_enabled and is_ishuman_skeleton_idv_enabled(),
        "qr_demo_idv_enabled": is_ishuman_demo_qr_idv_enabled(),
    }


@ishuman_demo_bp.route("/demo")
def lemma_demo_page():
    """Canonical public demo for lemma.id proof-of-humanity integration."""
    return render_template("demo/lemma.html", **_demo_page_context())


@ishuman_demo_bp.route("/demo/ishuman")
def ishuman_demo_page_legacy_redirect():
    """Legacy URL, isHuman is an assurance tier inside the lemma.id demo, not the demo itself."""
    return redirect("/demo", code=301)


@ishuman_demo_bp.route("/wallet/ishuman-idv")
def ishuman_idv_popup():
    """Popup flow: unlock wallet + complete IDV when a customer site has no master proof."""
    from api.config import one_ppid_assurance_model_enabled, passkey_assurance_enabled

    ctx = _demo_page_context()
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if request.args.get("preview_type"):
        # The design-QA gallery embeds only inert preview-mode renders. Keep the
        # live ceremony unframeable while allowing these same-origin previews.
        headers["X-Frame-Options"] = "SAMEORIGIN"
    return render_template(
        "wallet_ishuman_idv.html",
        demo_test_verify_enabled=ctx["demo_test_verify_enabled"],
        demo_test_token=ctx["demo_test_token"],
        skeleton_idv_enabled=ctx["skeleton_idv_enabled"],
        qr_demo_idv_enabled=ctx["qr_demo_idv_enabled"],
        passkey_assurance_enabled=(
            passkey_assurance_enabled()
            or one_ppid_assurance_model_enabled()
            or _demo_enabled()
        ),
    ), 200, headers


@ishuman_demo_bp.route("/demo/ishuman/ui-states")
def ishuman_ui_states_page():
    """Design-QA gallery for every production popup and redirect state."""
    return render_template("ishuman_ui_states.html"), 200, {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }


@ishuman_demo_bp.route("/api/demo/ishuman/config", methods=["GET"])
def ishuman_demo_config():
    from api.config import (
        is_ishuman_demo_qr_idv_enabled,
        is_ishuman_skeleton_idv_enabled,
        ishuman_demo_qr_credential_ttl_seconds,
    )

    sites = ensure_demo_sites()
    return jsonify({
        "success": True,
        "sites": sites,
        "stripe_demo_rail": True,
        "test_verify_enabled": (
            _demo_enabled()
            and os.getenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "").lower() == "true"
        ),
        "server_test_token_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN")),
        "server_admin_token_configured": bool(os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")),
        "skeleton_idv_enabled": _demo_enabled() and is_ishuman_skeleton_idv_enabled(),
        "qr_demo_idv_enabled": is_ishuman_demo_qr_idv_enabled(),
        "demo_qr_credential_ttl_seconds": ishuman_demo_qr_credential_ttl_seconds(),
        "customer_site_urls": {
            "tickets": os.getenv(
                "LEMMA_DEMO_TICKETS_URL",
                "https://lemma-demo-tickets-1d3d7411af33.herokuapp.com",
            ),
            "trials": os.getenv(
                "LEMMA_DEMO_TRIALS_URL",
                "https://lemma-demo-trials-7090f46cae0d.herokuapp.com",
            ),
        },
        **_assurance_demo_config(),
        "copy": {
            "stripe_notice": (
                "This demo uses Stripe Identity as the prototype IDV rail. "
                "Commercial deployment requires an approved IDV-provider path."
            )
        },
    })


@ishuman_demo_bp.route("/api/demo/ishuman/relying-site-preflight", methods=["GET"])
def ishuman_demo_relying_site_preflight():
    """Server-side health check for deployed relying-site demo apps."""
    import json
    import urllib.error
    import urllib.request

    site_urls = {
        "tickets": os.getenv(
            "LEMMA_DEMO_TICKETS_URL",
            "https://lemma-demo-tickets-1d3d7411af33.herokuapp.com",
        ),
        "trials": os.getenv(
            "LEMMA_DEMO_TRIALS_URL",
            "https://lemma-demo-trials-7090f46cae0d.herokuapp.com",
        ),
    }

    results: dict[str, dict] = {}
    for slug, base_url in site_urls.items():
        health_url = f"{base_url.rstrip('/')}/health"
        config_url = f"{base_url.rstrip('/')}/api/demo/config"
        entry = {"base_url": base_url, "success": False}
        try:
            with urllib.request.urlopen(health_url, timeout=8) as resp:
                health = json.loads(resp.read().decode("utf-8"))
            entry["health"] = health
            entry["site_id"] = health.get("site_id")
            with urllib.request.urlopen(config_url, timeout=8) as resp:
                config = json.loads(resp.read().decode("utf-8"))
            entry["config"] = config
            entry["success"] = bool(health.get("success") and config.get("success"))
        except urllib.error.URLError as exc:
            entry["error"] = str(exc.reason or exc)
        except Exception as exc:
            entry["error"] = str(exc)
        results[slug] = entry

    all_ok = all(row.get("success") for row in results.values())
    return jsonify({"success": all_ok, "sites": results})


@ishuman_demo_bp.route("/api/demo/ishuman/assurance-status", methods=["GET"])
def ishuman_demo_assurance_status():
    """Whether a wallet's person root is provisional (passkey-only) or IDV-anchored."""
    from api.database import LemmaDocumentRoot, LemmaPerson, LemmaWalletBinding, SessionLocal
    from api.identity_person import PERSON_STATUS_ACTIVE, PERSON_STATUS_PROVISIONAL

    wallet_id = (request.args.get("wallet_id") or "").strip()
    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    db = SessionLocal()
    try:
        binding = (
            db.query(LemmaWalletBinding)
            .filter_by(wallet_id=wallet_id, binding_status="active")
            .first()
        )
        if not binding:
            return jsonify({
                "success": True,
                "wallet_id": wallet_id,
                "person_bound": False,
                "person_status": None,
                "provisional": False,
                "anchored": False,
                "has_document_link": False,
            })

        person = db.query(LemmaPerson).filter_by(person_id=binding.lemma_person_id).first()
        doc = (
            db.query(LemmaDocumentRoot)
            .filter_by(lemma_person_id=binding.lemma_person_id)
            .filter(LemmaDocumentRoot.revoked_at.is_(None))
            .first()
        )
        status = (person.status if person else None) or ""
        has_doc = doc is not None
        provisional = status == PERSON_STATUS_PROVISIONAL
        anchored = status == PERSON_STATUS_ACTIVE and has_doc

        return jsonify({
            "success": True,
            "wallet_id": wallet_id,
            "person_bound": True,
            "person_id": binding.lemma_person_id,
            "person_status": status,
            "provisional": provisional,
            "anchored": anchored,
            "has_document_link": has_doc,
        })
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/require-ishuman", methods=["POST"])
def ishuman_demo_require_ishuman():
    """Demo-only admin path: legacy SiteDoubt row (not policy escalation).

    Main demo flow uses client-side ``requiredAssurance`` policy toggles for
    escalation and ``/api/demo/ishuman/site-doubt`` for temporary doubt.
    """
    from api.database import SessionLocal, SiteDoubt

    _guards, err = _require_demo_admin_token()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    slug = (body.get("site_slug") or "tickets").strip()
    ppid = (body.get("ppid") or "").strip()
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    _spec, site = _site_for_slug(slug)
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    db = SessionLocal()
    try:
        doubt = db.query(SiteDoubt).filter_by(site_id=site.site_id, ppid=ppid).first()
        if not doubt:
            doubt = SiteDoubt(site_id=site.site_id, ppid=ppid)
            db.add(doubt)
        doubt.reason = (
            body.get("reason") or "Demo: site requires isHuman assurance on this PPID"
        ).strip()
        doubt.requested_by = site.admin_email or "demo"
        doubt.requested_at = datetime.utcnow()
        doubt.is_active = True
        doubt.cleared_at = None
        doubt.cleared_by = None
        db.commit()

        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "site_domain": site.site_domain,
            "ppid": ppid,
            "doubt_required": True,
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/site-doubt", methods=["POST"])
def ishuman_demo_site_doubt():
    """Demo-only: temporary fresh-proof challenge for one site PPID."""
    if not _demo_enabled():
        return jsonify({"success": False, "error": "demo_disabled"}), 403

    from api.database import SessionLocal, SiteDoubt

    body = request.get_json(silent=True) or {}
    slug = (body.get("site_slug") or "tickets").strip()
    ppid = (body.get("ppid") or "").strip()
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    _spec, site = _site_for_slug(slug)
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    db = SessionLocal()
    try:
        doubt = db.query(SiteDoubt).filter_by(site_id=site.site_id, ppid=ppid).first()
        if not doubt:
            doubt = SiteDoubt(site_id=site.site_id, ppid=ppid)
            db.add(doubt)
        doubt.reason = (
            body.get("reason") or "Demo: site requires fresh proof for this PPID"
        ).strip()
        doubt.requested_by = site.admin_email or "demo"
        doubt.requested_at = datetime.utcnow()
        doubt.is_active = True
        doubt.cleared_at = None
        doubt.cleared_by = None
        db.commit()

        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "site_domain": site.site_domain,
            "ppid": ppid,
            "doubt_required": True,
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/clear-site-doubt", methods=["POST"])
def ishuman_demo_clear_site_doubt():
    """Demo-only: clear a temporary site doubt (blocks remain untouched)."""
    if not _demo_enabled():
        return jsonify({"success": False, "error": "demo_disabled"}), 403

    from api.database import SessionLocal, SiteDoubt

    body = request.get_json(silent=True) or {}
    slug = (body.get("site_slug") or "tickets").strip()
    ppid = (body.get("ppid") or "").strip()
    if not ppid:
        return jsonify({"success": False, "error": "ppid required"}), 400

    _spec, site = _site_for_slug(slug)
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    db = SessionLocal()
    try:
        doubt = db.query(SiteDoubt).filter_by(
            site_id=site.site_id,
            ppid=ppid,
            is_active=True,
        ).first()
        if not doubt:
            return jsonify({"success": False, "error": "no_active_doubt"}), 404
        doubt.is_active = False
        doubt.cleared_at = datetime.utcnow()
        doubt.cleared_by = site.admin_email or "demo"
        db.commit()
        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "ppid": ppid,
            "doubt_required": False,
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/status", methods=["GET"])
def ishuman_demo_status():
    from api.database import (
        IsHumanVerification,
        RevocationList,
        SessionLocal,
        SiteBlock,
        SiteDoubt,
    )

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

        site_blocks = []
        site_doubts = []
        demo_site_ids = [spec["site_id"] for spec in DEMO_SITES.values()]
        requested_ppid = (request.args.get("ppid") or "").strip()
        # Treat NULL is_active as active (older rows / ORM defaults).
        block_query = db.query(SiteBlock).filter(
            SiteBlock.site_id.in_(demo_site_ids),
            SiteBlock.is_active.isnot(False),
        )
        if requested_ppid:
            block_query = block_query.filter(SiteBlock.ppid == requested_ppid)
        for block in block_query.all():
            site_blocks.append({
                "site_id": block.site_id,
                "ppid": block.ppid,
                "reason": block.reason,
            })

        # Also surface site-scoped user revocations so Unban can hydrate even
        # when the SiteBlock row is missing or inactive.
        revoke_query = db.query(RevocationList).filter(
            RevocationList.site_id.in_(demo_site_ids),
            RevocationList.revocation_type == "user",
        )
        if requested_ppid:
            revoke_query = revoke_query.filter(RevocationList.ppid == requested_ppid)
        seen_block_keys = {(b["site_id"], b["ppid"]) for b in site_blocks}
        for row in revoke_query.all():
            ppid = (row.ppid or row.lemma_id or row.credential_id or "").strip()
            if not ppid or not row.site_id:
                continue
            key = (row.site_id, ppid)
            if key in seen_block_keys:
                continue
            seen_block_keys.add(key)
            site_blocks.append({
                "site_id": row.site_id,
                "ppid": ppid,
                "reason": row.reason or "site_ppid_revoked",
            })

        doubt_query = db.query(SiteDoubt).filter(
            SiteDoubt.site_id.in_(demo_site_ids),
            SiteDoubt.is_active.is_(True),
        )
        if requested_ppid:
            doubt_query = doubt_query.filter(SiteDoubt.ppid == requested_ppid)
        for doubt in doubt_query.all():
            site_doubts.append({
                "site_id": doubt.site_id,
                "ppid": doubt.ppid,
                "reason": doubt.reason,
            })

        return jsonify({
            "success": True,
            "master": _public_record(master),
            "derived": [],
            "site_blocks": site_blocks,
            "site_doubts": site_doubts,
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
    from api.database import SessionLocal
    from api.site_ppid_revocation import clear_site_bound_ppid

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
        result = clear_site_bound_ppid(
            db,
            site_id=site.site_id,
            ppid=ppid,
            cleared_by=site.admin_email or "demo",
        )
        return jsonify({
            "success": True,
            "unblocked": bool(result.get("lifted")),
            "site_id": site.site_id,
            "ppid": ppid,
            **result,
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@ishuman_demo_bp.route("/api/demo/ishuman/rotation-check", methods=["POST"])
def ishuman_demo_rotation_check():
    """Read-only: check whether demo-site PPIDs are blocked (rotation demo act)."""
    from api.database import RevocationList, SessionLocal, SiteBlock
    from api.rate_limiter import check_rate_limit

    body = request.get_json(silent=True) or {}
    slug = (body.get("site_slug") or "tickets").strip().lower()
    ppids = body.get("ppids") or []
    if not isinstance(ppids, list) or not ppids:
        return jsonify({"success": False, "error": "ppids required"}), 400
    if len(ppids) > 10:
        return jsonify({"success": False, "error": "too many ppids"}), 400

    _spec, site = _site_for_slug(slug)
    if not site:
        return jsonify({"success": False, "error": "unknown demo site"}), 404

    ip_key = (request.remote_addr or "unknown").strip()
    if not check_rate_limit(f"demo_rotation_check:{ip_key}", 60, 3600):
        return jsonify({"success": False, "error": "rate_limited"}), 429

    site_id = site.site_id
    normalized: list[str] = []
    for raw in ppids:
        ppid = str(raw or "").strip()
        if ppid and ppid not in normalized:
            normalized.append(ppid)

    results: dict[str, dict] = {}
    db = SessionLocal()
    try:
        for ppid in normalized:
            blocked = False
            reason = None
            block = (
                db.query(SiteBlock)
                .filter_by(site_id=site_id, ppid=ppid, is_active=True)
                .first()
            )
            if block:
                blocked = True
                reason = "site_block"
            if not blocked:
                revoke = (
                    db.query(RevocationList)
                    .filter_by(ppid=ppid, revocation_type="user", site_id=site_id)
                    .first()
                )
                if revoke:
                    blocked = True
                    reason = "site_ppid_revoked"
            results[ppid] = {"blocked": blocked, "reason": reason}
    finally:
        db.close()

    return jsonify({
        "success": True,
        "site_id": site_id,
        "site_domain": site.site_domain,
        "results": results,
    })


@ishuman_demo_bp.route("/api/demo/ishuman/network-revoke-request", methods=["POST"])
def ishuman_demo_network_revoke_request():
    return jsonify({"success": False, "error": "network_revocation_retired"}), 410


def _require_demo_admin_token() -> tuple[dict | None, tuple | None]:
    """Guard demo operator-only mutations with an out-of-band admin token."""
    expected = os.getenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN")
    provided = request.headers.get("X-Demo-Admin-Token") or ""
    if not expected or provided != expected:
        return None, (jsonify({
            "success": False,
            "error": "demo_admin_token_required",
            "message": "Set LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN and pass X-Demo-Admin-Token.",
        }), 403)
    return {}, None


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


def _require_demo_qr_idv(*, require_token_header: bool = True) -> tuple[dict | None, tuple | None]:
    """Guards for the public QR shell demo on /demo/ishuman."""
    from api.config import is_ishuman_demo_qr_idv_enabled

    if not is_ishuman_demo_qr_idv_enabled():
        return None, (jsonify({"success": False, "error": "qr_demo_idv_disabled"}), 403)
    if require_token_header:
        expected = os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN")
        provided = request.headers.get("X-Demo-Test-Token") or ""
        if not expected or provided != expected:
            return None, (jsonify({"success": False, "error": "demo_test_token_required"}), 403)
    return {}, None


def _require_demo_skeleton_idv(*, require_token_header: bool = True) -> tuple[dict | None, tuple | None]:
    """Guards for Didit-free skeleton IDV (non-production only)."""
    from api.config import is_ishuman_skeleton_idv_enabled

    if not is_ishuman_skeleton_idv_enabled():
        return None, (jsonify({"success": False, "error": "skeleton_idv_disabled"}), 403)
    if os.getenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "").lower() != "true":
        return None, (jsonify({"success": False, "error": "test_verify_disabled"}), 403)
    if require_token_header:
        expected = os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN")
        provided = request.headers.get("X-Demo-Test-Token") or ""
        if not expected or provided != expected:
            return None, (jsonify({"success": False, "error": "demo_test_token_required"}), 403)
    return {}, None


def _skeleton_credential_ttl_seconds(body: dict | None = None) -> int:
    from api.config import ishuman_skeleton_credential_ttl_seconds

    body = body or {}
    raw = body.get("credential_ttl_seconds")
    if raw is not None:
        try:
            return max(300, min(int(raw), 86400))
        except (TypeError, ValueError):
            pass
    return ishuman_skeleton_credential_ttl_seconds()


def _create_skeleton_verification_row(
    db,
    *,
    wallet_id: str,
    return_url: str = "",
    ppid: str = "",
    credential_ttl_seconds: int | None = None,
    qr_demo: bool = False,
) -> "IsHumanVerification":
    from api.database import IsHumanVerification

    session_id = f"ishuman_skeleton_{secrets.token_urlsafe(16)}"
    provider_session_id = f"skeleton_{secrets.token_urlsafe(12)}"
    metadata = {
        "return_url": return_url,
        "skeleton_idv": True,
    }
    if credential_ttl_seconds is not None:
        metadata["credential_ttl_seconds"] = int(credential_ttl_seconds)
    if qr_demo:
        metadata["qr_demo_idv"] = True
    row = IsHumanVerification(
        session_id=session_id,
        provider_session_id=provider_session_id,
        wallet_id=wallet_id,
        ppid=ppid or None,
        status="pending",
        issuer_id="skeleton",
        metadata_json=metadata,
    )
    db.add(row)
    return row


def _complete_demo_test_session(
    *,
    session_id: str = "",
    stripe_session_id: str = "",
    wallet_secret: str = "",
    credential_ttl_seconds: int | None = None,
    verification_method: str = "didit",
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
                stripe_session_id=record.stripe_session_id or record.session_id,
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
            verification_method=verification_method,
            ttl_seconds=credential_ttl_seconds,
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
            "skeleton_idv": bool((record.metadata_json or {}).get("skeleton_idv")),
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


@ishuman_demo_bp.route("/api/demo/ishuman/skeleton-idv-flow", methods=["POST"])
def ishuman_demo_skeleton_idv_flow():
    """Didit-free IDV for autonomous testing on non-production deploys.

    Creates a pending ``ishuman_skeleton_*`` verification row, optionally stores
    a mobile handoff relay, and can issue a short-lived master credential
    immediately (popup test path) or leave the session pending for handoff E2E.
    """
    _guards, err = _require_demo_skeleton_idv(require_token_header=True)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    wallet_secret = (body.get("wallet_secret") or "").strip()
    return_url = (body.get("return_url") or "").strip()
    include_handoff = bool(body.get("include_handoff", False))
    complete_immediately = bool(body.get("complete_immediately", not include_handoff))
    handoff_id = (body.get("handoff_id") or "").strip()
    encrypted_blob = (body.get("encrypted_blob") or "").strip()
    handoff_mk_fingerprint = (body.get("handoff_mk_fingerprint") or "").strip()
    mk = (body.get("mk") or "").strip()
    ttl = _skeleton_credential_ttl_seconds(body)

    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    from api.database import SessionLocal

    db = SessionLocal()
    try:
        ppid = ""
        if wallet_secret:
            from api.ppid import derive_ppid_from_wallet_secret

            ppid = derive_ppid_from_wallet_secret(wallet_secret, "lemma.id")
        row = _create_skeleton_verification_row(
            db,
            wallet_id=wallet_id,
            return_url=return_url,
            ppid=ppid,
        )
        db.commit()
        session_id = row.session_id
    except Exception:
        db.rollback()
        logger.exception("Skeleton IDV session create failed")
        return jsonify({"success": False, "error": "skeleton_session_failed"}), 500
    finally:
        db.close()

    handoff_payload = None
    if include_handoff:
        from api.ishuman import _handoff_mk_fingerprint, _idv_handoff_ttl_seconds, _store_idv_mobile_handoff

        if not handoff_id or len(handoff_id) < 16:
            handoff_id = f"handoff_{secrets.token_urlsafe(18)}"
        if not mk:
            mk = secrets.token_hex(16)
        if not handoff_mk_fingerprint:
            handoff_mk_fingerprint = _handoff_mk_fingerprint(mk)
        if not encrypted_blob:
            encrypted_blob = "skeleton_placeholder_blob"
        try:
            _store_idv_mobile_handoff(
                handoff_id=handoff_id,
                session_id=session_id,
                wallet_id=wallet_id,
                encrypted_blob=encrypted_blob,
                mk_fingerprint=handoff_mk_fingerprint,
            )
        except Exception:
            logger.exception("Skeleton handoff store failed")
            return jsonify({"success": False, "error": "skeleton_handoff_failed"}), 500

        base = return_url or (request.host_url.rstrip("/") + "/wallet/ishuman-idv")
        joiner = "&" if "?" in base else "?"
        mobile_return_url = (
            f"{base}{joiner}verification_return=true"
            f"&handoff_id={handoff_id}&mk={mk}&ishuman_session={session_id}"
        )
        handoff_payload = {
            "handoff_id": handoff_id,
            "mk": mk,
            "session_id": session_id,
            "mobile_return_url": mobile_return_url,
            "expires_in": _idv_handoff_ttl_seconds(),
        }

    payload = {
        "success": True,
        "session_id": session_id,
        "mode": "skeleton_idv_flow",
        "credential_ttl_seconds": ttl,
        "complete_immediately": complete_immediately,
    }
    if handoff_payload:
        payload["handoff"] = handoff_payload

    if complete_immediately:
        complete_payload, complete_status = _complete_demo_test_session(
            session_id=session_id,
            wallet_secret=wallet_secret,
            credential_ttl_seconds=ttl,
            verification_method="skeleton",
        )
        if complete_status != 200:
            return jsonify(complete_payload), complete_status
        payload.update({
            "credential_id": complete_payload["credential_id"],
            "credential": complete_payload["credential"],
            "ppid": complete_payload["ppid"],
            "expires_at": int((complete_payload["credential"].get("claims") or {}).get("expiresAt", 0)),
        })

    return jsonify(payload)


@ishuman_demo_bp.route("/api/demo/ishuman/skeleton-idv-complete", methods=["POST"])
def ishuman_demo_skeleton_idv_complete():
    """Issue a short-lived master credential for a pending skeleton session."""
    _guards, err = _require_demo_skeleton_idv(require_token_header=True)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    wallet_secret = (body.get("wallet_secret") or "").strip()
    if not session_id:
        return jsonify({"success": False, "error": "session_id required"}), 400
    if not session_id.startswith("ishuman_skeleton_"):
        return jsonify({"success": False, "error": "not_a_skeleton_session"}), 400

    ttl = _skeleton_credential_ttl_seconds(body)
    complete_payload, complete_status = _complete_demo_test_session(
        session_id=session_id,
        wallet_secret=wallet_secret,
        credential_ttl_seconds=ttl,
        verification_method="skeleton",
    )
    if complete_status != 200:
        return jsonify(complete_payload), complete_status

    return jsonify({
        "success": True,
        "session_id": complete_payload["session_id"],
        "credential_id": complete_payload["credential_id"],
        "credential": complete_payload["credential"],
        "ppid": complete_payload["ppid"],
        "mode": "skeleton_idv_complete",
        "credential_ttl_seconds": ttl,
        "expires_at": int((complete_payload["credential"].get("claims") or {}).get("expiresAt", 0)),
    })


@ishuman_demo_bp.route("/api/demo/ishuman/skeleton-idv-expire", methods=["POST"])
def ishuman_demo_skeleton_idv_expire():
    """Mark skeleton verification rows expired after a test run."""
    _guards, err = _require_demo_skeleton_idv(require_token_header=True)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    wallet_id = (body.get("wallet_id") or "").strip()
    if not session_id and not wallet_id:
        return jsonify({"success": False, "error": "session_id or wallet_id required"}), 400

    from api.database import IsHumanVerification, SessionLocal

    db = SessionLocal()
    try:
        query = db.query(IsHumanVerification).filter(
            IsHumanVerification.session_id.like("ishuman_skeleton_%")
        )
        if session_id:
            query = query.filter(IsHumanVerification.session_id == session_id)
        if wallet_id:
            query = query.filter(IsHumanVerification.wallet_id == wallet_id)
        rows = query.all()
        if not rows:
            return jsonify({"success": False, "error": "skeleton_session_not_found"}), 404
        now = datetime.utcnow()
        for row in rows:
            row.status = "expired"
            row.expires_at = now
            row.metadata_json = {
                **(row.metadata_json or {}),
                "skeleton_expired_at": now.isoformat() + "Z",
            }
        db.commit()
        return jsonify({
            "success": True,
            "expired_count": len(rows),
            "session_ids": [row.session_id for row in rows],
        })
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def complete_skeleton_handoff_after_claim(session_id: str) -> tuple[dict, int] | None:
    """Issue a short-lived master credential after a skeleton handoff claim (demo only)."""
    from api.config import (
        is_ishuman_demo_qr_idv_enabled,
        is_ishuman_skeleton_idv_enabled,
        ishuman_demo_qr_credential_ttl_seconds,
    )
    from api.database import SessionLocal, IsHumanVerification

    if not (is_ishuman_skeleton_idv_enabled() or is_ishuman_demo_qr_idv_enabled()):
        return None

    db = SessionLocal()
    try:
        row = (
            db.query(IsHumanVerification)
            .filter(IsHumanVerification.session_id == session_id)
            .first()
        )
        if not row or row.status != "pending":
            return None
        meta = row.metadata_json or {}
        if not meta.get("skeleton_idv"):
            return None
        if is_ishuman_demo_qr_idv_enabled() and not is_ishuman_skeleton_idv_enabled():
            if not meta.get("qr_demo_idv"):
                return None
        ttl = int(meta.get("credential_ttl_seconds") or ishuman_demo_qr_credential_ttl_seconds())
    finally:
        db.close()

    return _complete_demo_test_session(
        session_id=session_id,
        credential_ttl_seconds=ttl,
        verification_method="skeleton",
    )


@ishuman_demo_bp.route("/api/demo/ishuman/qr-demo-idv-flow", methods=["POST"])
def ishuman_demo_qr_demo_idv_flow():
    """Prepare a QR demo IDV session for /demo/ishuman (no Didit).

    The browser unlocks the wallet, calls this endpoint, deposits an encrypted
    handoff blob, renders a QR code, and polls until the phone scan completes.
    """
    _guards, err = _require_demo_qr_idv(require_token_header=True)
    if err:
        return err

    from api.config import ishuman_demo_qr_credential_ttl_seconds, ishuman_idv_handoff_ttl_seconds

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    return_url = (body.get("return_url") or "").strip()
    if not wallet_id:
        return jsonify({"success": False, "error": "wallet_id required"}), 400

    ttl = _skeleton_credential_ttl_seconds(body)
    if body.get("credential_ttl_seconds") is None:
        ttl = ishuman_demo_qr_credential_ttl_seconds()
    handoff_ttl = ishuman_idv_handoff_ttl_seconds()

    from api.database import SessionLocal

    db = SessionLocal()
    try:
        ppid = ""
        wallet_secret = (body.get("wallet_secret") or "").strip()
        if wallet_secret:
            from api.ppid import derive_ppid_from_wallet_secret

            ppid = derive_ppid_from_wallet_secret(wallet_secret, "lemma.id")
        row = _create_skeleton_verification_row(
            db,
            wallet_id=wallet_id,
            return_url=return_url,
            ppid=ppid,
            credential_ttl_seconds=ttl,
            qr_demo=True,
        )
        db.commit()
        session_id = row.session_id
    except Exception:
        db.rollback()
        logger.exception("QR demo IDV session create failed")
        return jsonify({"success": False, "error": "qr_demo_session_failed"}), 500
    finally:
        db.close()

    expires_at = int(time.time()) + ttl
    return jsonify({
        "success": True,
        "session_id": session_id,
        "mode": "qr_demo_idv_flow",
        "credential_ttl_seconds": ttl,
        "handoff_expires_in": handoff_ttl,
        "expires_at": expires_at,
    })


@ishuman_demo_bp.route("/api/demo/ishuman/probe-derive", methods=["POST"])
def ishuman_demo_probe_derive():
    """Server-side derive probe, proves enforcement is not UI-only."""
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
    """Demo-only: create a temporary ticketing doubt requiring fresh IDV."""
    from api.database import SessionLocal, SiteDoubt
    from api.ishuman import _require_wallet_assertion

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
        doubt = db.query(SiteDoubt).filter_by(site_id=site.site_id, ppid=ppid).first()
        if not doubt:
            doubt = SiteDoubt(site_id=site.site_id, ppid=ppid)
            db.add(doubt)
        doubt.reason = (body.get("reason") or "Demo: require fresh IDV on ticketing").strip()
        doubt.requested_by = site.admin_email or "demo"
        doubt.requested_at = datetime.utcnow()
        doubt.is_active = True
        doubt.cleared_at = None
        doubt.cleared_by = None
        db.commit()

        return jsonify({
            "success": True,
            "site_id": site.site_id,
            "site_domain": site.site_domain,
            "ppid": ppid,
            "revocation_synced": False,
            "cleared_derived_credential_ids": [],
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
      production, they still have to complete a real IDV (or pay the IDV
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
    _guards, err = _require_demo_admin_token()
    if err:
        return err

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
    """Retired: demo no longer constructs or exercises a cross-site graph."""
    return jsonify({"success": False, "error": "network_revocation_retired"}), 410
