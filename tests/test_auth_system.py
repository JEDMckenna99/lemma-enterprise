"""
Auth System Tests - Rate Limiting, Redis Store, and Passkey Security

Tests for:
1. Rate limiter configuration and decorator
2. Redis store with fallback to in-memory
3. Passkey challenge storage and expiration
4. Agent credential path normalization and validation
5. API key validation security

Run with: python -m pytest tests/test_auth_system.py -v
"""

import pytest
import json
import sys
import os
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================
# RATE LIMITER TESTS
# ============================================

class TestRateLimiterConfiguration:
    """Test rate limiter setup and limit functions."""

    def test_rate_limit_functions_exist(self):
        """Verify all rate limit functions are defined."""
        from auth.rate_limiter import (
            auth_limit,
            registration_limit,
            credential_issue_limit,
            session_limit,
            validation_limit
        )

        assert callable(auth_limit)
        assert callable(registration_limit)
        assert callable(credential_issue_limit)
        assert callable(session_limit)
        assert callable(validation_limit)

    def test_auth_limit_returns_strict_limit(self):
        """Auth endpoints should have strict rate limits."""
        from auth.rate_limiter import auth_limit

        limit = auth_limit()
        assert "10" in limit, "Auth limit should be 10 per minute"
        assert "minute" in limit.lower()

    def test_registration_limit_is_stricter_than_auth(self):
        """Registration should be more limited than auth."""
        from auth.rate_limiter import auth_limit, registration_limit

        auth = auth_limit()
        reg = registration_limit()

        # Extract numbers
        auth_num = int(''.join(c for c in auth.split()[0] if c.isdigit()))
        reg_num = int(''.join(c for c in reg.split()[0] if c.isdigit()))

        assert reg_num <= auth_num, "Registration should be same or stricter than auth"

    def test_credential_issue_limit_is_hourly(self):
        """Credential issuance is expensive, should be hourly limited."""
        from auth.rate_limiter import credential_issue_limit
        from flask import Flask

        app = Flask(__name__)
        # credential_issue_limit() is principal-aware and reads request headers,
        # so it must be evaluated inside a request context.
        with app.test_request_context():
            limit = credential_issue_limit()
        assert "hour" in limit.lower(), "Credential issuance should be hourly limited"

    def test_get_client_identifier_uses_forwarded_for(self):
        """Should use X-Forwarded-For header when present (Heroku)."""
        from auth.rate_limiter import get_client_identifier
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context(
            headers={'X-Forwarded-For': '1.2.3.4, 5.6.7.8'}
        ):
            identifier = get_client_identifier()
            assert identifier == '1.2.3.4', "Should use first IP from X-Forwarded-For"

    def test_create_limiter_uses_redis_when_available(self):
        """Limiter should use Redis storage in production."""
        from auth.rate_limiter import create_limiter, FLASK_LIMITER_AVAILABLE
        from flask import Flask

        app = Flask(__name__)

        if not FLASK_LIMITER_AVAILABLE:
            # Skip if flask_limiter not installed
            pytest.skip("flask_limiter not installed")

        with patch.dict(os.environ, {'REDIS_URL': 'redis://localhost:6379'}):
            limiter = create_limiter(app)
            assert limiter is not None

    def test_rate_limit_decorator_skips_options_requests(self):
        """Rate limiting should not apply to CORS preflight requests."""
        from auth.rate_limiter import rate_limit
        from flask import Flask

        app = Flask(__name__)

        @rate_limit("1 per minute")
        def test_func():
            return "OK"

        # OPTIONS requests should pass through
        with app.test_request_context(method='OPTIONS'):
            # Should not raise even without limiter
            result = test_func()
            assert result == "OK"


# ============================================
# REDIS STORE TESTS
# ============================================

