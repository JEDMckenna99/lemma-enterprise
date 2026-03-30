"""Minimal smoke tests that run quickly and do not require external services."""

import importlib
import os

from api.validation import ValidationError, validate_email, validate_site_id
from auth.permissions import normalize_scopes


def _load_session_manager():
    """Load session manager with a deterministic test secret."""
    previous = os.environ.get("SESSION_SECRET")
    os.environ["SESSION_SECRET"] = "test-session-secret"
    try:
        import auth.session_manager as sm

        return importlib.reload(sm)
    finally:
        if previous is None:
            os.environ.pop("SESSION_SECRET", None)
        else:
            os.environ["SESSION_SECRET"] = previous


def test_site_id_normalization():
    assert validate_site_id("EXAMPLE.COM") == "example.com"


def test_site_id_rejects_invalid_format():
    try:
        validate_site_id("bad site id")
        assert False, "invalid site_id should raise ValidationError"
    except ValidationError as exc:
        assert exc.code == "invalid_format"


def test_email_validation_lowercases():
    assert validate_email("User@Example.com") == "user@example.com"


def test_scope_normalization_aliases():
    assert normalize_scopes(["super_admin", "read"]) == ["admin", "read"]


def test_session_token_roundtrip_and_tamper_detection():
    sm = _load_session_manager()
    sm._is_session_revoked = lambda *_args, **_kwargs: False

    token = sm.generate_session_token("wallet_test", 1700000000000)
    data = sm.validate_session_token(token)
    assert data is not None
    assert data["wallet_id"] == "wallet_test"

    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert sm.validate_session_token(tampered) is None