"""Product sunset gate.

When ``LEMMA_SUNSET`` is truthy, lemma.id stops issuing, verifying, and
serving product surfaces. Privacy, terms, health, and static assets stay up
so data-subject requests and the tombstone page still work.
"""
from __future__ import annotations

import os

from flask import jsonify, render_template, request


_TRUTHY = {"1", "true", "yes", "on"}

_ALLOWED_EXACT = {
    "/privacy",
    "/terms",
    "/health",
    "/ready",
    "/favicon.ico",
    "/robots.txt",
}

_ALLOWED_PREFIXES = (
    "/static/",
    "/.well-known/",
)


def sunset_enabled() -> bool:
    return (os.getenv("LEMMA_SUNSET") or "").strip().lower() in _TRUTHY


def _is_allowed_path(path: str) -> bool:
    if path in _ALLOWED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def maybe_sunset_response():
    """Return a sunset response, or None to continue the normal request."""
    if not sunset_enabled():
        return None
    path = request.path or "/"
    if _is_allowed_path(path):
        return None
    wants_html = "text/html" in (request.headers.get("Accept") or "")
    if wants_html and request.method in {"GET", "HEAD"}:
        return render_template("legal/sunset.html"), 200
    return jsonify({
        "error": "service_shutdown",
        "message": "lemma.id has shut down. Contact privacy@lemma.id for data requests.",
    }), 410
