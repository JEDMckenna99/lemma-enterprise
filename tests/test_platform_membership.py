import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from api.platform_membership import (
    build_platform_user_row,
    collect_registered_platform_ppids,
    has_registered_platform_membership,
    is_probe_ppid,
    list_registered_platform_user_rows,
)

OWNER_PPID = "did:lemma:ppid_" + ("ab" * 32)
DEV_PPID = "did:lemma:ppid_" + ("cd" * 32)
PROBE_PPID = "did:lemma:ppid_" + ("b" * 64)


def test_is_probe_ppid_detects_uniform_test_hex():
    assert is_probe_ppid(PROBE_PPID) is True
    assert is_probe_ppid(OWNER_PPID) is False
    assert is_probe_ppid(None) is True
    assert is_probe_ppid("not-a-ppid") is True


class _Row:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Query:
    def __init__(self, rows):
        self._rows = list(rows)
        self._filters = []

    def filter(self, *args, **_kwargs):
        return self

    def filter_by(self, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        rows = self.all()
        return rows[0] if rows else None

    def order_by(self, *_args, **_kwargs):
        return self


class _FakeDb:
    def __init__(self, tables):
        self._tables = tables

    def query(self, model):
        name = model.__name__
        return _Query(self._tables.get(name, []))


def test_collect_registered_platform_ppids_uses_site_admins_and_developers():
    db = _FakeDb(
        {
            "SiteAdmin": [
                _Row(site_id="lemma.id", admin_did=OWNER_PPID, is_active=True),
            ],
            "Customer": [
                _Row(customer_did=DEV_PPID, role="developer"),
                _Row(customer_did=PROBE_PPID, role="developer"),
                _Row(customer_did=OWNER_PPID, role="user"),
            ],
        }
    )

    registered = collect_registered_platform_ppids(site_id="lemma.id", db=db)
    assert registered == {OWNER_PPID, DEV_PPID}


def test_has_registered_platform_membership_rejects_probe_and_orphans():
    db = _FakeDb(
        {
            "SiteAdmin": [_Row(site_id="lemma.id", admin_did=OWNER_PPID, is_active=True)],
            "Customer": [],
        }
    )

    assert has_registered_platform_membership(OWNER_PPID, db=db) is True
    assert has_registered_platform_membership(PROBE_PPID, db=db) is False
    assert has_registered_platform_membership(DEV_PPID, db=db) is False


def test_build_platform_user_row_prefers_site_admin_role():
    now = datetime.utcnow()
    db = _FakeDb(
        {
            "PlatformUser": [
                _Row(
                    id=1,
                    user_did=OWNER_PPID,
                    email="owner@lemma.id",
                    display_name="Owner",
                    status="active",
                )
            ],
            "PlatformUserSite": [
                _Row(id=9, user_did=OWNER_PPID, site_id="lemma.id", role="user", joined_at=now, status="active")
            ],
            "Customer": [],
            "SiteAdmin": [
                _Row(
                    id=3,
                    site_id="lemma.id",
                    admin_did=OWNER_PPID,
                    admin_email="owner@lemma.id",
                    admin_role="owner",
                    is_active=True,
                )
            ],
        }
    )

    row = build_platform_user_row(ppid=OWNER_PPID, site_id="lemma.id", db=db)
    assert row is not None
    assert row["role"] == "owner"
    assert row["source"] == "site_admins"


def test_list_registered_platform_user_rows_excludes_orphan_memberships(monkeypatch):
    db = _FakeDb(
        {
            "SiteAdmin": [
                _Row(
                    site_id="lemma.id",
                    admin_did=OWNER_PPID,
                    is_active=True,
                    admin_role="owner",
                    admin_email="owner@lemma.id",
                )
            ],
            "Customer": [],
            "PlatformUser": [],
            "PlatformUserSite": [
                _Row(id=1, user_did=PROBE_PPID, site_id="lemma.id", role="user", joined_at=datetime.utcnow())
            ],
        }
    )

    monkeypatch.setattr("api.platform_membership.get_db", lambda: db, raising=False)

    rows = list_registered_platform_user_rows(site_id="lemma.id", db=db)
    ppids = {row["ppid"] for row in rows}
    assert OWNER_PPID in ppids
    assert PROBE_PPID not in ppids


def test_get_admin_users_uses_registered_platform_rows(monkeypatch):
    from flask import Flask

    from api.dashboard_api import dashboard_bp, get_admin_users

    expected = [
        {
            "ppid": OWNER_PPID,
            "email": "owner@lemma.id",
            "role": "owner",
            "status": "active",
            "created_at": datetime.utcnow(),
            "last_active": None,
            "joined_at": datetime.utcnow(),
        }
    ]

    monkeypatch.setattr(
        "api.platform_membership.list_registered_platform_user_rows",
        lambda **kwargs: list(expected),
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(dashboard_bp)

    handler = get_admin_users
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__

    with app.test_request_context("/api/admin/users?site_id=lemma.id"):
        response = handler()
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["total"] == 1
        assert body["users"][0]["ppid"] == OWNER_PPID
