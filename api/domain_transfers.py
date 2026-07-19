"""
Audited domain transfer workflow between customer accounts.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any, Dict, Optional

from flask import Blueprint, g, jsonify, request

from auth.decorators import require_customer_or_admin, extract_authenticated_ppid_from_request
from api.domain_ownership import (
    consume_verified_domain_proof,
    get_verification_instructions,
    mint_domain_verification_token,
)
from api.site_access import authorize_site_access, get_authenticated_ppid, verify_site_ownership
from api.site_hostname import canonicalize_site_hostname, SiteHostnameError

logger = logging.getLogger(__name__)

domain_transfers_bp = Blueprint("domain_transfers", __name__)


def _audit_transfer_event(transfer_id: str, site_id: str, action: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    try:
        from api.audit_logger import AuditEvent, log_event

        log_event(
            AuditEvent.SITE_UPDATED,
            site_id=site_id,
            result="success",
            metadata={"transfer_id": transfer_id, "action": action, **(metadata or {})},
        )
    except Exception as exc:
        logger.debug("Could not audit domain transfer event: %s", exc)


def _active_transfer_for_site(db, site_id: str):
    from api.database import DomainTransfer

    return (
        db.query(DomainTransfer)
        .filter(
            DomainTransfer.site_id == site_id,
            DomainTransfer.status.in_(("pending", "accepted_pending_proof")),
        )
        .order_by(DomainTransfer.created_at.desc())
        .first()
    )


@domain_transfers_bp.route("/api/customer/domain-verification/start", methods=["POST"])
@require_customer_or_admin
def start_domain_verification():
    """Mint a domain verification token and return DNS/well-known instructions."""
    from api.customer_accounts import _extract_customer_id_from_request

    customer_id = _extract_customer_id_from_request()
    if not customer_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    raw_domain = (data.get("site_domain") or data.get("domain") or "").strip()
    if not raw_domain:
        return jsonify({"error": "site_domain required"}), 400

    try:
        domain = canonicalize_site_hostname(raw_domain)
    except SiteHostnameError as exc:
        return jsonify({"error": str(exc)}), 400

    actor_ppid = get_authenticated_ppid() or extract_authenticated_ppid_from_request()
    if not actor_ppid:
        return jsonify({"error": "wallet_ppid_required"}), 400

    token = mint_domain_verification_token(domain)
    method = (data.get("method") or "well-known").strip().lower()
    instructions = get_verification_instructions(domain, token)

    try:
        from api.database import SessionLocal
        from api.domain_ownership import store_domain_verification_challenge

        db = SessionLocal()
        try:
            store_domain_verification_challenge(
                db,
                domain=domain,
                token=token,
                customer_id=customer_id,
                actor_ppid=str(actor_ppid),
                purpose=(data.get("purpose") or "site_registration"),
            )
        finally:
            db.close()
    except Exception:
        pass

    return jsonify(
        {
            "success": True,
            "domain": domain,
            "verification_token": token,
            "method": method,
            "instructions": instructions,
        }
    )


@domain_transfers_bp.route("/api/customer/domain-transfers", methods=["POST"])
@require_customer_or_admin
def initiate_domain_transfer():
    """Source owner initiates transfer to another customer (requires domain proof)."""
    from api.customer_accounts import _extract_customer_id_from_request

    customer_id = _extract_customer_id_from_request()
    if not customer_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    site_id = (data.get("site_id") or "").strip()
    to_customer_id = (data.get("to_customer_id") or "").strip()
    token = (data.get("verification_token") or "").strip()
    method = (data.get("verification_method") or data.get("method") or "well-known").strip().lower()

    if not site_id or not to_customer_id or not token:
        return jsonify({"error": "site_id, to_customer_id, and verification_token are required"}), 400

    actor_ppid = get_authenticated_ppid() or extract_authenticated_ppid_from_request()
    if not actor_ppid or not verify_site_ownership(site_id, str(actor_ppid)):
        return jsonify({"success": False, "code": "UNAUTHORIZED_SITE_ACCESS", "error": "Site ownership required"}), 403

    from api.database import DomainTransfer, SessionLocal, Site

    db = SessionLocal()
    try:
        site = db.query(Site).filter(Site.site_id == site_id).first()
        if not site:
            return jsonify({"error": "site_not_found"}), 404

        if not consume_verified_domain_proof(site.site_domain, token, method):
            return jsonify({"error": "domain_verification_failed"}), 403

        existing = _active_transfer_for_site(db, site_id)
        if existing:
            return jsonify({"error": "transfer_already_pending", "transfer_id": existing.transfer_id}), 409

        transfer_id = secrets.token_urlsafe(16)
        row = DomainTransfer(
            transfer_id=transfer_id,
            site_id=site_id,
            site_domain=site.site_domain,
            status="pending",
            from_customer_id=customer_id,
            to_customer_id=to_customer_id,
            initiated_by_ppid=str(actor_ppid),
            verification_method=method,
            verification_token=token,
            audit_metadata={"initiated_at": datetime.utcnow().isoformat()},
        )
        db.add(row)
        db.commit()
        _audit_transfer_event(transfer_id, site_id, "initiated", {"to_customer_id": to_customer_id})
        return jsonify({"success": True, "transfer_id": transfer_id, "status": "pending"})
    finally:
        db.close()


@domain_transfers_bp.route("/api/customer/domain-transfers/<transfer_id>/accept", methods=["POST"])
@require_customer_or_admin
def accept_domain_transfer(transfer_id: str):
    """Target customer accepts transfer with domain proof."""
    from api.customer_accounts import _extract_customer_id_from_request

    customer_id = _extract_customer_id_from_request()
    if not customer_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    token = (data.get("verification_token") or "").strip()
    method = (data.get("verification_method") or data.get("method") or "well-known").strip().lower()
    if not token:
        return jsonify({"error": "verification_token required"}), 400

    actor_ppid = get_authenticated_ppid() or extract_authenticated_ppid_from_request()
    if not actor_ppid:
        return jsonify({"error": "wallet_ppid_required"}), 400

    from api.database import DomainTransfer, SessionLocal, Site, SiteAdmin

    db = SessionLocal()
    try:
        transfer = db.query(DomainTransfer).filter(DomainTransfer.transfer_id == transfer_id).first()
        if not transfer or transfer.status != "pending":
            return jsonify({"error": "transfer_not_available"}), 404
        if transfer.to_customer_id != customer_id:
            return jsonify({"error": "transfer_not_for_this_customer"}), 403

        if not consume_verified_domain_proof(transfer.site_domain, token, method):
            return jsonify({"error": "domain_verification_failed"}), 403

        site = db.query(Site).filter(Site.site_id == transfer.site_id).first()
        if not site:
            return jsonify({"error": "site_not_found"}), 404

        transfer.status = "completed"
        transfer.accepted_by_ppid = str(actor_ppid)
        transfer.completed_at = datetime.utcnow()
        transfer.updated_at = datetime.utcnow()
        transfer.audit_metadata = {
            **(transfer.audit_metadata or {}),
            "accepted_at": datetime.utcnow().isoformat(),
        }

        try:
            from api.storage_helpers import upsert_site_to_postgres

            upsert_site_to_postgres(
                site_id=transfer.site_id,
                site_domain=transfer.site_domain,
                customer_id=customer_id,
                allow_customer_reassign=True,
            )
        except Exception as exc:
            logger.warning("Could not upsert site customer reassignment: %s", exc)

        db.query(SiteAdmin).filter(
            SiteAdmin.site_id == transfer.site_id,
            SiteAdmin.is_active == True,  # noqa: E712
        ).update({"is_active": False})

        admin = SiteAdmin(
            site_id=transfer.site_id,
            admin_did=str(actor_ppid),
            admin_email=(data.get("admin_email") or "").strip() or site.admin_email,
            admin_role="owner",
            permissions=["users", "permissions", "billing"],
            added_by=str(actor_ppid),
            is_active=True,
        )
        db.add(admin)
        db.commit()
        _audit_transfer_event(transfer_id, transfer.site_id, "completed", {"to_customer_id": customer_id})
        return jsonify({"success": True, "transfer_id": transfer_id, "site_id": transfer.site_id, "status": "completed"})
    finally:
        db.close()


@domain_transfers_bp.route("/api/customer/domain-transfers/<transfer_id>/cancel", methods=["POST"])
@require_customer_or_admin
def cancel_domain_transfer(transfer_id: str):
    from api.customer_accounts import _extract_customer_id_from_request

    customer_id = _extract_customer_id_from_request()
    if not customer_id:
        return jsonify({"error": "Authentication required"}), 401

    actor_ppid = get_authenticated_ppid() or extract_authenticated_ppid_from_request()
    from api.database import DomainTransfer, SessionLocal

    db = SessionLocal()
    try:
        transfer = db.query(DomainTransfer).filter(DomainTransfer.transfer_id == transfer_id).first()
        if not transfer or transfer.status != "pending":
            return jsonify({"error": "transfer_not_available"}), 404

        if transfer.from_customer_id != customer_id and not (
            actor_ppid and verify_site_ownership(transfer.site_id, str(actor_ppid))
        ):
            return jsonify({"error": "not_authorized_to_cancel"}), 403

        transfer.status = "cancelled"
        transfer.cancelled_at = datetime.utcnow()
        transfer.updated_at = datetime.utcnow()
        db.commit()
        _audit_transfer_event(transfer_id, transfer.site_id, "cancelled")
        return jsonify({"success": True, "transfer_id": transfer_id, "status": "cancelled"})
    finally:
        db.close()


def pending_transfer_allows_registration(db, site_id: str, customer_id: str) -> bool:
    transfer = _active_transfer_for_site(db, site_id)
    return bool(transfer and transfer.to_customer_id == customer_id and transfer.status == "pending")
