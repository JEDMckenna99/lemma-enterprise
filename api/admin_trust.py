"""Admin Trust & Safety API for persistent, site-scoped isHuman decisions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request
from flask_cors import cross_origin

from auth.decorators import require_platform_admin as require_site_admin

logger = logging.getLogger(__name__)

admin_trust_bp = Blueprint("admin_trust", __name__)


def _to_iso(value) -> Optional[str]:
    if value is None:
        return None
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def truncate_ppid(ppid: Optional[str]) -> str:
    if not ppid:
        return ""
    text = str(ppid)
    if len(text) <= 20:
        return text
    return f"{text[:16]}…{text[-6:]}"


def _site_domain_map() -> Dict[str, str]:
    from api.dashboard_api import _load_admin_sites

    mapping: Dict[str, str] = {}
    for row in _load_admin_sites():
        site_id = str(row.get("site_id") or "").strip()
        domain = str(row.get("site_domain") or site_id).strip()
        if site_id:
            mapping[site_id] = domain
    return mapping


def _resolve_master_credential_id(db, wallet_id: Optional[str]) -> Optional[str]:
    if not wallet_id:
        return None
    from api.database import IsHumanVerification

    row = (
        db.query(IsHumanVerification)
        .filter_by(wallet_id=wallet_id, status="verified")
        .order_by(IsHumanVerification.verified_at.desc())
        .first()
    )
    if row and row.credential_id:
        return row.credential_id
    row = (
        db.query(IsHumanVerification)
        .filter_by(wallet_id=wallet_id)
        .order_by(IsHumanVerification.created_at.desc())
        .first()
    )
    return row.credential_id if row else None


def _serialize_block_row(db, block, site_domains: Dict[str, str]) -> Dict[str, Any]:
    return {
        "block_id": block.id,
        "site_id": block.site_id,
        "site_domain": site_domains.get(block.site_id, block.site_id),
        "ppid": block.ppid,
        "ppid_display": truncate_ppid(block.ppid),
        "reason": block.reason or "",
        "evidence_url": block.evidence_url or "",
        "blocked_at": _to_iso(block.blocked_at),
        "blocked_by": block.blocked_by or "",
        "is_active": bool(block.is_active),
    }


def _require_admin_principal():
    from auth.request_principal import resolve_admin_principal

    principal, error = resolve_admin_principal()
    if not principal:
        return None, (jsonify({"success": False, "error": error or "admin_required"}), 403)
    return principal, None


@admin_trust_bp.route("/api/admin/trust/queue", methods=["GET"])
@cross_origin()
@require_site_admin
def list_trust_queue():
    return jsonify({"success": False, "error": "network_revocation_retired"}), 410


@admin_trust_bp.route("/api/admin/trust/blocks", methods=["GET"])
@cross_origin()
@require_site_admin
def list_active_blocks():
    """Active site-scoped blocks across the network."""
    from api.database import SessionLocal, SiteBlock

    site_id = (request.args.get("site_id") or "").strip()
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = max(int(request.args.get("offset", 0)), 0)

    db = SessionLocal()
    try:
        site_domains = _site_domain_map()
        query = db.query(SiteBlock).filter_by(is_active=True)
        if site_id:
            query = query.filter_by(site_id=site_id)
        total = query.count()
        rows = query.order_by(SiteBlock.blocked_at.desc()).all()
        rows = rows[offset:offset + limit]
        items = [_serialize_block_row(db, row, site_domains) for row in rows]
        return jsonify({
            "success": True,
            "blocks": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as exc:
        logger.exception("Failed to list active blocks: %s", exc)
        return jsonify({"success": False, "error": "blocks_list_failed"}), 500
    finally:
        db.close()


@admin_trust_bp.route("/api/admin/trust/revocations", methods=["GET"])
@cross_origin()
@require_site_admin
def list_network_revocations():
    return jsonify({"success": False, "error": "network_revocation_retired"}), 410


@admin_trust_bp.route("/api/admin/trust/queue/<int:block_id>/reject", methods=["POST"])
@cross_origin()
@require_site_admin
def reject_trust_queue_item(block_id: int):
    return jsonify({"success": False, "error": "network_revocation_retired"}), 410
