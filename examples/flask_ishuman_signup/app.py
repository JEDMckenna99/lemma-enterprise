"""Minimal Flask T2 signup example using lemma-ishuman-verify (Section 10)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "ishuman-verify-py"))

from lemma_ishuman_verify import VerificationContext  # noqa: E402

app = Flask(__name__)
SITE_ID = os.getenv("SITE_ID", "app.example.com")
REQUIRED = os.getenv("REQUIRED_ASSURANCE", "ishuman")
_CTX = VerificationContext(site_id=SITE_ID, required_assurance=REQUIRED)


@app.post("/api/signup")
def signup():
    body = request.get_json(silent=True) or {}
    presentation = body.get("presentation")
    if not presentation:
        return jsonify({"success": False, "reason": "presentation_missing"}), 400

    result = _CTX.verify(presentation)
    if not result.ok:
        return jsonify({"success": False, "reason": result.reason}), 401

    # Bind ppid to account row here (omitted).
    return jsonify({"success": True, "ppid": result.ppid, "assurance": result.assurance}), 200


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "5050")))
