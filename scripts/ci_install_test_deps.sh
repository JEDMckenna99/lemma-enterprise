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
  build \
  twine
