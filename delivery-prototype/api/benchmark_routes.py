"""Benchmark API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request

from models.db import list_benchmark_runs, save_benchmark_run

benchmark_bp = Blueprint("benchmark", __name__)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@benchmark_bp.route("/driver/benchmark")
def benchmark_page():
    return render_template("driver/benchmark.html")


@benchmark_bp.route("/api/benchmark/run", methods=["POST"])
def run_benchmark():
    from app import DB_PATH

    data = request.get_json(force=True) or {}
    mode = str(data.get("mode") or "local-first")
    profile = str(data.get("network_profile") or "good")
    results = data.get("results") or {}
    run_id = f"BENCH-{uuid.uuid4().hex[:8].upper()}"
    save_benchmark_run(DB_PATH, run_id, mode, profile, results, _now())
    return jsonify({"success": True, "run_id": run_id})


@benchmark_bp.route("/api/benchmark/results")
def benchmark_results():
    from app import DB_PATH

    return jsonify({"runs": list_benchmark_runs(DB_PATH)})
