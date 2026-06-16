"""Custody chain audit API."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from crypto.verifier import verify_delivery_event, verify_route_credential
from models.db import get_events_for_route, get_route

audit_bp = Blueprint("audit", __name__)


def _build_chain(route_row: dict, events: list[dict]) -> dict:
    credential = route_row["credential"]
    steps = []

    ok, reason = verify_route_credential(credential, device_id=credential.get("device_id"))
    steps.append({"step": "route_credential_issued", "valid": ok, "detail": reason})

    pkg_count = len(credential.get("packages") or [])
    steps.append({
        "step": "packages_assigned",
        "valid": pkg_count > 0,
        "detail": f"{pkg_count} packages on route",
    })

    prior_by_pkg: dict[str, dict] = {}
    synced = 0
    rejected = 0
    for row in events:
        event = row["event"]
        ok, reason = verify_delivery_event(
            event,
            route_credential=credential,
            prior_event=prior_by_pkg.get(row["package_id"]),
        )
        prior_by_pkg[row["package_id"]] = event
        steps.append({
            "step": f"delivery_event_{row['event_id']}",
            "valid": ok and row["status"] == "synced",
            "detail": f"{row['status']}: {reason}",
            "package_id": row["package_id"],
        })
        if row["status"] == "synced":
            synced += 1
        elif row["status"] == "rejected":
            rejected += 1

    steps.append({"step": "events_synced", "valid": synced > 0 or not events, "detail": f"{synced} synced"})
    steps.append({"step": "backend_verified_signatures", "valid": rejected == 0, "detail": f"{rejected} rejected"})
    tamper_free = all(s["valid"] for s in steps)
    steps.append({"step": "no_tampering_detected", "valid": tamper_free, "detail": "chain intact" if tamper_free else "tamper detected"})

    return {
        "route_id": route_row["route_id"],
        "driver_id": route_row["driver_id"],
        "device_id": route_row["device_id"],
        "steps": steps,
        "event_count": len(events),
        "tamper_free": tamper_free,
    }


@audit_bp.route("/audit")
def audit_page():
    return render_template("audit/index.html")


@audit_bp.route("/api/audit/chain/<route_id>")
def audit_chain(route_id: str):
    from app import DB_PATH

    row = get_route(DB_PATH, route_id)
    if not row:
        return jsonify({"error": "route_not_found"}), 404
    events = get_events_for_route(DB_PATH, route_id)
    return jsonify(_build_chain(row, events))


@audit_bp.route("/api/audit/routes")
def audit_routes():
    from app import DB_PATH
    from models.db import list_routes

    routes = list_routes(DB_PATH)
    chains = []
    for r in routes:
        row = get_route(DB_PATH, r["route_id"])
        if row:
            events = get_events_for_route(DB_PATH, r["route_id"])
            chains.append(_build_chain(row, events))
    return jsonify({"chains": chains})