class TestRedisStore:
    """Test Redis store with in-memory fallback."""

    def test_store_and_get_in_memory(self):
        """Test basic store/get without Redis."""
        from auth import redis_store

        # Force in-memory mode
        with patch.object(redis_store, 'get_redis_client', return_value=None):
            redis_store.store("test_key", {"data": "value"}, ttl_seconds=60)
            result = redis_store.get("test_key")

            assert result is not None
            assert result["data"] == "value"

    def test_store_expires_after_ttl(self):
        """Stored values should expire after TTL."""
        from auth import redis_store

        with patch.object(redis_store, 'get_redis_client', return_value=None):
            # Store with 1 second TTL
            redis_store.store("expire_test", {"temp": True}, ttl_seconds=1)

            # Should exist immediately
            assert redis_store.get("expire_test") is not None

            # Wait for expiration
            time.sleep(1.1)

            # Should be gone
            assert redis_store.get("expire_test") is None

    def test_delete_removes_entry(self):
        """Delete should remove stored entry."""
        from auth import redis_store

        with patch.object(redis_store, 'get_redis_client', return_value=None):
            redis_store.store("delete_test", {"data": 1})

            assert redis_store.get("delete_test") is not None

            result = redis_store.delete("delete_test")
            assert result == True

            assert redis_store.get("delete_test") is None

    def test_delete_returns_false_for_missing_key(self):
        """Delete should return False for non-existent keys."""
        from auth import redis_store

        with patch.object(redis_store, 'get_redis_client', return_value=None):
            result = redis_store.delete("nonexistent_key_12345")
            assert result == False

    def test_cleanup_expired_removes_old_entries(self):
        """Cleanup should remove expired entries from memory store."""
        from auth import redis_store

        with patch.object(redis_store, 'get_redis_client', return_value=None):
            # Store with very short TTL
            redis_store.store("cleanup_test", {"old": True}, ttl_seconds=1)

            time.sleep(1.1)

            removed = redis_store.cleanup_expired()
            assert removed >= 1

    def test_is_redis_available_returns_boolean(self):
        """is_redis_available should return True/False."""
        from auth import redis_store

        result = redis_store.is_redis_available()
        assert isinstance(result, bool)

    def test_redis_client_handles_connection_failure(self):
        """Should gracefully handle Redis connection failures."""
        from auth import redis_store
        from api.redis_client import reset_shared_redis_for_tests

        with patch.dict(os.environ, {'REDIS_URL': 'redis://invalid:6379'}):
            reset_shared_redis_for_tests()
            with patch.object(redis_store, 'REDIS_URL', 'redis://invalid:6379'):
                # Should not raise
                redis_store.get_redis_client()
    def test_key_prefixing(self):
        """Keys should be prefixed with 'lemma:'."""
        from auth import redis_store

        # Mock Redis client to capture the key
        mock_redis = Mock()
        mock_redis.setex = Mock()
        mock_redis.get = Mock(return_value=None)

        with patch.object(redis_store, 'get_redis_client', return_value=mock_redis):
            redis_store.store("mykey", {"data": 1})

            # Check the key was prefixed
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == "lemma:mykey"


# ============================================
# PASSKEY CHALLENGE STORAGE TESTS
# ============================================

class TestPasskeyChallengeStorage:
    """Test challenge storage for passkey authentication."""

    def test_challenge_storage_functions_exist(self):
        """Verify challenge storage functions are available."""
        # These are defined in passkey_auth but we test the underlying redis_store
        from auth import redis_store

        assert callable(redis_store.store)
        assert callable(redis_store.get)
        assert callable(redis_store.delete)

    def test_challenge_data_structure(self):
        """Challenge should store required fields."""
        from auth import redis_store
        import base64
        import secrets

        with patch.object(redis_store, 'get_redis_client', return_value=None):
            challenge = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

            challenge_data = {
                'challenge': challenge,
                'user_id': 'user_123',
                'expires': (datetime.utcnow() + timedelta(minutes=5)).isoformat()
            }

            redis_store.store("challenge:passkey_auth_test", challenge_data, ttl_seconds=300)

            retrieved = redis_store.get("challenge:passkey_auth_test")
            assert retrieved is not None
            assert retrieved['challenge'] == challenge
            assert retrieved['user_id'] == 'user_123'
            assert 'expires' in retrieved

    def test_challenge_single_use(self):
        """Challenges should be deleted after use (single-use)."""
        from auth import redis_store

        with patch.object(redis_store, 'get_redis_client', return_value=None):
            redis_store.store("challenge:single_use", {"challenge": "abc123"})

            # First retrieval succeeds
            assert redis_store.get("challenge:single_use") is not None

            # Delete after use
            redis_store.delete("challenge:single_use")

            # Second retrieval fails (replay attack prevention)
            assert redis_store.get("challenge:single_use") is None


