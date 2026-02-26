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

