"""Dispatch dashboard API — fake route creation and QR generation."""

from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone

import qrcode
from flask import Blueprint, jsonify, render_template, request, send_file

from config import DEVICE_KEY_PATH, ISSUER_KEY_PATH
from crypto.device_keys import ensure_device_keypair, ensure_issuer_keypair, load_public_key_b64
from crypto.issuer import build_fake_packages, issue_route_credential
from models.db import get_route, list_routes, save_route

dispatch_bp = Blueprint("dispatch", __name__)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dispatch_bp.route("/dispatch")
def dispatch_page():
    return render_template("dispatch/index.html")


@dispatch_bp.route("/api/routes", methods=["GET"])
def api_list_routes():
    from app import DB_PATH

    return jsonify({"routes": list_routes(DB_PATH)})


@dispatch_bp.route("/api/routes", methods=["POST"])
def api_create_route():
    from app import DB_PATH

    data = request.get_json(force=True) or {}
    route_id = str(data.get("route_id") or "R-001").strip()
    driver_id = str(data.get("driver_id") or "D-42").strip()
    device_id = str(data.get("device_id") or "DEVICE-001").strip()
    package_count = int(data.get("package_count") or 20)
    stops = data.get("stops") or ["S-014", "S-015", "S-016"]
    if isinstance(stops, str):
        stops = [s.strip() for s in stops.split(",") if s.strip()]
    policy_defaults = {
        "photo_required": bool(data.get("photo_required", True)),
        "signature_required": bool(data.get("signature_required", False)),
        "otp_required": bool(data.get("otp_required", False)),
    }
    expires_hours = int(data.get("expires_hours") or 12)

    issuer_key = ensure_issuer_keypair(ISSUER_KEY_PATH)
    device_key = ensure_device_keypair(DEVICE_KEY_PATH)
    device_pubkey = load_public_key_b64(device_key)

    packages = build_fake_packages(
        issuer_key, route_id, stops, package_count, policy_defaults
    )
    credential = issue_route_credential(
        issuer_key,
        route_id=route_id,
        driver_id=driver_id,
        device_id=device_id,
        device_pubkey=device_pubkey,
        stops=stops,
        packages=[{
            "package_id": p["package_id"],
            "stop_id": p["stop_id"],
            "policy": p["policy"],
        } for p in packages],
        policy_defaults=policy_defaults,
        expires_hours=expires_hours,
    )
    created_at = _now()
    save_route(DB_PATH, route_id, driver_id, device_id, credential, created_at)

    from cryptography.hazmat.primitives import serialization

    bundle = {
        "route_credential": credential,
        "packages": packages,
        "device_private_key_hex": device_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex(),
    }

    return jsonify({
        "success": True,
        "route_id": route_id,
        "credential": credential,
        "packages": packages,
        "bundle": bundle,
        "created_at": created_at,
    })


@dispatch_bp.route("/api/routes/<route_id>/bundle")
def api_route_bundle(route_id: str):
    from app import DB_PATH

    row = get_route(DB_PATH, route_id)
    if not row:
        return jsonify({"error": "route_not_found"}), 404
    device_key = ensure_device_keypair(DEVICE_KEY_PATH)
    from cryptography.hazmat.primitives import serialization

    credential = row["credential"]
    packages = []
    issuer_key = ensure_issuer_keypair(ISSUER_KEY_PATH)
    from crypto.issuer import issue_package_assignment

    for pkg in credential.get("packages", []):
        assignment = issue_package_assignment(
            issuer_key,
            package_id=pkg["package_id"],
            route_id=route_id,
            stop_id=pkg["stop_id"],
            policy=pkg.get("policy", {}),
        )
        packages.append({**pkg, "assignment": assignment})

    return jsonify({
        "route_credential": credential,
        "packages": packages,
        "device_private_key_hex": device_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex(),
    })


@dispatch_bp.route("/api/routes/<route_id>/qr/<package_id>")
def api_package_qr(route_id: str, package_id: str):
    from app import DB_PATH

    row = get_route(DB_PATH, route_id)
    if not row:
        return jsonify({"error": "route_not_found"}), 404
    pkg = next((p for p in row["credential"].get("packages", []) if p["package_id"] == package_id), None)
    if not pkg:
        return jsonify({"error": "package_not_found"}), 404
    issuer_key = ensure_issuer_keypair(ISSUER_KEY_PATH)
    from crypto.issuer import issue_package_assignment

    assignment = issue_package_assignment(
        issuer_key,
        package_id=package_id,
        route_id=route_id,
        stop_id=pkg["stop_id"],
        policy=pkg.get("policy", {}),
    )
    payload = json.dumps(assignment, separators=(",", ":"))
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", download_name=f"{package_id}.png")


@dispatch_bp.route("/api/routes/<route_id>/qr-sheet")
def api_qr_sheet(route_id: str):
    from app import DB_PATH

    row = get_route(DB_PATH, route_id)
    if not row:
        return jsonify({"error": "route_not_found"}), 404
    return render_template(
        "dispatch/qr_sheet.html",
        route_id=route_id,
        packages=row["credential"].get("packages", []),
    )
