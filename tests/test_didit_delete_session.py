"""Unit tests for Didit session/user purge routing."""

from __future__ import annotations

import pytest


class _Resp:
    def __init__(self, status_code: int, text: str = "", content_type: str = "application/json"):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}


@pytest.mark.unit
def test_delete_response_success_accepts_204():
    from billing.didit_manager import DiditManager

    assert DiditManager._delete_response_success(_Resp(204, "")) is True


@pytest.mark.unit
def test_delete_response_rejects_html_404():
    from billing.didit_manager import DiditManager

    assert DiditManager._delete_response_success(
        _Resp(404, "<!doctype html><html>", "text/html")
    ) is False


@pytest.mark.unit
def test_delete_session_tries_delete_route_before_legacy(monkeypatch):
    import billing.didit_manager as dm

    calls = []

    def _fake_delete(url, **kwargs):
        calls.append(url)
        if url.endswith("/delete/"):
            return _Resp(204, "")
        return _Resp(404, "<!doctype html>", "text/html")

    monkeypatch.setattr(dm.requests, "delete", _fake_delete)

    mgr = dm.DiditManager.__new__(dm.DiditManager)
    mgr.api_base = "https://verification.didit.me"
    mgr.api_key = "test-key"
    mgr.enabled = True

    result = mgr.delete_session("sess-123")
    assert result["success"] is True
    assert result["status_code"] == 204
    assert len(calls) == 1
    assert calls[0].endswith("/v3/session/sess-123/delete/")
