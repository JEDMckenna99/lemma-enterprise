"""Minimal Flask app for the lemma-signing Heroku worker."""

from __future__ import annotations

import os

os.environ.setdefault("LEMMA_SIGNING_SERVICE", "1")

from flask import Flask

from api.revocation_api import revocation_api
from api.signing_service import signing_bp


def create_signing_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(signing_bp)
    # Public trust-bundle mirror (same signed bloom/trust-list as lemma.id).
    # Gives verifiers a second origin when the main web dynos are down.
    app.register_blueprint(revocation_api)
    return app


app = create_signing_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")))
