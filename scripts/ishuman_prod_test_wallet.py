"""
Shared configuration for the production isHuman revocation test wallet.

Secrets are read from environment variables only, never commit wallet_secret.
"""

from __future__ import annotations

import os
import secrets

DEFAULT_WALLET_ID = "wallet_ishuman_prod_fixture"
DEFAULT_TARGET_SITE = "lemma-demo-tickets-1d3d7411af33.herokuapp.com"
DEFAULT_SITE_ID = "site_demo_tickets"


def prod_test_wallet_id() -> str:
    return (os.getenv("LEMMA_ISHUMAN_PROD_TEST_WALLET_ID") or DEFAULT_WALLET_ID).strip()


def prod_test_wallet_secret() -> str:
    return (os.getenv("LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET") or "").strip()


def prod_test_target_site() -> str:
    return (os.getenv("LEMMA_ISHUMAN_PROD_TEST_TARGET_SITE") or DEFAULT_TARGET_SITE).strip()


def prod_test_site_id() -> str:
    return (os.getenv("LEMMA_ISHUMAN_PROD_TEST_SITE_ID") or DEFAULT_SITE_ID).strip()


def prod_test_site_ppid() -> str:
    return (os.getenv("LEMMA_ISHUMAN_PROD_TEST_SITE_PPID") or "").strip()


def prod_test_master_credential_id() -> str:
    return (os.getenv("LEMMA_ISHUMAN_PROD_TEST_MASTER_CREDENTIAL_ID") or "").strip()


def generate_wallet_secret() -> str:
    return secrets.token_hex(32)


def require_prod_test_secret() -> str:
    secret = prod_test_wallet_secret()
    if not secret:
        raise RuntimeError(
            "Set LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET (64-char hex) before running prod drills."
        )
    return secret
