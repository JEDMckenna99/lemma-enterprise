from api.authz_policy import get_error_defaults, get_policy_for_request


def test_get_policy_for_request_known_route():
    policy = get_policy_for_request("GET", "/api/developer/sites")
    assert policy is not None
    assert policy.required_scope == "read"
    assert "user_lemma" in policy.allowed_principals


def test_get_error_defaults_known_and_unknown_codes():
    status, message = get_error_defaults("missing_lemma_header")
    assert status == 401
    assert "X-Lemma-Credential" in message

    unknown_status, unknown_message = get_error_defaults("nonexistent_code")
    assert unknown_status == 401
    assert unknown_message == "Authentication required"


def test_get_policy_for_request_template_route_match():
    policy = get_policy_for_request("POST", "/api/developer/sites/site_abc/keys/123/rotate")
    assert policy is not None
    assert policy.required_scope == "admin"
    assert policy.site_binding_required is True


def test_core_protected_route_coverage():
    # Core protected routes that should remain mapped in unified policy.
    expected_routes = [
        ("GET", "/api/developer/stats"),
        ("GET", "/api/developer/sites"),
        ("POST", "/api/developer/sites"),
        ("GET", "/api/developer/sites/site_1"),
        ("POST", "/api/developer/sites/site_1/bootstrap-admin"),
        ("POST", "/api/developer/sites/site_1/admin-transfer-token"),
        ("GET", "/api/developer/sites/site_1/users"),
        ("POST", "/api/developer/sites/site_1/users"),
        ("PUT", "/api/developer/sites/site_1/users/did:lemma:ppid_abc"),
        ("POST", "/api/developer/sites/site_1/users/did:lemma:ppid_abc/revoke"),
        ("POST", "/api/developer/sites/site_1/users/did:lemma:ppid_abc/unblock"),
        ("GET", "/api/developer/sites/site_1/permissions"),
        ("POST", "/api/developer/sites/site_1/permissions"),
        ("DELETE", "/api/developer/sites/site_1/permissions/admin_access"),
        ("GET", "/api/customer/profile"),
        ("GET", "/api/customer/usage"),
        ("POST", "/api/developer/issue-self-permission"),
        ("GET", "/api/agent/credentials"),
        ("POST", "/api/agent/credentials/issue"),
        ("POST", "/api/auth/introspect"),
        ("POST", "/api/auth/revoke"),
        ("POST", "/api/v1/iam/admin/self-issue"),
    ]

    for method, path in expected_routes:
        policy = get_policy_for_request(method, path)
        assert policy is not None, f"Missing policy for {method} {path}"

