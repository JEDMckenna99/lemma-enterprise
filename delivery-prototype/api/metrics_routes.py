"""Field metrics optional backend helpers."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, send_from_directory

from models.schemas import MetricsLog, aggregate_metrics, validate_metrics_payload

metrics_bp = Blueprint("metrics", __name__)

ROOT = Path(__file__).resolve().parents[1]
SW_PATH = ROOT / "static" / "js" / "metrics" / "service-worker.js"


@metrics_bp.route("/metrics")
def metrics_home():
    return redirect("/metrics/log")


@metrics_bp.route("/metrics/start")
def metrics_start_page():
    return render_template("metrics/start.html")


@metrics_bp.route("/metrics/log")
def metrics_log_page():
    return render_template("metrics/log.html")


@metrics_bp.route("/metrics/summary")
def metrics_summary_page():
    return render_template("metrics/summary.html")


@metrics_bp.route("/metrics/report")
def metrics_report_page():
    return render_template("metrics/report.html")


@metrics_bp.route("/metrics/sw.js")
def metrics_service_worker():
    response = send_from_directory(SW_PATH.parent, "service-worker.js")
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Service-Worker-Allowed"] = "/metrics/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@metrics_bp.route("/api/metrics/validate", methods=["POST"])
def validate_metrics():
    data = request.get_json(force=True) or {}
    try:
        log = MetricsLog.from_dict(data)
        return jsonify({"valid": True, "log": log.to_dict()})
    except ValueError as exc:
        return jsonify({"valid": False, "error": str(exc)}), 400


@metrics_bp.route("/api/metrics/aggregate", methods=["POST"])
def aggregate():
    data = request.get_json(force=True) or {}
    logs = data.get("logs") or []
    for row in logs:
        validate_metrics_payload(row)
    return jsonify(aggregate_metrics(logs))
