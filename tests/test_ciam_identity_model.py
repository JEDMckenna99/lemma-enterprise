"""Static and unit checks for CIAM Phase 0–1 foundations."""

from __future__ import annotations

import ast
from pathlib import Path

from api.ciam_identity import (
    ALIAS_STATUS_ACTIVE,
    ALIAS_STATUS_RESERVED,
    APP_SUBJECT_KEY,
    is_active_directory_status,
    normalize_app_subject_ppid,
)
from api.database import IdentitySubjectAlias, SiteUser


ROOT = Path(__file__).resolve().parents[1]
LEMMA_SIGNIN_JS = ROOT / "static" / "js" / "lemma-signin.js"
SITE_MANAGEMENT_PY = ROOT / "api" / "site_management_api.py"


def test_lemma_signin_label_not_interpolated_into_innerhtml():
    source = LEMMA_SIGNIN_JS.read_text(encoding="utf-8")
    assert "btn.textContent = this.buttonLabel" in source
    assert "${this.buttonLabel}" not in source


def test_lemma_signin_supports_lemma_origin_attribute():
    source = LEMMA_SIGNIN_JS.read_text(encoding="utf-8")
    assert "'lemma-origin'" in source
    assert "config.lemmaOrigin = this.lemmaOrigin" in source


def test_site_users_list_fail_closed_on_db_error():
    source = SITE_MANAGEMENT_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "get_site_users"
    )
    body = ast.get_source_segment(source, func) or ""
    assert "'directory_unavailable'" in body
    assert "), 503" in body
    assert "'success': True" not in body.split("Database query failed")[1].split("finally:")[0]


def test_site_user_orm_uses_canonical_ppid_columns():
    assert SiteUser.user_ppid.key == "user_ppid"
    assert SiteUser.status.key == "status"
    assert SiteUser.role.key == "role"
    assert SiteUser.user_metadata.name == "metadata"


def test_identity_subject_alias_model_columns():
    assert IdentitySubjectAlias.__tablename__ == "identity_subject_aliases"
    assert hasattr(IdentitySubjectAlias, "from_ppid")
    assert hasattr(IdentitySubjectAlias, "to_ppid")
    assert hasattr(IdentitySubjectAlias, "evidence_jti")


def test_ciam_identity_helpers():
    assert APP_SUBJECT_KEY == "user_ppid"
    assert normalize_app_subject_ppid("  did:lemma:ppid_abc  ") == "did:lemma:ppid_abc"
    assert is_active_directory_status("active") is True
    assert is_active_directory_status("suspended") is False
    assert ALIAS_STATUS_RESERVED == "reserved"
    assert ALIAS_STATUS_ACTIVE == "active"
