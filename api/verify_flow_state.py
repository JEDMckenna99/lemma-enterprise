"""Server-minted opaque flow state for lemma.id verification ceremonies.

Binds opener origin + site_id (+ purpose/redirect) so the /verify popup cannot
be driven by independently attacker-controlled query parameters.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Optional
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

verify_flow_state_bp = Blueprint("verify_flow_state", __name__)

FLOW_STATE_TTL_SECONDS = 600
FLOW_STATE_PREFIX = "verify_flow_state:"
PLATFORM_SITE_IDS = frozenset({"lemma.id", "lemma_platform", "www.lemma.id"})


def _bool_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def require_verify_flow_state() -> bool:
    """When true, live /verify ceremonies must present a minted flow_state."""
    return _bool_env("LEMMA_REQUIRE_VERIFY_FLOW_STATE", default=True)


def _normalize_origin(origin: str) -> Optional[str]:
    text = (origin or "").strip()
    if not text:
        return None
    try:
        parsed = urlparse(text)
    except Exception:
        return None
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"https", "http"} or not host:
        return None
    # Production-facing origins must be https; loopback may use http.
    if scheme == "http" and host not in {"localhost", "127.0.0.1"}:
        return None
    port = parsed.port
    if port and not (
        (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    ):
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def _origin_host(origin: str) -> str:
    try:
        return (urlparse(origin).hostname or "").lower()
    except Exception:
        return ""


def _canonicalize_site(site_id: str) -> tuple[Optional[str], Optional[str]]:
    from api.site_hostname import try_canonicalize_site_hostname

    raw = (site_id or "").strip().lower()
    if raw in {"lemma_platform", "lemma.id", "www.lemma.id"}:
        return "lemma.id", None
    return try_canonicalize_site_hostname(raw)


def origin_matches_site(opener_origin: str, site_id: str) -> bool:
    """Opener origin host must equal the requested site hostname (platform exception)."""
    origin = _normalize_origin(opener_origin)
    site, err = _canonicalize_site(site_id)
    if not origin or err or not site:
        return False
    host = _origin_host(origin)
    if not host:
        return False
    if site in PLATFORM_SITE_IDS or site == "lemma.id":
        return host in {"lemma.id", "www.lemma.id", "localhost", "127.0.0.1"}
    return host == site


def _redirect_allowed(redirect_return: str, opener_origin: str) -> bool:
    text = (redirect_return or "").strip()
    if not text:
        return True
    from api.url_safety import is_host_allowed_redirect, is_safe_relative_redirect

    if is_safe_relative_redirect(text):
        return True
    host = _origin_host(opener_origin)
    if not host:
        return False
    # Absolute return URLs must stay on the opener's host (https, or http loopback).
    try:
        parsed = urlparse(text)
    except Exception:
        return False
    scheme = (parsed.scheme or "").lower()
    ret_host = (parsed.hostname or "").lower()
    if scheme == "http" and ret_host in {"localhost", "127.0.0.1"}:
        return ret_host == host
    return is_host_allowed_redirect(text, [host])


def mint_flow_state(
    *,
    opener_origin: str,
    site_id: str,
    issue_mode: str = "",
    redirect_return: str = "",
    request_nonce: str = "",
    required_assurance: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """Persist and return an opaque flow_state token, or (None, error_code)."""
    origin = _normalize_origin(opener_origin)
    site, site_err = _canonicalize_site(site_id)
    if not origin:
        return None, "invalid_opener_origin"
    if site_err or not site:
        return None, "invalid_site_id"
    if not origin_matches_site(origin, site):
        return None, "origin_site_mismatch"
    redirect = (redirect_return or "").strip()
    if redirect and not _redirect_allowed(redirect, origin):
        return None, "invalid_redirect_return"

    token = secrets.token_urlsafe(32)
    payload = {
        "opener_origin": origin,
        "site_id": site,
        "issue_mode": (issue_mode or "").strip(),
        "redirect_return": redirect,
        "request_nonce": (request_nonce or "").strip(),
        "required_assurance": (required_assurance or "").strip().lower(),
    }
    from auth.redis_store import store as redis_store

    redis_store(f"{FLOW_STATE_PREFIX}{token}", payload, ttl_seconds=FLOW_STATE_TTL_SECONDS)
    return token, None


def resolve_flow_state(token: str) -> Optional[dict[str, Any]]:
    """Read flow state without consuming (popup may reload)."""
    text = (token or "").strip()
    if not text:
        return None
    from auth.redis_store import get as redis_get

    data = redis_get(f"{FLOW_STATE_PREFIX}{text}")
    if not isinstance(data, dict):
        return None
    if not data.get("opener_origin") or not data.get("site_id"):
        return None
    return data


@verify_flow_state_bp.route("/api/verify/flow-state", methods=["POST", "OPTIONS"])
def create_verify_flow_state():
    """Mint opaque flow state from a relying-site Origin + site_id."""
    if request.method == "OPTIONS":
        origin = _normalize_origin(request.headers.get("Origin") or "")
        resp = jsonify({"success": True})
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Max-Age"] = "600"
            resp.headers["Vary"] = "Origin"
        return resp, 204

    origin_header = request.headers.get("Origin") or ""
    data = request.get_json(silent=True) or {}
    # Prefer browser Origin; body opener_origin is ignored for binding.
    site_id = str(data.get("site_id") or "").strip()
    issue_mode = str(data.get("issue_mode") or "").strip()
    redirect_return = str(data.get("redirect_return") or "").strip()
    request_nonce = str(data.get("request_nonce") or "").strip()
    required_assurance = str(data.get("required_assurance") or "").strip()

    token, err = mint_flow_state(
        opener_origin=origin_header,
        site_id=site_id,
        issue_mode=issue_mode,
        redirect_return=redirect_return,
        request_nonce=request_nonce,
        required_assurance=required_assurance,
    )
    if err or not token:
        resp = jsonify({"success": False, "error": err or "flow_state_mint_failed"})
        origin = _normalize_origin(origin_header)
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
        return resp, 400

    binding = resolve_flow_state(token) or {}
    resp = jsonify(
        {
            "success": True,
            "flow_state": token,
            "opener_origin": binding.get("opener_origin"),
            "site_id": binding.get("site_id"),
            "expires_in_seconds": FLOW_STATE_TTL_SECONDS,
        }
    )
    origin = _normalize_origin(origin_header)
    if origin:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    return resp
