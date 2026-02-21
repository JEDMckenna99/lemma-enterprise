# Lemma.id

Passwordless authentication with locally verifiable credentials.

## Status

`beta` - production deployed at `https://lemma.id`.

This repository contains the platform implementation used for ongoing beta rollout.
Some areas are production-proven, and some are still being hardened.

## What Exists Today

- Passkey-based wallet unlock flow
- Signed credential issuance and local credential verification
- Revocation checks (Bloom filter path)
- IAM-style permission lemmas and developer APIs
- Session-sync and cross-site wallet bridge infrastructure

## Current Limits (Important)

- Not all endpoints have fully uniform auth/error policy yet
- Cross-device and cross-site behavior works, but edge-case hardening is still active
- Some docs and interfaces are still evolving during beta

## Repo Layout

- `app.py` - Flask app entry and route wiring
- `api/` - API endpoints and service modules
- `auth/` - auth decorators, session, rate limiting
- `lemma-crypto/` - Rust verification/signing engine
- `static/js/` - wallet bridge and client SDK assets
- `templates/` - web UI templates
- `tests/` - test suites, including a fast smoke set

## Quick Start (Local)

Prerequisites:

- Python 3.11+
- Rust toolchain
- PostgreSQL

Setup:

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

cd lemma-crypto
cargo build --release
cd ..

python app.py
```

Configuration is environment-variable based.
No secrets are committed to this repository.

## Fast Verification (<5 min)

Run the minimal smoke suite:

```bash
python -m pytest tests/test_quickstart_smoke.py -q
```

These tests are pure local checks and do not require Redis, Stripe, or external services.

## Security

Please see `SECURITY.md` for vulnerability reporting and responsible disclosure.

## License

Licensed under Apache-2.0. See `LICENSE`.