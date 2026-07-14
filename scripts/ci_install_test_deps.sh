#!/usr/bin/env bash
# Shared CI dependency install for lemma.id Python test workflows.
set -euo pipefail

python -m pip install --upgrade pip
python -m pip install \
  pytest \
  flask \
  requests \
  sqlalchemy \
  stripe \
  flask-cors \
  psycopg2-binary \
  redis \
  cryptography \
  webauthn \
  PyJWT \
  python-dotenv \
  Flask-Limiter \
  qrcode \
  boto3 \
  build \
  twine

# Application tests exercise the native verifier directly. Install the local
# extension instead of leaving those paths to fail at runtime.
python -m pip install -e ./lemma-crypto
