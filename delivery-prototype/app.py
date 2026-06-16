"""Delivery prototype Flask application."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, render_template

from api.audit_routes import audit_bp
from api.benchmark_routes import benchmark_bp
from api.cloud_sim import cloud_bp
from api.dispatch_routes import dispatch_bp
from api.driver_routes import driver_bp
from api.metrics_routes import metrics_bp
from api.sync_routes import sync_bp
from config import BENCHMARK_DIR, DATA_DIR, DB_PATH, FAKE_DATA_ONLY, KEYS_DIR
from models.db import init_db

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
app.config["JSON_SORT_KEYS"] = False

DATA_DIR.mkdir(parents=True, exist_ok=True)
KEYS_DIR.mkdir(parents=True, exist_ok=True)
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
init_db(DB_PATH)

app.register_blueprint(dispatch_bp)
app.register_blueprint(driver_bp)
app.register_blueprint(cloud_bp)
app.register_blueprint(sync_bp)
app.register_blueprint(audit_bp)
app.register_blueprint(metrics_bp)
app.register_blueprint(benchmark_bp)


@app.route("/")
def index():
    return render_template("index.html", fake_data_only=FAKE_DATA_ONLY)


@app.route("/health")
def health():
    return jsonify({"success": True, "fake_data_only": FAKE_DATA_ONLY})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5099"))
    app.run(host="0.0.0.0", port=port, debug=not bool(os.getenv("DYNO")))
