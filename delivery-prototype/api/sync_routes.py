"""Offline queue sync API."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from config import DEVICE_KEY_PATH
from crypto.device_keys import ensure_device_keypair
from crypto.verifier import verify_delivery_event
from models.db import get_events_for_route, get_route, save_event

sync_bp = Blueprint("sync", __name__)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@sync_bp.route("/api/sync/events", methods=["POST"])
def sync_events():
    from app import DB_PATH

    data = request.get_json(force=True) or {}
    route_id = str(data.get("route_id") or "").strip()
    events = data.get("events") or []
    if not route_id:
        return jsonify({"error": "route_id_required"}), 400

    row = get_route(DB_PATH, route_id)
    if not row:
        return jsonify({"error": "route_not_found"}), 404

    credential = row["credential"]
    existing = get_events_for_route(DB_PATH, route_id)
    prior_by_pkg: dict[str, dict] = {}
    results = []

    for item in events:
        event = item if isinstance(item, dict) else {}
        event_id = str(event.get("event_id") or "")
        package_id = str(event.get("package_id") or "")
        if not event_id:
            results.append({"event_id": None, "status": "rejected", "reason": "missing_event_id"})
            continue

        dup = next((e for e in existing if e["event_id"] == event_id), None)
        if dup:
            results.append({"event_id": event_id, "status": "synced", "reason": "duplicate"})
            continue

        prior = prior_by_pkg.get(package_id)
        ok, reason = verify_delivery_event(event, route_credential=credential, prior_event=prior)
        if not ok:
            save_event(DB_PATH, event_id, route_id, package_id, "rejected", event, _now())
            results.append({"event_id": event_id, "status": "rejected", "reason": reason})
            continue

        synced_at = _now()
        save_event(DB_PATH, event_id, route_id, package_id, "synced", event, event.get("timestamp", synced_at), synced_at)
        prior_by_pkg[package_id] = event
        existing.append({"event_id": event_id, "event": event})
        results.append({"event_id": event_id, "status": "synced", "reason": "ok"})

    return jsonify({"success": True, "results": results})


@sync_bp.route("/api/sync/status/<route_id>")
def sync_status(route_id: str):
    from app import DB_PATH

    events = get_events_for_route(DB_PATH, route_id)
    return jsonify({"route_id": route_id, "events": events})
