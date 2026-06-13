"""
Bootstrap-specific auth decorators (site API key flows).
"""

from __future__ import annotations

from functools import wraps

from flask import g, jsonify, request


def require_site_bootstrap_api_key(f):
    """
    Validate site bootstrap API key from X-API-Key or Authorization Bearer.
    Does not require X-Lemma-Credential (bootstrap uses site key + email binding).
    """

    @wraps(f)
    def wrapped(*args, **kwargs):
        api_key = (request.headers.get("X-API-Key") or "").strip()
        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                candidate = auth_header[7:].strip()
                if candidate and not candidate.startswith("{") and not candidate.startswith("lm_agent_"):
                    api_key = candidate
        if not api_key:
            return jsonify(
                {
                    "error": "unauthorized",
                    "message": "Site API key required in X-API-Key or Authorization: Bearer",
                }
            ), 401

        from api.agent_credentials import _validate_request_api_key

        is_valid, key_info = _validate_request_api_key(api_key)
        if not is_valid:
            return jsonify({"error": "unauthorized", "message": "Invalid API key"}), 401

        g.api_key = api_key
        g.api_key_info = key_info
        g.authenticated = True
        g.auth_method = "api_key"
        return f(*args, **kwargs)

    return wrapped
