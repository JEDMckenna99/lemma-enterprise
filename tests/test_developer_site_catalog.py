"""Tests for merged developer site catalog (customer JSON + site registry)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from unittest.mock import MagicMock

import pytest


@dataclass
class FakeCustomer:
    customer_id: str = "dev_test"
    email: Optional[str] = "dev@lemma.id"
    sites: List[Dict[str, Any]] = field(default_factory=list)
    api_keys: List[Dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def catalog_module(monkeypatch):
    import api.customer_accounts as mod

    class FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self._rows

    class FakeSession:
        def __init__(self, sites):
            self._sites = sites

        def query(self, model):
            return FakeQuery(self._sites)

        def close(self):
            return None

    class FakeSite:
        site_id = MagicMock()

    FakeSite.site_id.in_ = MagicMock(side_effect=lambda ids: ids)

    site_rows = [
        SimpleNamespace(
            site_id="lemma.id",
            site_domain="lemma.id",
            company_name="Lemma Platform",
            admin_email="owner@lemma.id",
            api_key="lm_live_abc1234567890",
            key_status="active",
            created_at=datetime(2026, 1, 1),
            key_last_used=None,
        ),
        SimpleNamespace(
            site_id="tickets-demo.lemma.id",
            site_domain="tickets-demo.lemma.id",
            company_name="Tickets Demo",
            admin_email="owner@lemma.id",
            api_key="lm_live_demo9876543210",
            key_status="active",
            created_at=datetime(2026, 2, 1),
            key_last_used=None,
        ),
    ]

    monkeypatch.setattr(
        "api.developer_api._get_owned_site_ids",
        lambda db, ppid: ["lemma.id", "tickets-demo.lemma.id"],
    )
    monkeypatch.setattr(
        "api.database.SessionLocal",
        lambda: FakeSession(site_rows),
    )
    monkeypatch.setattr(
        "api.database.Site",
        FakeSite,
    )
    return mod


def test_collect_developer_site_catalog_merges_registry_sites_and_keys(catalog_module):
    customer = FakeCustomer(sites=[], api_keys=[])
    ppid = "did:lemma:ppid_" + ("a" * 64)

    sites, keys = catalog_module._collect_developer_site_catalog(customer, ppid)

    assert len(sites) == 2
    domains = {s["site_domain"] for s in sites}
    assert "lemma.id" in domains
    assert "tickets-demo.lemma.id" in domains

    assert len(keys) == 2
    assert {k["site_id"] for k in keys} == {"lemma.id", "tickets-demo.lemma.id"}
    assert all(k.get("key_hint") for k in keys)


def test_collect_developer_site_catalog_dedupes_customer_and_registry(catalog_module):
    customer = FakeCustomer(
        sites=[{"site_id": "lemma.id", "site_domain": "lemma.id", "site_label": "Lemma"}],
        api_keys=[{
            "site_id": "lemma.id",
            "name": "Existing",
            "key_hint": "34567890",
            "status": "active",
        }],
    )
    ppid = "did:lemma:ppid_" + ("b" * 64)

    sites, keys = catalog_module._collect_developer_site_catalog(customer, ppid)

    assert len(sites) == 2
    lemma_keys = [k for k in keys if k["site_id"] == "lemma.id"]
    assert len(lemma_keys) == 1
    assert lemma_keys[0]["key_hint"] == "34567890"