# ============================================
# AGENT CREDENTIAL SECURITY TESTS
# ============================================

class TestAgentCredentialSecurity:
    """Test agent credential authorization and path validation."""

    def test_normalize_path_function_exists(self):
        """Path normalization function should exist."""
        from api.agent_credentials import normalize_path
        assert callable(normalize_path)

    def test_normalize_path_blocks_traversal(self):
        """Path normalization should block directory traversal."""
        from api.agent_credentials import normalize_path

        # These should raise ValueError
        # Note: URL-encoded paths like %2f are decoded by Flask before reaching this function
        traversal_attempts = [
            "/api/sites/../admin",
            "/api/sites/../../etc/passwd",
            "/../../../root",
            "/api/../admin",
        ]

        for path in traversal_attempts:
            with pytest.raises(ValueError, match="traversal"):
                normalize_path(path)

    def test_normalize_path_removes_dots(self):
        """Should remove single dots (current directory)."""
        from api.agent_credentials import normalize_path

        assert normalize_path("/api/./sites/./files") == "/api/sites/files"
        assert normalize_path("/./api/sites") == "/api/sites"

    def test_normalize_path_collapses_slashes(self):
        """Should collapse multiple slashes."""
        from api.agent_credentials import normalize_path

        assert normalize_path("/api//sites///files") == "/api/sites/files"
        assert normalize_path("///api/sites/") == "/api/sites"

    def test_normalize_path_empty_returns_root(self):
        """Empty path should return root."""
        from api.agent_credentials import normalize_path

        assert normalize_path("") == "/"
        assert normalize_path(None) == "/"

    def test_path_matches_pattern_exact_match(self):
        """Exact path matching should work."""
        from api.agent_credentials import path_matches_pattern

        assert path_matches_pattern("/api/sites", "/api/sites") == True
        assert path_matches_pattern("/api/sites", "/api/users") == False

    def test_path_matches_pattern_single_wildcard(self):
        """Single wildcard should match one segment."""
        from api.agent_credentials import path_matches_pattern

        assert path_matches_pattern("/api/sites/123", "/api/sites/*") == True
        assert path_matches_pattern("/api/sites/123/files", "/api/sites/*") == False

    def test_path_matches_pattern_double_wildcard(self):
        """Double wildcard should match multiple segments."""
        from api.agent_credentials import path_matches_pattern

        assert path_matches_pattern("/api/sites/123/files/foo", "/api/sites/**") == True
        assert path_matches_pattern("/api/sites/a/b/c/d", "/api/sites/**") == True

    def test_hash_task_consistency(self):
        """Task hashing should be consistent."""
        from api.agent_credentials import hash_task

        task = "Fix the login bug in auth.py"
        hash1 = hash_task(task)
        hash2 = hash_task(task)

        assert hash1 == hash2, "Same task should produce same hash"
        assert len(hash1) == 64, "SHA256 should be 64 hex chars"

    def test_hash_task_none_returns_none(self):
        """None task should return None hash."""
        from api.agent_credentials import hash_task

        assert hash_task(None) is None
        assert hash_task("") is None


# ============================================
# API KEY VALIDATION TESTS (removed — local-first auth uses credential verification only)
# ============================================

import pytest

@pytest.mark.skip(reason="API key validation removed in local-first auth transition; all auth uses signed credentials")
class TestAPIKeyValidation:
    """Formerly tested API key validation — API keys replaced by credential auth."""

    def test_placeholder(self):
        pass


