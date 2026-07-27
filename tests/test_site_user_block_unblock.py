"""Pins the developer-dashboard site-user block / unblock controls.

These cover the operator-facing tier-1 revocation UX:
1. ``clear_site_bound_ppid`` is the authenticated inverse of
   ``revoke_site_bound_ppid`` and is the only path that removes a site block.
2. The dashboard ``/revoke`` endpoint blocks ANY PPID (upsert, not 404) so an
   operator can paste a PPID straight from their logs.
3. The dashboard ``/unblock`` endpoint routes to the canonical clear.
4. Both privileged routes are registered in the authz policy at admin scope
   with site binding required.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_PPID_REVOCATION_PY = ROOT / "api" / "site_ppid_revocation.py"
SITE_MANAGEMENT_PY = ROOT / "api" / "site_management_api.py"
AUTHZ_POLICY_PY = ROOT / "api" / "authz_policy.py"
SITE_USERS_HTML = ROOT / "templates" / "developer" / "site_users.html"


def _func_source(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name),
        None,
    )
    assert func is not None, f"{name} missing from {path.name}"
    return ast.get_source_segment(src, func) or ""


def test_clear_site_bound_ppid_signature_and_behavior():
    source = _func_source(SITE_PPID_REVOCATION_PY, "clear_site_bound_ppid")
    # Touches both enforcement surfaces.
    assert "SiteBlock" in source
    assert "RevocationList" in source
    # Only acts on the site-scoped user revocation for this PPID.
    assert 'revocation_type="user"' in source or "revocation_type='user'" in source
    assert "is_amnesty_eligible.is_(False)" not in source
    assert "governance_kill_not_amnesty_eligible" not in source
    # Rebuilds verifier state so the PPID stops being rejected.
    assert "invalidate_bloom_filter_cache" in source
    assert "rebuild_global_verifier_from_db" in source
    assert "db.delete(row)" in source
    # Reports what happened to the caller.
    assert '"lifted"' in source
    assert '"blocks_deactivated"' in source
    assert '"revocations_cleared"' in source
    assert '"bloom_rebuilt"' in source


def test_dashboard_revoke_blocks_any_ppid_without_404():
    source = _func_source(SITE_MANAGEMENT_PY, "revoke_site_user")
    # Upsert rather than 404 when the PPID isn't a pre-stored site user.
    assert "INSERT INTO site_users" in source
    assert "ON CONFLICT (site_id, user_ppid)" in source
    assert "User not found" not in source
    # Still drives canonical tier-1 revocation.
    assert "revoke_site_bound_ppid" in source


def test_dashboard_unblock_endpoint_exists():
    source = _func_source(SITE_MANAGEMENT_PY, "unblock_site_user")
    assert "clear_site_bound_ppid" in source
    assert "governance_kill" not in source
    # Restores the stored user row.
    assert "status = 'active'" in source

    full = SITE_MANAGEMENT_PY.read_text(encoding="utf-8")
    assert "/api/developer/sites/<site_id>/users/<ppid>/unblock" in full


def test_unblock_route_registered_admin_scope():
    source = AUTHZ_POLICY_PY.read_text(encoding="utf-8")
    assert '"/api/developer/sites/<site_id>/users/<ppid>/unblock"' in source
    tree = ast.parse(source)
    # Find the dict entry for the unblock route and assert admin scope nearby.
    idx = source.index("/api/developer/sites/<site_id>/users/<ppid>/unblock")
    window = source[idx: idx + 300]
    assert 'required_scope="admin"' in window
    assert "site_binding_required=True" in window


def test_site_users_template_has_block_unblock_controls():
    html = SITE_USERS_HTML.read_text(encoding="utf-8")
    # Per-row actions.
    assert "data-block=" in html
    assert "data-unblock=" in html
    # Block-by-PPID box + handlers.
    assert "block-ppid-input" in html
    assert "function blockUser(" in html
    assert "function unblockUser(" in html
    # Wired to the real endpoints.
    assert "/revoke`" in html or "/revoke'" in html or "}/revoke" in html
    assert "/unblock" in html
