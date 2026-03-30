import json
from argparse import Namespace
from pathlib import Path

from scripts import lemma_cli


def test_build_doctor_report_untrusted_issuer():
    report = lemma_cli.build_doctor_report("invalid_lemma:untrusted_issuer:did:lemma:abc")
    findings = report["findings"]
    assert any("issuer" in item["issue"].lower() for item in findings)


def test_build_doctor_report_wallet_unlock_required():
    report = lemma_cli.build_doctor_report("wallet_unlock_required")
    findings = report["findings"]
    assert any("wallet unlock" in item["issue"].lower() for item in findings)


def test_run_doctor_fix_wallet_unlock_required_no_browser(monkeypatch, capsys):
    def fake_http_json_request(**kwargs):
        assert kwargs.get("method") == "POST"
        assert str(kwargs.get("url", "")).endswith("/api/wallet/session-sync")
        return 401, {"success": False, "error": "no_session", "unlock_url": "https://lemma.id/wallet/unlock"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        error="wallet_unlock_required",
        message="",
        fix=True,
        api_base="https://lemma.id",
        session_file="",
        no_browser=True,
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_doctor(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    remediation = payload["remediation"]
    assert remediation["action"] == "unlock_wallet_session"
    assert remediation["unlock_url"] == "https://lemma.id/wallet/unlock"
    assert remediation["browser_opened"] is False
    assert payload["fix_requested"] is True


def test_run_doctor_fix_auth_required_clears_session(tmp_path, capsys):
    session_file = tmp_path / "auth.json"
    session_file.write_text(json.dumps({"agent_token": "lm_agent_old"}), encoding="utf-8")
    args = Namespace(
        error=lemma_cli.ERR_AUTH_REQUIRED,
        message="",
        fix=True,
        api_base="https://lemma.id",
        session_file=str(session_file),
        no_browser=True,
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_doctor(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    remediation = payload["remediation"]
    assert remediation["action"] == "reset_auth_session"
    assert remediation["removed_session_file"] is True
    assert not session_file.exists()


def test_run_doctor_fix_invalid_ppid_dry_run(monkeypatch, tmp_path, capsys):
    def fake_http_json_request(**kwargs):
        assert kwargs.get("method") == "POST"
        return 401, {"success": False, "error": "no_session", "unlock_url": "https://lemma.id/wallet/unlock"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    dry_run_output = tmp_path / "doctor-dry-run.json"
    args = Namespace(
        error="invalid_ppid",
        message="",
        fix=True,
        api_base="https://lemma.id",
        session_file="",
        no_browser=True,
        timeout=5.0,
        dry_run=True,
        dry_run_output=str(dry_run_output),
        json=True,
    )
    code = lemma_cli.run_doctor(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    remediation = payload["remediation"]
    assert payload["dry_run"] is True
    assert remediation["action"] == "switch_to_wallet_credential_flow"
    assert "credential-file" in " ".join(remediation["next_steps"])
    artifact = json.loads(dry_run_output.read_text(encoding="utf-8"))
    assert artifact["command"] == "doctor"
    assert artifact["dry_run"] is True


def test_run_verify_checks_without_env(monkeypatch):
    monkeypatch.delenv("LEMMA_API_KEY", raising=False)
    monkeypatch.delenv("LEMMA_PLATFORM_API_KEY", raising=False)
    report = lemma_cli.run_verify_checks(api_base=None)
    assert report["ok"] is False
    assert any(item["name"] == "platform_api_key_present" for item in report["checks"])


def test_run_init_writes_config(tmp_path):
    args = Namespace(
        site_id="site_test123",
        site_domain="https://Example.com/path",
        api_base="https://lemma.id",
        output_dir=str(tmp_path),
        force=False,
        json=False,
    )
    code = lemma_cli.run_init(args)
    assert code == 0

    config_file = tmp_path / ".lemma" / "config.json"
    assert config_file.exists()
    payload = json.loads(config_file.read_text(encoding="utf-8"))
    assert payload["site_id"] == "site_test123"
    assert payload["site_domain"] == "example.com"
    assert payload["auth_header"] == "X-Lemma-Credential"


def test_run_setup_creates_scaffold_files(tmp_path):
    args = Namespace(
        site_id="site_test123",
        site_domain="https://Example.com/path",
        api_base="https://lemma.id",
        output_dir=str(tmp_path),
        framework="both",
        force=False,
        json=True,
    )
    code = lemma_cli.run_setup(args)
    assert code == 0
    assert (tmp_path / ".lemma" / "config.json").exists()
    assert (tmp_path / ".lemma" / "frontend-header-snippet.js").exists()
    assert (tmp_path / ".lemma" / "server-middleware-flask.py").exists()
    assert (tmp_path / ".lemma" / "server-middleware-express.js").exists()
    assert (tmp_path / ".lemma" / ".env.lemma.example").exists()


def test_build_audit_report_fails_without_setup(tmp_path):
    report = lemma_cli.build_audit_report(
        project_dir=tmp_path,
        framework="both",
        api_base=None,
        skip_health=True,
    )
    assert report["ok"] is False
    assert report["score"]["passing"] < report["score"]["total"]
    check_names = [check["name"] for check in report["checks"]]
    assert "config_present" in check_names


def test_main_audit_json_output(tmp_path, capsys):
    setup_exit = lemma_cli.main(
        [
            "setup",
            "--site-id",
            "site_abc",
            "--site-domain",
            "example.com",
            "--output-dir",
            str(tmp_path),
            "--framework",
            "flask",
            "--json",
        ]
    )
    assert setup_exit == 0
    capsys.readouterr()

    exit_code = lemma_cli.main(
        [
            "audit",
            "--project-dir",
            str(tmp_path),
            "--framework",
            "flask",
            "--skip-health",
            "--json",
        ]
    )
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert exit_code in (0, 1)
    assert payload["schema_version"] == lemma_cli.CLI_SCHEMA_VERSION
    assert payload["error_code"] in (lemma_cli.ERR_OK, lemma_cli.ERR_EXPECTED_STATUS_MISMATCH)
    assert "checks" in payload
    assert "score" in payload


def test_run_fix_requires_safe_flag(tmp_path):
    args = Namespace(
        project_dir=str(tmp_path),
        framework="both",
        site_id="site_x",
        site_domain="example.com",
        api_base="",
        skip_health=True,
        safe=False,
        json=True,
    )
    code = lemma_cli.run_fix(args)
    assert code == lemma_cli.EXIT_USAGE


def test_run_fix_safe_bootstraps_files(tmp_path):
    args = Namespace(
        project_dir=str(tmp_path),
        framework="flask",
        site_id="site_x",
        site_domain="https://Example.com/path",
        api_base="https://lemma.id",
        skip_health=True,
        safe=True,
        json=True,
    )
    code = lemma_cli.run_fix(args)
    assert code in (lemma_cli.EXIT_OK, lemma_cli.EXIT_CHECK_FAILED)
    assert (tmp_path / ".lemma" / "config.json").exists()
    assert (tmp_path / ".lemma" / "frontend-header-snippet.js").exists()
    assert (tmp_path / ".lemma" / "server-middleware-flask.py").exists()


def test_run_smoke_accepts_credential_file(tmp_path, monkeypatch):
    credential_path = tmp_path / "credential.json"
    credential_path.write_text(json.dumps({"id": "cred_1", "issuer": "did:lemma:issuer"}), encoding="utf-8")

    captured: dict[str, str] = {}

    def fake_execute_smoke_request(**kwargs):
        captured["header_value"] = kwargs.get("header_value", "")
        return 200, '{"ok":true}', None

    monkeypatch.setattr(lemma_cli, "_execute_smoke_request", fake_execute_smoke_request)
    args = Namespace(
        url="https://example.com/protected",
        method="GET",
        header="",
        credential_file=str(credential_path),
        expect_status=200,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_smoke(args)
    assert code == lemma_cli.EXIT_OK
    assert len(captured.get("header_value", "")) > 10


def test_run_smoke_succeeds_with_mocked_request(monkeypatch):
    def fake_execute_smoke_request(**kwargs):
        assert kwargs.get("url") == "https://example.com/protected"
        assert kwargs.get("method") == "GET"
        assert kwargs.get("header_value") == "abc123"
        assert kwargs.get("timeout") == 5.0
        return 200, '{"ok":true}', None

    monkeypatch.setattr(lemma_cli, "_execute_smoke_request", fake_execute_smoke_request)
    args = Namespace(
        url="https://example.com/protected",
        method="GET",
        header="abc123",
        credential_file="",
        expect_status=200,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_smoke(args)
    assert code == lemma_cli.EXIT_OK


def test_main_ci_json_output_skip_smoke(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LEMMA_API_KEY", "test-key")
    setup_exit = lemma_cli.main(
        [
            "setup",
            "--site-id",
            "site_ci",
            "--site-domain",
            "example.com",
            "--output-dir",
            str(tmp_path),
            "--framework",
            "flask",
            "--json",
        ]
    )
    assert setup_exit == 0
    capsys.readouterr()

    ci_exit = lemma_cli.main(
        [
            "ci",
            "--project-dir",
            str(tmp_path),
            "--framework",
            "flask",
            "--skip-health",
            "--skip-smoke",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert ci_exit == lemma_cli.EXIT_OK
    assert payload["schema_version"] == lemma_cli.CLI_SCHEMA_VERSION
    assert payload["command"] == "ci"
    assert payload["error_code"] == lemma_cli.ERR_OK


def test_run_ci_requires_smoke_url_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("LEMMA_API_KEY", "test-key")
    args = Namespace(
        project_dir=str(tmp_path),
        framework="both",
        api_base="https://lemma.id",
        skip_health=True,
        skip_smoke=False,
        smoke_url="",
        smoke_method="GET",
        smoke_header="",
        smoke_credential_file="",
        smoke_expect_status=200,
        smoke_timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_ci(args)
    assert code == lemma_cli.EXIT_USAGE


def test_run_smoke_fails_when_header_missing():
    args = Namespace(
        url="https://example.com/protected",
        method="GET",
        header="",
        credential_file="",
        expect_status=200,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_smoke(args)
    assert code == lemma_cli.EXIT_USAGE


def test_run_login_stores_session(monkeypatch, tmp_path):
    cred_file = tmp_path / "credential.json"
    cred_file.write_text(json.dumps({"id": "cred_1", "subject": "did:lemma:ppid_abc"}), encoding="utf-8")
    session_file = tmp_path / "cli_auth.json"

    def fake_http_json_request(**kwargs):
        assert kwargs.get("method") == "POST"
        assert str(kwargs.get("url", "")).endswith("/api/agent/auto-issue")
        assert "X-Lemma-Credential" in (kwargs.get("headers") or {})
        return 200, {"success": True, "token": "lm_agent_test_123456", "token_id": "tok_1", "scope": ["read"]}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file=str(cred_file),
        scope="read",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test",
        allowed_site=[],
        timeout=5.0,
        session_file=str(session_file),
        non_interactive=False,
        no_browser=False,
        login_timeout=30.0,
        json=True,
    )
    code = lemma_cli.run_login(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(session_file.read_text(encoding="utf-8"))
    assert payload["token_id"] == "tok_1"
    assert payload["agent_token"].startswith("lm_agent_")


def test_run_login_allows_issue_json_and_extra_headers(monkeypatch, tmp_path):
    cred_file = tmp_path / "credential.json"
    cred_file.write_text(json.dumps({"id": "cred_1", "subject": "did:lemma:ppid_abc"}), encoding="utf-8")
    session_file = tmp_path / "cli_auth.json"
    captured: dict[str, object] = {}

    def fake_http_json_request(**kwargs):
        captured["headers"] = kwargs.get("headers") or {}
        captured["json_body"] = kwargs.get("json_body") or {}
        return 200, {"success": True, "token": "lm_agent_test_123456", "token_id": "tok_2", "scope": ["admin"]}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file=str(cred_file),
        scope="read,write",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test",
        allowed_site=[],
        issue_json='{"ttl_hours": 24, "allowed_sites": ["acme.example"]}',
        extra_header=["X-Trace-Id: test-123"],
        timeout=5.0,
        session_file=str(session_file),
        non_interactive=False,
        no_browser=False,
        login_timeout=30.0,
        json=True,
    )
    code = lemma_cli.run_login(args)
    assert code == lemma_cli.EXIT_OK
    headers = captured["headers"]
    assert headers["X-Trace-Id"] == "test-123"
    body = captured["json_body"]
    assert body["ttl_hours"] == 24
    assert body["allowed_sites"] == ["acme.example"]


def test_run_login_includes_delegation_fields_in_issue_payload(monkeypatch, tmp_path):
    cred_file = tmp_path / "credential.json"
    cred_file.write_text(json.dumps({"id": "cred_1", "subject": "did:lemma:ppid_abc"}), encoding="utf-8")
    session_file = tmp_path / "cli_auth.json"
    captured: dict[str, object] = {}

    def fake_http_json_request(**kwargs):
        captured["json_body"] = kwargs.get("json_body") or {}
        return 200, {"success": True, "token": "lm_agent_test_123456", "token_id": "tok_2", "scope": ["admin"]}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file=str(cred_file),
        scope="read,write",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test",
        allowed_site=[],
        issue_json="",
        delegation_reason="approve deployment",
        delegation_id="dlg_test_1",
        acting_for_ppid="did:lemma:ppid_actor",
        requested_by_ppid="did:lemma:ppid_requester",
        delegated_by_user_ref="user_admin_001",
        acting_for_user_ref="user_actor_002",
        requested_by_user_ref="user_requester_003",
        extra_header=[],
        timeout=5.0,
        session_file=str(session_file),
        non_interactive=False,
        no_browser=False,
        login_timeout=30.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_login(args)
    assert code == lemma_cli.EXIT_OK
    body = captured["json_body"]
    assert body["delegation_reason"] == "approve deployment"
    assert body["delegation_id"] == "dlg_test_1"
    assert body["acting_for_ppid"] == "did:lemma:ppid_actor"
    assert body["requested_by_ppid"] == "did:lemma:ppid_requester"
    assert body["delegated_by_user_ref"] == "user_admin_001"
    assert body["acting_for_user_ref"] == "user_actor_002"
    assert body["requested_by_user_ref"] == "user_requester_003"


def test_run_login_dry_run_does_not_write_session(monkeypatch, tmp_path):
    cred_file = tmp_path / "credential.json"
    cred_file.write_text(json.dumps({"id": "cred_1", "subject": "did:lemma:ppid_abc"}), encoding="utf-8")
    session_file = tmp_path / "cli_auth.json"

    def fail_http_json_request(**_kwargs):
        raise AssertionError("network should not be called in dry-run")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fail_http_json_request)
    artifact_file = tmp_path / "login-dry-run.json"
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file=str(cred_file),
        scope="read",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test",
        allowed_site=[],
        issue_json="",
        extra_header=[],
        timeout=5.0,
        session_file=str(session_file),
        non_interactive=False,
        no_browser=False,
        login_timeout=30.0,
        dry_run=True,
        dry_run_output=str(artifact_file),
        json=True,
    )
    code = lemma_cli.run_login(args)
    assert code == lemma_cli.EXIT_OK
    assert not session_file.exists()
    assert artifact_file.exists()
    artifact = json.loads(artifact_file.read_text(encoding="utf-8"))
    assert artifact["dry_run"] is True
    assert str(artifact.get("dry_run_output", "")).endswith("login-dry-run.json")


def test_run_login_platform_self_issue_when_header_missing(monkeypatch, tmp_path):
    session_file = tmp_path / "cli_auth.json"
    calls = []

    def fake_http_json_request(**kwargs):
        calls.append((kwargs.get("method"), kwargs.get("url")))
        method = kwargs.get("method")
        url = str(kwargs.get("url", ""))
        if method == "POST" and url.endswith("/api/v1/iam/admin/self-issue"):
            headers = kwargs.get("headers") or {}
            assert headers.get("Authorization") == "Bearer lemma_key_123"
            body = kwargs.get("json_body") or {}
            assert body.get("site_id") == "lemma.id"
            assert body.get("site_domain") == "lemma.id"
            assert body.get("user_email") == "admin@lemma.id"
            assert body.get("permission_level") == "super_admin"
            return 200, {"success": True, "credential": {"id": "cred_platform_1", "subject": "did:lemma:ppid_abc"}}, None
        if method == "POST" and url.endswith("/api/agent/auto-issue"):
            assert "X-Lemma-Credential" in (kwargs.get("headers") or {})
            return 200, {"success": True, "token": "lm_agent_test_987654", "token_id": "tok_platform", "scope": ["admin"]}, None
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test",
        allowed_site=[],
        platform_api_key="lemma_key_123",
        user_email="admin@lemma.id",
        site_id="lemma.id",
        site_domain="lemma.id",
        permission_level="super_admin",
        timeout=5.0,
        session_file=str(session_file),
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        json=True,
    )
    code = lemma_cli.run_login(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(session_file.read_text(encoding="utf-8"))
    assert payload["token_id"] == "tok_platform"
    assert payload["agent_token"].startswith("lm_agent_")
    assert calls[0][1].endswith("/api/v1/iam/admin/self-issue")
    assert calls[1][1].endswith("/api/agent/auto-issue")


def test_run_login_wallet_unlock_error_includes_next_steps(monkeypatch, tmp_path, capsys):
    cred_file = tmp_path / "credential.json"
    cred_file.write_text(json.dumps({"id": "cred_1", "subject": "did:lemma:ppid_abc"}), encoding="utf-8")
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file=str(cred_file),
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test",
        allowed_site=[],
        issue_json="",
        extra_header=[],
        timeout=5.0,
        session_file=str(tmp_path / "cli_auth.json"),
        non_interactive=False,
        no_browser=False,
        login_timeout=30.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )

    def fake_http_json_request(**kwargs):
        assert str(kwargs.get("url", "")).endswith("/api/agent/auto-issue")
        return 403, {"success": False, "error": "wallet_unlock_required", "message": "Unlock required"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    code = lemma_cli.run_login(args)
    assert code == lemma_cli.EXIT_CHECK_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == lemma_cli.ERR_LOGIN_FAILED
    assert any("Unlock your lemma.id wallet" in step for step in payload.get("next_steps", []))


def test_run_login_browser_flow_when_header_missing(monkeypatch, tmp_path):
    session_file = tmp_path / "cli_auth.json"
    opened: dict[str, str] = {}

    def fake_open(url, **_kwargs):
        opened["url"] = url
        return True

    poll_calls = {"count": 0}

    def fake_http_json_request(**kwargs):
        method = kwargs.get("method")
        url = str(kwargs.get("url", ""))
        assert method == "GET"
        assert "/api/agent/cli-login/poll?state=" in url
        poll_calls["count"] += 1
        if poll_calls["count"] < 2:
            return 200, {"success": True, "completed": False}, None
        return 200, {
            "success": True,
            "completed": True,
            "token": "lm_agent_browser_123",
            "token_id": "tok_browser",
            "scope": ["read", "admin"],
            "allowed_sites": ["lemma.id"],
            "authorized_by": "did:lemma:ppid_abc",
            "expires_at": "2026-03-03T00:00:00Z",
        }, None

    monkeypatch.setattr(lemma_cli.webbrowser, "open", fake_open)
    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    monkeypatch.setattr(lemma_cli.time, "sleep", lambda _x: None)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,admin",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test browser",
        allowed_site=[],
        platform_api_key="",
        user_email="",
        site_id="lemma.id",
        site_domain="lemma.id",
        permission_level="super_admin",
        timeout=5.0,
        session_file=str(session_file),
        non_interactive=False,
        no_browser=False,
        login_timeout=10.0,
        json=True,
    )
    code = lemma_cli.run_login(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(session_file.read_text(encoding="utf-8"))
    assert payload["token_id"] == "tok_browser"
    assert payload["agent_token"].startswith("lm_agent_")
    assert opened["url"].startswith("https://lemma.id/api/agent/cli-login/complete?")


def test_run_site_create_requires_auth_when_no_session(tmp_path):
    args = Namespace(
        api_base="https://lemma.id",
        name="Demo Site",
        domain="demo.example",
        environment="development",
        agent_token="",
        api_key="",
        timeout=5.0,
        session_file=str(tmp_path / "missing_auth.json"),
        json=True,
    )
    code = lemma_cli.run_site_create(args)
    assert code == lemma_cli.EXIT_USAGE


def test_run_site_create_allows_payload_override_and_extra_header(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_build_sensitive_headers(**_kwargs):
        return {"X-Agent-Token": "lm_agent_ok"}, None

    def fake_http_json_request(**kwargs):
        captured["headers"] = kwargs.get("headers") or {}
        captured["json_body"] = kwargs.get("json_body") or {}
        return 201, {"success": True, "site": {"site_id": "site_custom"}}, None

    monkeypatch.setattr(lemma_cli, "_build_sensitive_headers", fake_build_sensitive_headers)
    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        name="Default Name",
        domain="default.example",
        environment="development",
        payload_json='{"domain":"custom.example","plan":"starter"}',
        extra_header=["X-Tenant: acme"],
        agent_token="",
        api_key="",
        timeout=5.0,
        session_file=str(tmp_path / "auth.json"),
        json=True,
    )
    code = lemma_cli.run_site_create(args)
    assert code == lemma_cli.EXIT_OK
    body = captured["json_body"]
    assert body["domain"] == "custom.example"
    assert body["plan"] == "starter"
    headers = captured["headers"]
    assert headers["X-Tenant"] == "acme"


def test_run_site_create_dry_run_without_auth(monkeypatch, tmp_path):
    def fail_http_json_request(**_kwargs):
        raise AssertionError("network should not be called in dry-run")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fail_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        name="Default Name",
        domain="default.example",
        environment="development",
        payload_json='{"plan":"starter"}',
        extra_header=["X-Tenant: acme"],
        agent_token="",
        api_key="",
        timeout=5.0,
        session_file=str(tmp_path / "auth.json"),
        dry_run=True,
        dry_run_output=str(tmp_path / "site-create-dry-run.json"),
        json=True,
    )
    code = lemma_cli.run_site_create(args)
    assert code == lemma_cli.EXIT_OK


def test_run_key_bootstrap_dry_run_without_auth(monkeypatch, tmp_path):
    def fail_http_json_request(**_kwargs):
        raise AssertionError("network should not be called in dry-run")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fail_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        site_id="site_demo",
        name="CLI Key",
        key_type="live",
        permissions="read,write",
        payload_json="",
        extra_header=[],
        env_file="",
        overwrite_env=False,
        agent_token="",
        api_key="",
        timeout=5.0,
        session_file=str(tmp_path / "auth.json"),
        dry_run=True,
        dry_run_output=str(tmp_path / "key-bootstrap-dry-run.json"),
        json=True,
    )
    code = lemma_cli.run_key_bootstrap(args)
    assert code == lemma_cli.EXIT_OK


def test_run_logout_removes_session(tmp_path):
    session_file = tmp_path / "cli_auth.json"
    session_file.write_text(json.dumps({"agent_token": "lm_agent_test"}), encoding="utf-8")
    args = Namespace(session_file=str(session_file), json=True)
    code = lemma_cli.run_logout(args)
    assert code == lemma_cli.EXIT_OK
    assert not session_file.exists()


def test_run_auth_status_valid(monkeypatch, tmp_path):
    session_file = tmp_path / "cli_auth.json"
    session_file.write_text(
        json.dumps({"api_base": "https://lemma.id", "agent_token": "lm_agent_valid"}),
        encoding="utf-8",
    )

    def fake_http_json_request(**kwargs):
        assert kwargs.get("method") == "GET"
        assert str(kwargs.get("url", "")).endswith("/api/agent/validate")
        return 200, {"valid": True, "token_id": "tok_live"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(api_base="", timeout=5.0, session_file=str(session_file), json=True)
    code = lemma_cli.run_auth_status(args)
    assert code == lemma_cli.EXIT_OK


def test_run_safety_status_safe(monkeypatch, capsys):
    def fake_http_json_request(**kwargs):
        assert kwargs.get("method") == "GET"
        assert str(kwargs.get("url", "")).endswith("/aim/health")
        return 200, {
            "ok": True,
            "auth_mode": "proof",
            "local_proof_enforcement": True,
            "runtime_authorize_required_tiers": ["critical"],
            "online_check_on_stale_noncritical": False,
            "sync": {"enabled": True, "last_sync_error": None},
        }, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        firewall_url="http://127.0.0.1:8787",
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_safety_status(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "safety-status"
    assert payload["safety_status"] == "safe"
    assert payload["error_code"] == lemma_cli.ERR_OK


def test_run_safety_status_degraded(monkeypatch, capsys):
    def fake_http_json_request(**kwargs):
        assert kwargs.get("method") == "GET"
        assert str(kwargs.get("url", "")).endswith("/aim/health")
        return 200, {
            "ok": True,
            "auth_mode": "proof",
            "local_proof_enforcement": False,
            "runtime_authorize_required_tiers": [],
            "online_check_on_stale_noncritical": True,
            "sync": {"enabled": False, "last_sync_error": "revocation_sync_failed"},
        }, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        firewall_url="http://127.0.0.1:8787",
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_safety_status(args)
    assert code == lemma_cli.EXIT_CHECK_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "safety-status"
    assert payload["safety_status"] == "degraded"
    assert payload["error_code"] == lemma_cli.ERR_SAFETY_DEGRADED
    assert "local_proof_enforcement_disabled" in payload["reasons"]


def test_run_session_status_locked_returns_check_failed(monkeypatch):
    def fake_http_json_request(**kwargs):
        assert kwargs.get("method") == "POST"
        assert str(kwargs.get("url", "")).endswith("/api/wallet/session-sync")
        assert kwargs.get("headers", {}).get("Origin") == "https://lemma.id"
        return 401, {"success": False, "error": "no_session", "unlock_url": "https://lemma.id/unlock"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_session_status(args)
    assert code == lemma_cli.EXIT_CHECK_FAILED


def test_run_session_status_unlocked_returns_ok(monkeypatch):
    def fake_http_json_request(**_kwargs):
        return 200, {
            "success": True,
            "session": {
                "wallet_id": "wallet_123",
                "unlocked_at": 1700000000,
                "expires_at": 1700003600,
                "time_remaining": 3600,
            },
        }, None

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_session_status(args)
    assert code == lemma_cli.EXIT_OK


def test_run_session_start_opens_browser_when_locked(monkeypatch):
    captured: dict[str, str] = {}

    def fake_http_json_request(**_kwargs):
        return 401, {"success": False, "error": "no_session", "unlock_url": "https://lemma.id/unlock"}, None

    def fake_open(url):
        captured["url"] = str(url)
        return True

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    monkeypatch.setattr(lemma_cli.webbrowser, "open", fake_open)
    args = Namespace(
        api_base="https://lemma.id",
        no_browser=False,
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_session_start(args)
    assert code == lemma_cli.EXIT_OK
    assert captured["url"] == "https://lemma.id/unlock"


def test_run_session_start_no_browser_does_not_open(monkeypatch):
    def fake_http_json_request(**_kwargs):
        return 401, {"success": False, "error": "no_session", "unlock_url": "https://lemma.id/unlock"}, None

    def fail_open(_url):
        raise AssertionError("browser should not be opened")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    monkeypatch.setattr(lemma_cli.webbrowser, "open", fail_open)
    args = Namespace(
        api_base="https://lemma.id",
        no_browser=True,
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_session_start(args)
    assert code == lemma_cli.EXIT_OK


def test_run_session_link_approves_and_returns_unlock_token(monkeypatch, capsys):
    calls = {"poll": 0, "opened": ""}

    def fake_http_json_request(**kwargs):
        url = str(kwargs.get("url", ""))
        method = str(kwargs.get("method", "")).upper()
        if method == "POST" and url.endswith("/api/wallet/cli-link/start"):
            return 200, {
                "success": True,
                "state": "st_123",
                "approve_url": "https://lemma.id/api/wallet/cli-link/approve?state=st_123",
                "poll_url": "https://lemma.id/api/wallet/cli-link/poll?state=st_123",
            }, None
        if method == "GET" and "/api/wallet/cli-link/poll" in url:
            calls["poll"] += 1
            if calls["poll"] < 2:
                return 200, {"success": True, "approved": False, "state": "st_123"}, None
            return 200, {
                "success": True,
                "approved": True,
                "state": "st_123",
                "wallet_id": "w_123",
                "unlock_token": "lm_unlock_abc",
            }, None
        raise AssertionError(f"unexpected call: {method} {url}")

    def fake_open(url, **_kwargs):
        calls["opened"] = str(url)
        return True

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    monkeypatch.setattr(lemma_cli.webbrowser, "open", fake_open)
    monkeypatch.setattr(lemma_cli.time, "sleep", lambda _seconds: None)
    args = Namespace(
        api_base="https://lemma.id",
        requested_scope="wallet:revoke",
        no_browser=False,
        poll_interval=0.1,
        link_timeout=5.0,
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_session_link(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "session-link"
    assert payload["unlock_token"] == "lm_unlock_abc"
    assert payload["wallet_id"] == "w_123"
    assert "cli-link/approve" in calls["opened"]


def test_run_session_link_times_out_when_not_approved(monkeypatch, capsys):
    def fake_http_json_request(**kwargs):
        url = str(kwargs.get("url", ""))
        method = str(kwargs.get("method", "")).upper()
        if method == "POST" and url.endswith("/api/wallet/cli-link/start"):
            return 200, {
                "success": True,
                "state": "st_123",
                "approve_url": "https://lemma.id/api/wallet/cli-link/approve?state=st_123",
                "poll_url": "https://lemma.id/api/wallet/cli-link/poll?state=st_123",
            }, None
        if method == "GET" and "/api/wallet/cli-link/poll" in url:
            return 200, {"success": True, "approved": False, "state": "st_123"}, None
        raise AssertionError(f"unexpected call: {method} {url}")

    # Make time jump forward to force timeout quickly.
    ticks = iter([0.0, 0.0, 10.0]).__next__
    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    monkeypatch.setattr(lemma_cli.time, "time", ticks)
    monkeypatch.setattr(lemma_cli.time, "sleep", lambda _seconds: None)
    args = Namespace(
        api_base="https://lemma.id",
        requested_scope="wallet:revoke",
        no_browser=True,
        poll_interval=0.1,
        link_timeout=5.0,
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_session_link(args)
    assert code == lemma_cli.EXIT_CHECK_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == lemma_cli.ERR_BROWSER_LOGIN_TIMEOUT


def test_run_iam_type_create_success(monkeypatch, tmp_path):
    session_file = tmp_path / "auth.json"
    session_file.write_text(json.dumps({"agent_token": "lm_agent_valid"}), encoding="utf-8")

    def fake_http_json_request(**kwargs):
        method = kwargs.get("method")
        url = str(kwargs.get("url", ""))
        if method == "GET" and url.endswith("/api/agent/validate"):
            return 200, {"valid": True}, None
        if method == "POST" and url.endswith("/api/iam/sites/site_demo/permission-types"):
            return 201, {"success": True, "permission_type": {"name": "admin_access"}}, None
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        site_id="site_demo",
        name="admin_access",
        iam_type="role",
        description="Admin role",
        config='{"scope":["*"]}',
        admin_email="admin@lemma.id",
        agent_token="",
        api_key="",
        timeout=5.0,
        session_file=str(session_file),
        json=True,
    )
    code = lemma_cli.run_iam_type_create(args)
    assert code == lemma_cli.EXIT_OK


def test_run_iam_type_list_success(monkeypatch, tmp_path):
    session_file = tmp_path / "auth.json"
    session_file.write_text(json.dumps({"agent_token": "lm_agent_valid"}), encoding="utf-8")

    def fake_http_json_request(**kwargs):
        method = kwargs.get("method")
        url = str(kwargs.get("url", ""))
        if method == "GET" and url.endswith("/api/agent/validate"):
            return 200, {"valid": True}, None
        if method == "GET" and url.endswith("/api/iam/sites/site_demo/permission-types"):
            return 200, {"success": True, "count": 1, "permission_types": [{"name": "admin_access"}]}, None
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        site_id="site_demo",
        agent_token="",
        api_key="",
        timeout=5.0,
        session_file=str(session_file),
        json=True,
    )
    code = lemma_cli.run_iam_type_list(args)
    assert code == lemma_cli.EXIT_OK


def test_run_key_bootstrap_writes_env(monkeypatch, tmp_path):
    session_file = tmp_path / "auth.json"
    session_file.write_text(json.dumps({"agent_token": "lm_agent_valid"}), encoding="utf-8")
    env_file = tmp_path / ".env"

    def fake_http_json_request(**kwargs):
        method = kwargs.get("method")
        url = kwargs.get("url", "")
        if url.endswith("/api/agent/validate"):
            return 200, {"valid": True}, None
        if method == "POST" and "/api/developer/sites/" in url and url.endswith("/keys"):
            return 200, {"success": True, "key_id": "primary", "key": "lm_demo_key_123", "warning": "shown once"}, None
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        site_id="site_demo",
        name="CLI Key",
        key_type="live",
        permissions="read,write",
        env_file=str(env_file),
        overwrite_env=True,
        agent_token="",
        api_key="",
        timeout=5.0,
        session_file=str(session_file),
        json=True,
    )
    code = lemma_cli.run_key_bootstrap(args)
    assert code == lemma_cli.EXIT_OK
    env_text = env_file.read_text(encoding="utf-8")
    assert "LEMMA_SITE_ID=site_demo" in env_text
    assert "LEMMA_API_KEY=lm_demo_key_123" in env_text


def test_run_flow_non_interactive_happy_path(monkeypatch, tmp_path, capsys):
    session_file = tmp_path / "flow_auth.json"
    responses = []

    def fake_http_json_request(**kwargs):
        method = kwargs.get("method")
        url = str(kwargs.get("url", ""))
        responses.append((method, url))
        if method == "POST" and url.endswith("/api/v1/iam/admin/self-issue"):
            return 200, {"success": True, "credential": {"id": "cred_flow_1", "subject": "did:lemma:ppid_abc"}}, None
        if method == "POST" and url.endswith("/api/agent/auto-issue"):
            return 200, {"success": True, "token": "lm_agent_flow_123456", "token_id": "tok_flow", "scope": ["admin"]}, None
        if method == "GET" and url.endswith("/api/agent/validate"):
            return 200, {"valid": True, "token_id": "tok_flow"}, None
        if method == "POST" and url.endswith("/api/developer/sites"):
            return 201, {"success": True, "site": {"site_id": "site_created_1"}}, None
        if method == "POST" and url.endswith("/api/developer/sites/site_created_1/keys"):
            return 200, {"success": True, "key_id": "primary", "key": "lm_demo_key_flow"}, None
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)

    args = Namespace(
        project_dir=str(tmp_path),
        site_id="lemma.id",
        site_domain="lemma.id",
        new_site_domain="newsite.example",
        new_site_name="New Site",
        framework="both",
        force=False,
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test flow",
        allowed_site=[],
        platform_api_key="lemma_key_123",
        user_email="admin@lemma.id",
        permission_level="super_admin",
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        environment="development",
        bootstrap_site_id="",
        bootstrap_key_name="CLI Flow Key",
        key_type="live",
        permissions="read,write",
        env_file="",
        overwrite_env=False,
        timeout=5.0,
        session_file=str(session_file),
        json=True,
    )
    code = lemma_cli.run_flow(args)
    assert code == lemma_cli.EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "flow"
    assert payload["error_code"] == lemma_cli.ERR_OK
    assert payload["ok"] is True
    step_names = [step["step"] for step in payload["steps"]]
    assert step_names == ["setup", "login", "site-create", "issue", "validate"]
    assert (tmp_path / ".lemma" / "config.json").exists()
    assert session_file.exists()
    assert any(url.endswith("/api/developer/sites/site_created_1/keys") for _, url in responses)


def test_run_flow_preserves_upstream_error_code(monkeypatch, tmp_path, capsys):
    def fake_http_json_request(**kwargs):
        method = kwargs.get("method")
        url = str(kwargs.get("url", ""))
        if method == "POST" and url.endswith("/api/v1/iam/admin/self-issue"):
            return 401, {"success": False, "message": "bad api key"}, None
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)

    args = Namespace(
        project_dir=str(tmp_path),
        site_id="lemma.id",
        site_domain="lemma.id",
        new_site_domain="",
        new_site_name="",
        framework="both",
        force=False,
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test flow",
        allowed_site=[],
        platform_api_key="bad_key",
        user_email="admin@lemma.id",
        permission_level="super_admin",
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        environment="development",
        bootstrap_site_id="",
        bootstrap_key_name="CLI Flow Key",
        key_type="live",
        permissions="read,write",
        env_file="",
        overwrite_env=False,
        timeout=5.0,
        session_file=str(tmp_path / "flow_auth.json"),
        json=True,
    )
    code = lemma_cli.run_flow(args)
    assert code == lemma_cli.EXIT_CHECK_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "flow"
    assert payload["failed_step"] == "login"
    assert payload["error_code"] == lemma_cli.ERR_PLATFORM_ISSUE_FAILED


def test_run_flow_supports_skipping_steps(tmp_path, capsys):
    args = Namespace(
        project_dir=str(tmp_path),
        site_id="lemma.id",
        site_domain="lemma.id",
        new_site_domain="",
        new_site_name="",
        framework="both",
        force=False,
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test flow",
        allowed_site=[],
        platform_api_key="",
        user_email="",
        permission_level="super_admin",
        issue_json="",
        site_create_json="",
        key_bootstrap_json="",
        extra_header=[],
        skip_setup=True,
        skip_login=True,
        skip_site_create=True,
        skip_issue=True,
        skip_validate=True,
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        environment="development",
        bootstrap_site_id="",
        bootstrap_key_name="CLI Flow Key",
        key_type="live",
        permissions="read,write",
        env_file="",
        overwrite_env=False,
        timeout=5.0,
        session_file=str(tmp_path / "flow_auth.json"),
        json=True,
    )
    code = lemma_cli.run_flow(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    step_names = [step["step"] for step in payload["steps"]]
    assert step_names == ["setup", "login", "site-create", "issue", "validate"]
    assert all(bool((step["report"] or {}).get("skipped")) for step in payload["steps"])


def test_run_flow_dry_run_executes_without_network(monkeypatch, tmp_path, capsys):
    def fail_http_json_request(**_kwargs):
        raise AssertionError("network should not be called in dry-run")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fail_http_json_request)
    args = Namespace(
        project_dir=str(tmp_path),
        site_id="lemma.id",
        site_domain="lemma.id",
        new_site_domain="newsite.example",
        new_site_name="New Site",
        framework="both",
        force=False,
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="test flow",
        allowed_site=[],
        platform_api_key="",
        user_email="",
        permission_level="super_admin",
        issue_json="",
        site_create_json="",
        key_bootstrap_json="",
        extra_header=["X-Test: dry-run"],
        skip_setup=False,
        skip_login=False,
        skip_site_create=False,
        skip_issue=False,
        skip_validate=False,
        dry_run=True,
        dry_run_output=str(tmp_path / "flow-dry-run.json"),
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        environment="development",
        bootstrap_site_id="",
        bootstrap_key_name="CLI Flow Key",
        key_type="live",
        permissions="read,write",
        env_file="",
        overwrite_env=False,
        timeout=5.0,
        session_file=str(tmp_path / "flow_auth.json"),
        json=True,
    )
    code = lemma_cli.run_flow(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["ok"] is True
    artifact = json.loads((tmp_path / "flow-dry-run.json").read_text(encoding="utf-8"))
    assert artifact["command"] == "flow"
    assert artifact["dry_run"] is True


def test_run_authorize_agent_happy_path(monkeypatch, tmp_path, capsys):
    session_file = tmp_path / "auth.json"
    cred_file = tmp_path / "credential.json"
    cred_file.write_text(json.dumps({"id": "cred_1", "subject": "did:lemma:ppid_abc"}), encoding="utf-8")

    def fake_http_json_request(**kwargs):
        method = kwargs.get("method")
        url = str(kwargs.get("url", ""))
        if method == "POST" and url.endswith("/api/agent/auto-issue"):
            return 200, {"success": True, "token": "lm_agent_authz_123", "token_id": "tok_authz", "scope": ["admin"]}, None
        if method == "GET" and url.endswith("/api/agent/validate"):
            return 200, {"valid": True, "token_id": "tok_authz"}, None
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file=str(cred_file),
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-cli",
        task="authorize test",
        allowed_site=[],
        platform_api_key="",
        user_email="",
        site_id="lemma.id",
        site_domain="lemma.id",
        permission_level="super_admin",
        issue_json="",
        extra_header=[],
        non_interactive=False,
        no_browser=False,
        login_timeout=30.0,
        dry_run=False,
        dry_run_output="",
        timeout=5.0,
        session_file=str(session_file),
        json=True,
    )
    code = lemma_cli.run_authorize_agent(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "authorize-agent"
    assert payload["ok"] is True
    assert [step["step"] for step in payload["steps"]] == ["login", "validate"]
    assert payload["token_id"] == "tok_authz"


def test_run_setup_firewall_happy_path_runs_conformance(monkeypatch, tmp_path, capsys):
    session_file = tmp_path / "firewall_auth.json"
    session_file.write_text(json.dumps({"agent_token": "lm_agent_firewall_token"}), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_invoke(handler, _args):
        name = handler.__name__
        if name == "run_verify":
            return lemma_cli.EXIT_OK, {"command": "verify", "ok": True}
        if name == "run_authorize_agent":
            return lemma_cli.EXIT_OK, {"command": "authorize-agent", "ok": True, "token_id": "tok_firewall"}
        if name == "run_auth_status":
            return lemma_cli.EXIT_OK, {"command": "auth-status", "ok": True, "validation_status": 200}
        raise AssertionError(f"unexpected handler {name}")

    def fake_run_external_command(**kwargs):
        captured.update(kwargs)
        return 0, "PASS Lemma Firewall conformance", ""

    monkeypatch.setattr(lemma_cli, "_invoke_handler_capture_report", fake_invoke)
    monkeypatch.setattr(lemma_cli, "_run_external_command", fake_run_external_command)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-firewall-cli",
        task="Lemma Firewall onboarding session",
        allowed_site=[],
        platform_api_key="",
        user_email="",
        site_id="lemma.id",
        site_domain="lemma.id",
        permission_level="super_admin",
        issue_json="",
        delegation_reason="",
        delegation_id="",
        acting_for_ppid="",
        requested_by_ppid="",
        delegated_by_user_ref="",
        acting_for_user_ref="",
        requested_by_user_ref="",
        extra_header=[],
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        agent_token="",
        firewall_audience="lemma-firewall",
        conformance_command="node mcp-server/run-lemma-firewall-conformance.js",
        conformance_workdir=".",
        conformance_timeout=60.0,
        skip_conformance=False,
        dry_run=False,
        dry_run_output="",
        timeout=5.0,
        session_file=str(session_file),
        json=True,
    )
    code = lemma_cli.run_setup_firewall(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "setup-firewall"
    assert payload["ok"] is True
    assert [step["step"] for step in payload["steps"]] == ["verify", "authorize", "validate", "conformance"]
    env_overrides = captured["env_overrides"]
    assert env_overrides["LEMMA_AGENT_TOKEN"] == "lm_agent_firewall_token"
    assert env_overrides["LEMMA_FIREWALL_REQUIRED_AUDIENCE"] == "lemma-firewall"


def test_run_setup_firewall_conformance_failure(monkeypatch, tmp_path, capsys):
    session_file = tmp_path / "firewall_auth.json"
    session_file.write_text(json.dumps({"agent_token": "lm_agent_firewall_token"}), encoding="utf-8")

    def fake_invoke(handler, _args):
        name = handler.__name__
        if name in {"run_verify", "run_authorize_agent", "run_auth_status"}:
            return lemma_cli.EXIT_OK, {"command": name, "ok": True}
        raise AssertionError(f"unexpected handler {name}")

    def fake_run_external_command(**_kwargs):
        return 1, "FAIL Lemma Firewall conformance", "conformance failed"

    monkeypatch.setattr(lemma_cli, "_invoke_handler_capture_report", fake_invoke)
    monkeypatch.setattr(lemma_cli, "_run_external_command", fake_run_external_command)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-firewall-cli",
        task="Lemma Firewall onboarding session",
        allowed_site=[],
        platform_api_key="",
        user_email="",
        site_id="lemma.id",
        site_domain="lemma.id",
        permission_level="super_admin",
        issue_json="",
        delegation_reason="",
        delegation_id="",
        acting_for_ppid="",
        requested_by_ppid="",
        delegated_by_user_ref="",
        acting_for_user_ref="",
        requested_by_user_ref="",
        extra_header=[],
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        agent_token="",
        firewall_audience="lemma-firewall",
        conformance_command="node mcp-server/run-lemma-firewall-conformance.js",
        conformance_workdir=".",
        conformance_timeout=60.0,
        skip_conformance=False,
        dry_run=False,
        dry_run_output="",
        timeout=5.0,
        session_file=str(session_file),
        json=True,
    )
    code = lemma_cli.run_setup_firewall(args)
    assert code == lemma_cli.EXIT_CHECK_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "setup-firewall"
    assert payload["ok"] is False
    assert payload["failed_step"] == "conformance"


def test_run_setup_firewall_skip_conformance(monkeypatch, tmp_path, capsys):
    def fake_invoke(handler, _args):
        name = handler.__name__
        if name in {"run_verify", "run_authorize_agent", "run_auth_status"}:
            return lemma_cli.EXIT_OK, {"command": name, "ok": True}
        raise AssertionError(f"unexpected handler {name}")

    def fail_external(**_kwargs):
        raise AssertionError("external command should be skipped")

    monkeypatch.setattr(lemma_cli, "_invoke_handler_capture_report", fake_invoke)
    monkeypatch.setattr(lemma_cli, "_run_external_command", fail_external)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-firewall-cli",
        task="Lemma Firewall onboarding session",
        allowed_site=[],
        platform_api_key="",
        user_email="",
        site_id="lemma.id",
        site_domain="lemma.id",
        permission_level="super_admin",
        issue_json="",
        delegation_reason="",
        delegation_id="",
        acting_for_ppid="",
        requested_by_ppid="",
        delegated_by_user_ref="",
        acting_for_user_ref="",
        requested_by_user_ref="",
        extra_header=[],
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        agent_token="",
        firewall_audience="lemma-firewall",
        conformance_command="node mcp-server/run-lemma-firewall-conformance.js",
        conformance_workdir=".",
        conformance_timeout=60.0,
        skip_conformance=True,
        dry_run=False,
        dry_run_output="",
        timeout=5.0,
        session_file=str(tmp_path / "firewall_auth.json"),
        json=True,
    )
    code = lemma_cli.run_setup_firewall(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["skip_conformance"] is True
    conformance_step = payload["steps"][-1]
    assert conformance_step["step"] == "conformance"
    assert bool((conformance_step["report"] or {}).get("skipped")) is True


def test_run_setup_openclaw_happy_path(monkeypatch, tmp_path, capsys):
    class DummyProc:
        def __init__(self):
            self._terminated = False

        def poll(self):
            return None if not self._terminated else 0

        def terminate(self):
            self._terminated = True

        def wait(self, _timeout=None, **_kwargs):
            self._terminated = True
            return 0

        def kill(self):
            self._terminated = True

    proof_payload = {
        "success": True,
        "credential": {"id": "cred_123", "issuer": "did:lemma:issuer_demo", "scope": ["read"]},
    }

    def fake_invoke(handler, _args):
        name = handler.__name__
        if name == "run_session_link":
            return lemma_cli.EXIT_OK, {"ok": True, "unlock_token": "unlock_demo"}
        if name == "run_firewall_connect":
            return lemma_cli.EXIT_OK, {"ok": True, "runtime_id": "openclaw-default"}
        raise AssertionError(f"unexpected handler {name}")

    calls = {"action_count": 0}

    def fake_http_json_request(**kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/aim/health"):
            return 200, {
                "ok": True,
                "local_proof_enforcement": True,
                "sync": {"enabled": True},
                "runtime_authorize_required_tiers": ["critical"],
                "online_check_on_stale_noncritical": False,
            }, None
        if url.endswith("/aim/policy"):
            return 200, {
                "success": True,
                "apis": {
                    "openclaw-demo": {
                        "allowed_methods": ["GET"],
                        "path_prefixes": ["/ok"],
                    }
                },
            }, None
        if "/firewall/openclaw-demo/ok" in url:
            calls["action_count"] += 1
            if calls["action_count"] == 1:
                return 200, {"ok": True}, None
            return 403, {"error": "runtime_inactive_local"}, None
        if url.endswith("/api/wallet/runtimes/openclaw-default/kill"):
            return 200, {"success": True}, None
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(lemma_cli, "_invoke_handler_capture_report", fake_invoke)
    monkeypatch.setattr(lemma_cli, "_issue_wallet_runtime_proof", lambda **kwargs: (proof_payload, None))
    monkeypatch.setattr(lemma_cli, "_http_json_request", fake_http_json_request)
    monkeypatch.setattr(lemma_cli.subprocess, "Popen", lambda *args, **kwargs: DummyProc())

    args = Namespace(
        api_base="https://lemma.id",
        runtime_id="openclaw-default",
        agent_id="main",
        workspace_id="default",
        display_name="OpenClaw Runtime",
        proof_file=str(tmp_path / ".lemma-proof.json"),
        site_id="lemma.id",
        bind_host="127.0.0.1",
        firewall_port=8787,
        policy_profile="runtime_default_v1",
        root_type="passkey_root",
        org_id="org_default",
        environment="prod",
        no_browser=True,
        link_timeout=30.0,
        timeout=5.0,
        json=True,
    )

    code = lemma_cli.run_setup_openclaw(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "setup-openclaw"
    assert payload["ok"] is True
    assert payload["installed_or_prereqs_ok"] is True
    assert payload["browser_approved"] is True
    assert payload["firewall_started"] is True
    assert payload["protected_action_allowed"] is True
    assert payload["runtime_kill_succeeded"] is True
    assert payload["post_kill_action_denied"] is True
    assert Path(args.proof_file).exists()


def test_run_setup_firewall_softens_verify_missing_platform_key(monkeypatch, tmp_path, capsys):
    def fake_invoke(handler, _args):
        name = handler.__name__
        if name == "run_verify":
            return lemma_cli.EXIT_CHECK_FAILED, {
                "command": "verify",
                "ok": False,
                "error_code": lemma_cli.ERR_EXPECTED_STATUS_MISMATCH,
                "checks": [
                    {
                        "name": "platform_api_key_present",
                        "ok": False,
                        "message": "missing platform API key env",
                    }
                ],
            }
        if name in {"run_authorize_agent", "run_auth_status"}:
            return lemma_cli.EXIT_OK, {"command": name, "ok": True}
        raise AssertionError(f"unexpected handler {name}")

    def fail_external(**_kwargs):
        raise AssertionError("external command should be skipped")

    monkeypatch.setattr(lemma_cli, "_invoke_handler_capture_report", fake_invoke)
    monkeypatch.setattr(lemma_cli, "_run_external_command", fail_external)
    args = Namespace(
        api_base="https://lemma.id",
        header="",
        credential_file="",
        scope="read,write,admin",
        ttl_hours=8,
        agent_name="lemma-firewall-cli",
        task="Lemma Firewall onboarding session",
        allowed_site=[],
        platform_api_key="",
        user_email="",
        site_id="lemma.id",
        site_domain="lemma.id",
        permission_level="super_admin",
        issue_json="",
        delegation_reason="",
        delegation_id="",
        acting_for_ppid="",
        requested_by_ppid="",
        delegated_by_user_ref="",
        acting_for_user_ref="",
        requested_by_user_ref="",
        extra_header=[],
        non_interactive=True,
        no_browser=True,
        login_timeout=30.0,
        agent_token="",
        firewall_audience="lemma-firewall",
        conformance_command="node mcp-server/run-lemma-firewall-conformance.js",
        conformance_workdir=".",
        conformance_timeout=60.0,
        skip_conformance=True,
        dry_run=False,
        dry_run_output="",
        timeout=5.0,
        session_file=str(tmp_path / "firewall_auth.json"),
        json=True,
    )
    code = lemma_cli.run_setup_firewall(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    verify_step = payload["steps"][0]
    assert verify_step["step"] == "verify"
    assert bool((verify_step["report"] or {}).get("soft_failed")) is True


def test_run_incident_bundle_dry_run_writes_artifact(monkeypatch, tmp_path, capsys):
    def fail_http(**_kwargs):
        raise AssertionError("network should not be called in dry-run")

    monkeypatch.setattr(lemma_cli, "_http_json_request_with_headers", fail_http)
    dry_output = tmp_path / "incident-dry-run.json"
    args = Namespace(
        api_base="https://lemma.id",
        agent_token="",
        session_file="",
        output_dir=str(tmp_path),
        bundle_label="incident-bundle",
        audit_limit=10,
        include_deny_probe=False,
        timeout=5.0,
        dry_run=True,
        dry_run_output=str(dry_output),
        json=True,
    )
    code = lemma_cli.run_incident_bundle(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "incident-bundle"
    assert payload["dry_run"] is True
    assert dry_output.exists()


def test_run_incident_bundle_collects_decision_receipts(monkeypatch, tmp_path, capsys):
    session_file = tmp_path / "cli_auth.json"
    session_file.write_text(json.dumps({"agent_token": "lm_agent_demo_token"}), encoding="utf-8")

    calls = {"count": 0}

    def fake_http_json_request_with_headers(**kwargs):
        calls["count"] += 1
        url = str(kwargs.get("url", ""))
        if url.endswith("/api/agent/validate"):
            return 200, {"valid": True, "token_id": "tok_1"}, {"X-Lemma-Decision-Id": "dec_validate"}, None
        if "/api/developer/sites" in url:
            token = (kwargs.get("headers") or {}).get("X-Agent-Token", "")
            if token == "lm_agent_invalid_incident_probe":
                return 401, {"error": "invalid_token"}, {"X-Lemma-Decision-Id": "dec_deny"}, None
            return 200, {"success": True, "entries": []}, {"X-Lemma-Decision-Id": "dec_allow"}, None
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(lemma_cli, "_http_json_request_with_headers", fake_http_json_request_with_headers)
    monkeypatch.setattr(
        lemma_cli,
        "_check_wallet_unlock_status",
        lambda _api_base, _timeout: {"state": "locked", "status_code": 401, "unlock_url": "https://lemma.id/wallet/unlock"},
    )
    args = Namespace(
        api_base="https://lemma.id",
        agent_token="",
        session_file=str(session_file),
        output_dir=str(tmp_path),
        bundle_label="incident-bundle",
        audit_limit=10,
        decision_probe_path="/api/developer/sites",
        include_deny_probe=True,
        timeout=5.0,
        dry_run=False,
        dry_run_output="",
        json=True,
    )
    code = lemma_cli.run_incident_bundle(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "incident-bundle"
    assert payload["allow_decision_id"] == "dec_allow"
    assert payload["deny_probe_included"] is True
    assert calls["count"] >= 3
    bundle_json = Path(payload["bundle_json"])
    assert bundle_json.exists()


def test_run_authz_latency_passes_budget_with_server_header(monkeypatch, capsys):
    samples = iter([2.1, 2.8, 3.0, 2.5, 3.3, 2.9])

    def fake_http_json_request_with_headers(**_kwargs):
        val = next(samples, 3.0)
        return 200, {"success": True}, {"X-Lemma-Authz-Latency-Ms": str(val)}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request_with_headers", fake_http_json_request_with_headers)
    args = Namespace(
        api_base="https://lemma.id",
        agent_token="lm_agent_demo_token",
        session_file="",
        decision_probe_path="/api/developer/sites",
        requests=4,
        warmup=2,
        budget_p95_ms=5.0,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_authz_latency(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "authz-latency"
    assert payload["budget_passed"] is True
    assert payload["authz_header_samples"] == 4


def test_run_authz_latency_fails_budget(monkeypatch, capsys):
    def fake_http_json_request_with_headers(**_kwargs):
        return 200, {"success": True}, {"X-Lemma-Authz-Latency-Ms": "9.9"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request_with_headers", fake_http_json_request_with_headers)
    args = Namespace(
        api_base="https://lemma.id",
        agent_token="lm_agent_demo_token",
        session_file="",
        decision_probe_path="/api/developer/sites",
        requests=5,
        warmup=0,
        budget_p95_ms=5.0,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_authz_latency(args)
    assert code == lemma_cli.EXIT_CHECK_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "authz-latency"
    assert payload["budget_passed"] is False


def test_run_authz_latency_fails_e2e_budget(monkeypatch, capsys):
    def fake_http_json_request_with_headers(**_kwargs):
        return 200, {"success": True}, {"X-Lemma-Authz-Latency-Ms": "1.0"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request_with_headers", fake_http_json_request_with_headers)
    monkeypatch.setattr(
        lemma_cli.time,
        "perf_counter",
        iter([0.0, 0.20, 0.20, 0.40, 0.40, 0.60, 0.60, 0.80, 0.80, 1.00]).__next__,
    )
    args = Namespace(
        api_base="https://lemma.id",
        agent_token="lm_agent_demo_token",
        session_file="",
        decision_probe_path="/api/developer/sites",
        requests=5,
        warmup=0,
        budget_p95_ms=5.0,
        e2e_budget_p95_ms=150.0,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_authz_latency(args)
    assert code == lemma_cli.EXIT_CHECK_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["budget_passed"] is True
    assert payload["e2e_budget_passed"] is False


def test_run_authz_latency_passes_e2e_budget(monkeypatch, capsys):
    def fake_http_json_request_with_headers(**_kwargs):
        return 200, {"success": True}, {"X-Lemma-Authz-Latency-Ms": "1.2"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request_with_headers", fake_http_json_request_with_headers)
    monkeypatch.setattr(
        lemma_cli.time,
        "perf_counter",
        iter([0.0, 0.05, 0.05, 0.10, 0.10, 0.15, 0.15, 0.20, 0.20, 0.25]).__next__,
    )
    args = Namespace(
        api_base="https://lemma.id",
        agent_token="lm_agent_demo_token",
        session_file="",
        decision_probe_path="/api/developer/sites",
        requests=5,
        warmup=0,
        budget_p95_ms=5.0,
        e2e_budget_p95_ms=100.0,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_authz_latency(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["budget_passed"] is True
    assert payload["e2e_budget_passed"] is True


def test_run_authz_latency_supports_proof_only_mode(monkeypatch, capsys):
    captured = {}

    def fake_http_json_request_with_headers(**kwargs):
        captured.update(kwargs.get("headers") or {})
        return 200, {"success": True}, {"X-Lemma-Authz-Latency-Ms": "1.4"}, None

    monkeypatch.setattr(lemma_cli, "_http_json_request_with_headers", fake_http_json_request_with_headers)
    args = Namespace(
        api_base="https://lemma.id",
        auth_mode="proof",
        agent_token="",
        proof='{"proof_id":"prf_1","scope":["read"]}',
        proof_file="",
        pop="",
        pop_file="",
        pop_agent_key_id="test-key",
        session_file="",
        decision_probe_path="/api/developer/sites",
        requests=2,
        warmup=0,
        budget_p95_ms=5.0,
        e2e_budget_p95_ms=0.0,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_authz_latency(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["proof_supplied"] is True
    assert payload["auth_mode"] == "proof"
    assert "X-Lemma-Proof" in captured
    assert "X-Lemma-PoP" in captured


def test_run_authz_latency_requires_proof_when_proof_mode(monkeypatch, capsys):
    monkeypatch.setattr(
        lemma_cli,
        "_http_json_request_with_headers",
        lambda **_kwargs: (200, {"success": True}, {"X-Lemma-Authz-Latency-Ms": "1.0"}, None),
    )
    args = Namespace(
        api_base="https://lemma.id",
        auth_mode="proof",
        agent_token="",
        proof="",
        proof_file="",
        pop="",
        pop_file="",
        pop_agent_key_id="lemma-cli",
        session_file="",
        decision_probe_path="/api/developer/sites",
        requests=1,
        warmup=0,
        budget_p95_ms=5.0,
        e2e_budget_p95_ms=0.0,
        timeout=5.0,
        json=True,
    )
    code = lemma_cli.run_authz_latency(args)
    assert code == lemma_cli.EXIT_USAGE
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == lemma_cli.ERR_USAGE_MISSING_REQUIRED_ARGS


# ---------------------------------------------------------------------------
# Developer Control Panel: start / stop / replay commands
# ---------------------------------------------------------------------------

def test_start_command_parses_scope_and_ttl():
    parser = lemma_cli.build_parser()
    args = parser.parse_args(["start", "--scope", "read:~/project/**", "--ttl", "30m"])
    assert args.scope == "read:~/project/**"
    assert args.ttl == "30m"
    assert args.handler == lemma_cli.run_start


def test_stop_command_parser():
    parser = lemma_cli.build_parser()
    args = parser.parse_args(["stop"])
    assert args.handler == lemma_cli.run_stop


def test_replay_command_parser():
    parser = lemma_cli.build_parser()
    args = parser.parse_args(["replay", "--last"])
    assert args.last is True
    assert args.handler == lemma_cli.run_replay


def test_replay_command_reads_jsonl(tmp_path, monkeypatch, capsys):
    log_file = tmp_path / "session_abc.jsonl"
    decisions = [
        {"allowed": True, "action": "file.read", "resource": "/x.py", "timestamp": 1000},
        {"allowed": False, "action": "shell.exec", "resource": "rm -rf /", "error": "action_not_granted", "timestamp": 1001},
    ]
    log_file.write_text("\n".join(json.dumps(d) for d in decisions) + "\n")

    active = tmp_path / "_active.json"
    active.write_text(json.dumps({"log_file": str(log_file)}))
    monkeypatch.setattr(lemma_cli, "_ACTIVE_SESSION_FILE", active)

    args = Namespace(json=True, last=True, session_id="")
    code = lemma_cli.run_replay(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_decisions"] == 2
    assert payload["allowed"] == 1
    assert payload["denied"] == 1


def test_stop_command_revokes_and_kills(tmp_path, monkeypatch, capsys):
    active = tmp_path / "_active.json"
    active.write_text(json.dumps({
        "session_id": "session_test",
        "pid": 999999,
        "port": 19999,
    }))
    monkeypatch.setattr(lemma_cli, "_ACTIVE_SESSION_FILE", active)

    args = Namespace(json=True)
    code = lemma_cli.run_stop(args)
    assert code == lemma_cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["stopped"] is True
    assert not active.exists()
