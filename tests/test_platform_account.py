import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from api.platform_account import (
    is_admin_account_type,
    resolve_account_type,
    resolve_account_type_for_customer,
)


class _Account:
    def __init__(self, account_type="developer"):
        self.account_type = account_type


class _Customer:
    customer_did = "did:lemma:ppid_" + ("ab" * 32)


def test_resolve_account_type_defaults_to_customer(monkeypatch):
    monkeypatch.setattr("api.platform_account.get_platform_account", lambda ppid, db=None: None)
    assert resolve_account_type(_Customer.customer_did) == "customer"


def test_resolve_account_type_for_customer_uses_platform_account(monkeypatch):
    monkeypatch.setattr(
        "api.platform_account.get_platform_account",
        lambda ppid, db=None: _Account("owner"),
    )
    assert resolve_account_type_for_customer(_Customer()) == "owner"
    assert is_admin_account_type("owner") is True
    assert is_admin_account_type("developer") is False
