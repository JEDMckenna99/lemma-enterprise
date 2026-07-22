"""Production-pattern signup with Redis required for co-located action-stamp services."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "proof-verifier-py"))

from lemma_proof_verifier_nonce_store import RedisNonceStore  # noqa: E402
from lemma_proof_verifier import VerificationContext  # noqa: E402

app = Flask(__name__)
SITE_ID = os.getenv("SITE_ID", "app.example.com")


def _require_redis():
    url = os.getenv("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL required")
    import redis

    return redis.from_url(url, decode_responses=True)


@app.post("/api/signup")
def signup():
    # Production deployments colocate Redis for action-stamp nonce consumption.
    _require_redis()
    body = request.get_json(silent=True) or {}
    presentation = body.get("presentation")
    if not presentation:
        return jsonify({"success": False, "reason": "presentation_missing"}), 400
    ctx = VerificationContext(site_id=SITE_ID, required_assurance="ishuman")
    result = ctx.verify(presentation)
    if not result.ok:
        return jsonify({"success": False, "reason": result.reason}), 401
    return jsonify({"success": True, "ppid": result.ppid}), 200


def action_nonce_store() -> RedisNonceStore:
    return RedisNonceStore(_require_redis())
