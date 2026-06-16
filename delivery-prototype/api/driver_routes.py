"""Driver PWA page routes."""

from __future__ import annotations

from flask import Blueprint, render_template

driver_bp = Blueprint("driver", __name__)


@driver_bp.route("/driver")
def driver_home():
    return render_template("driver/home.html")


@driver_bp.route("/driver/scan")
def driver_scan():
    return render_template("driver/scan.html")


@driver_bp.route("/driver/queue")
def driver_queue():
    return render_template("driver/queue.html")