# ============================================
# ORIGIN VALIDATION TESTS
# ============================================

class TestOriginValidation:
    """Test CORS origin validation security."""

    def test_origin_validation_exists(self):
        """Origin validation function should exist in source."""
        with open('api/passkey_auth.py', 'r', encoding='utf-8') as f:
            content = f.read()

        assert 'def _is_origin_allowed' in content, \
            "passkey_auth should have _is_origin_allowed function"

    def test_origin_validation_rejects_empty(self):
        """Should check for empty/None origins in source."""
        with open('api/passkey_auth.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # The function should check for empty origin
        assert 'if not origin' in content, \
            "_is_origin_allowed should check for empty origin"

    def test_origin_validation_uses_exact_hostname(self):
        """Should use URL parsing for hostname matching, not substring."""
        with open('api/passkey_auth.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Should use urlparse or URL parsing, not string contains
        assert 'urlparse' in content, \
            "Origin validation should use urlparse for proper hostname extraction"

        # Should NOT use unsafe patterns like origin.includes() or 'in origin'
        # (This was the vulnerability we fixed earlier)
        assert 'origin.includes' not in content, \
            "Should not use unsafe origin.includes() pattern"


# ============================================
# THREAD SAFETY TESTS
# ============================================

class TestThreadSafety:
    """Test thread safety of auth components."""

    def test_redis_store_uses_locks(self):
        """Redis store should use locks for thread safety."""
        from auth import redis_store
        import threading

        # Verify lock exists
        assert hasattr(redis_store, '_memory_lock')
        assert isinstance(redis_store._memory_lock, type(threading.Lock()))

    def test_concurrent_store_operations(self):
        """Concurrent store operations should not corrupt data."""
        from auth import redis_store
        import threading

        with patch.object(redis_store, 'get_redis_client', return_value=None):
            errors = []

            def store_item(i):
                try:
                    redis_store.store(f"concurrent_{i}", {"value": i})
                    result = redis_store.get(f"concurrent_{i}")
                    if result is None or result["value"] != i:
                        errors.append(f"Mismatch for key {i}")
                except Exception as e:
                    errors.append(str(e))

            threads = [threading.Thread(target=store_item, args=(i,)) for i in range(10)]

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"Concurrent errors: {errors}"


# ============================================
# INTEGRATION TESTS
# ============================================

class TestAuthIntegration:
    """Integration tests for auth flow."""

    def test_rate_limit_decorator_integration(self):
        """Rate limit decorator should integrate with Flask."""
        from auth.rate_limiter import rate_limit
        from flask import Flask

        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'test'

        @app.route('/test')
        @rate_limit("100 per minute")
        def test_endpoint():
            return "OK"

        # Create test client
        with app.test_client() as client:
            # Without limiter attached, should still work (fail open)
            response = client.get('/test')
            # Should not error, may return 200 or pass through
            assert response.status_code in [200, 404]  # 404 if not registered properly

    def test_passkey_endpoints_have_rate_limits(self):
        """Passkey endpoints should have rate limit decorators."""
        import inspect

        # Read the source file to check decorators
        with open('api/passkey_auth.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Check that rate_limit is imported and used
        assert 'from auth.rate_limiter import rate_limit' in content
        assert '@rate_limit(auth_limit)' in content or '@rate_limit(registration_limit)' in content

    def test_agent_credential_endpoint_has_rate_limit(self):
        """Agent credential endpoint should have rate limit."""
        with open('api/agent_credentials.py', 'r', encoding='utf-8') as f:
            content = f.read()

        assert 'from auth.rate_limiter import rate_limit' in content
        # The decorator now takes an explicit principal-aware key_func, so match
        # the call prefix rather than the exact single-arg form.
        assert '@rate_limit(credential_issue_limit' in content


# ============================================
# SESSION MANAGER TESTS
# ============================================

class TestSessionManager:
    """Test centralized session management."""

    def test_session_manager_imports(self):
        """Session manager should export all required functions."""
        from auth.session_manager import (
            SESSION_DURATION,
            SESSION_COOKIE_NAME,
            CSRF_COOKIE_NAME,
            UNLOCK_TOKEN_TTL,
            generate_session_token,
            validate_session_token,
            generate_unlock_token,
            validate_unlock_token,
            generate_csrf_token,
            get_session_expiry,
            get_current_time_ms,
            is_session_expired,
            get_time_remaining,
        )

        assert SESSION_DURATION == 10 * 60 * 60
        assert callable(generate_session_token)
        assert callable(validate_session_token)

    def test_session_token_roundtrip(self):
        """Session token should validate after generation."""
        from auth.session_manager import generate_session_token, validate_session_token

        wallet_id = "wallet_test123"
        unlocked_at = int(time.time() * 1000)

        token = generate_session_token(wallet_id, unlocked_at)
        assert token is not None

        data = validate_session_token(token)
        assert data is not None
        assert data['wallet_id'] == wallet_id

    def test_session_token_with_profile(self):
        """Session token should preserve profile information."""
        from auth.session_manager import generate_session_token, validate_session_token

        wallet_id = "wallet_profile_test"
        unlocked_at = int(time.time() * 1000)
        profile_id = "work"
        profile_name = "Work Profile"

        token = generate_session_token(wallet_id, unlocked_at, profile_id, profile_name)
        data = validate_session_token(token)

        assert data is not None
        assert data['profile_id'] == profile_id
        assert data['profile_name'] == profile_name

    def test_session_token_invalid_signature(self):
        """Tampered session token should not validate."""
        from auth.session_manager import generate_session_token, validate_session_token

        token = generate_session_token("wallet_123", int(time.time() * 1000))
        # Tamper with the token
        parts = token.split(':')
        parts[-1] = 'invalid_signature_12345678'
        tampered = ':'.join(parts)

        assert validate_session_token(tampered) is None

    def test_unlock_token_roundtrip(self):
        """Unlock token should validate within TTL."""
        from auth.session_manager import generate_unlock_token, validate_unlock_token

        wallet_id = "wallet_unlock_test"
        unlocked_at = int(time.time() * 1000)
        expires_at = int(time.time()) + 86400

        token = generate_unlock_token(wallet_id, unlocked_at, expires_at)
        assert token is not None

        data = validate_unlock_token(token)
        assert data is not None
        assert data['wallet_id'] == wallet_id
        assert data['expires_at'] == expires_at

    def test_unlock_token_expiry(self):
        """Unlock token should expire after TTL."""
        from auth.session_manager import (
            generate_unlock_token,
            validate_unlock_token,
            UNLOCK_TOKEN_TTL
        )

        # We can't easily test real expiry without waiting,
        # but we can verify the TTL constant is reasonable
        assert UNLOCK_TOKEN_TTL == 5 * 60  # 5 minutes

    def test_csrf_token_generation(self):
        """CSRF token should be generated securely."""
        from auth.session_manager import generate_csrf_token

        token1 = generate_csrf_token()
        token2 = generate_csrf_token()

        assert token1 is not None
        assert len(token1) > 20  # Should be sufficiently long
        assert token1 != token2  # Should be unique

    def test_session_expiry_helpers(self):
        """Session expiry helpers should work correctly."""
        from auth.session_manager import (
            get_session_expiry,
            is_session_expired,
            get_time_remaining,
            SESSION_DURATION
        )

        expires_at = get_session_expiry()
        assert expires_at > int(time.time())
        assert expires_at <= int(time.time()) + SESSION_DURATION + 1

        # Not expired yet
        assert not is_session_expired(expires_at)

        # Time remaining should be positive
        remaining = get_time_remaining(expires_at)
        assert remaining > 0
        assert remaining <= SESSION_DURATION

        # Expired session
        past_expiry = int(time.time()) - 100
        assert is_session_expired(past_expiry)
        assert get_time_remaining(past_expiry) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
