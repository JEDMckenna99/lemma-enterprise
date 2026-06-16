"""Simulated cloud-check delivery confirmation."""

from __future__ import annotations

import random
import time

from flask import Blueprint, jsonify, request

from config import CLOUD_DELAYS

cloud_bp = Blueprint("cloud", __name__)


@cloud_bp.route("/api/cloud/confirm", methods=["POST"])
def cloud_confirm():
    data = request.get_json(force=True) or {}
    profile = str(data.get("network_profile") or "good")
    delay = CLOUD_DELAYS.get(profile, 0.5)

    if profile == "offline":
        return jsonify({"success": False, "error": "offline", "allowed": False}), 503

    if delay is not None:
        if profile == "timeout":
            time.sleep(min(delay, 5))
            return jsonify({"success": False, "error": "timeout", "allowed": False}), 504
        time.sleep(delay)

    package_id = data.get("package_id")
    retry = profile in ("weak", "bad") and random.random() < 0.14
    if retry:
        return jsonify({
            "success": False,
            "error": "retry_required",
            "allowed": False,
            "network_profile": profile,
            "latency_sec": delay,
        }), 409

    return jsonify({
        "success": True,
        "allowed": True,
        "package_id": package_id,
        "network_profile": profile,
        "latency_sec": delay,
    })


@cloud_bp.route("/api/cloud/deliver", methods=["POST"])
def cloud_deliver():
    data = request.get_json(force=True) or {}
    profile = str(data.get("network_profile") or "good")
    delay = CLOUD_DELAYS.get(profile, 0.5)
    if profile == "offline":
        return jsonify({"success": False, "error": "offline"}), 503
    if delay:
        time.sleep(min(delay, 2))
    return jsonify({"success": True, "completed": True, "mode": "cloud-check"})
