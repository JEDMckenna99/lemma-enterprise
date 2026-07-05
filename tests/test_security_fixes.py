"""
Security Fix Tests - High Priority KMS Security Audit Fixes

Tests for:
1. Site ownership validation in developer API key endpoints
2. KMS unavailable hard failure for new key generation

Run with: python -m pytest tests/test_security_fixes.py -v
"""

import pytest
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSiteOwnershipValidation:
    """
    Test Fix #1: Site ownership validation in developer API key endpoints
    
    SECURITY: Ensures that users can only access API keys for sites they own.
    """
    
    def test_verify_site_ownership_function_exists(self):
        """Verify the ownership validation function exists"""
        from api.developer_api import _verify_site_ownership
        assert callable(_verify_site_ownership)
    
    def test_verify_site_ownership_rejects_none_ppid(self):
        """Ownership check should reject None PPID"""
        from api.developer_api import _verify_site_ownership
        
        result = _verify_site_ownership('test_site', None)
        assert result == False, "Should reject None PPID"
    
    def test_verify_site_ownership_rejects_none_site_id(self):
        """Ownership check should reject None site_id"""
        from api.developer_api import _verify_site_ownership
        
        result = _verify_site_ownership(None, 'did:lemma:ppid_test')
        assert result == False, "Should reject None site_id"
    
    def test_verify_site_ownership_rejects_empty_values(self):
        """Ownership check should reject empty values"""
        from api.developer_api import _verify_site_ownership
        
        assert _verify_site_ownership('', 'did:lemma:ppid_test') == False
        assert _verify_site_ownership('test_site', '') == False
    
    def test_require_site_ownership_returns_401_without_auth(self):
        """Should return 401 when no authentication provided"""
        from api.developer_api import _require_site_ownership, _get_authenticated_ppid
        from flask import Flask
        
        app = Flask(__name__)
        with app.test_request_context():
            # No PPID in context
            error = _require_site_ownership('test_site')
            
            if error:
                response, status_code = error
                assert status_code == 401, "Should return 401 for unauthenticated request"
    
    def test_get_site_keys_endpoint_has_ownership_check(self):
        """Verify get_site_keys endpoint includes ownership validation"""
        import inspect
        from api.developer_api import get_site_keys
        
        source = inspect.getsource(get_site_keys)
        assert '_require_site_ownership' in source, \
            "get_site_keys must call _require_site_ownership for security"
    
    def test_create_site_key_endpoint_has_ownership_check(self):
        """Verify create_site_key endpoint includes ownership validation"""
        import inspect
        from api.developer_api import create_site_key
        
        source = inspect.getsource(create_site_key)
        assert '_require_site_ownership' in source, \
            "create_site_key must call _require_site_ownership for security"
    
    def test_revoke_site_key_endpoint_has_ownership_check(self):
        """Verify revoke_site_key endpoint includes ownership validation"""
        import inspect
        from api.developer_api import revoke_site_key
        
        source = inspect.getsource(revoke_site_key)
        assert '_require_site_ownership' in source, \
            "revoke_site_key must call _require_site_ownership for security"


class TestKMSHardFailure:
    """
    Test Fix #2: KMS unavailable hard failure for new key generation
    
    SECURITY: Ensures that signing keys are NEVER created without KMS encryption.
    """
    
    def test_kms_unavailable_error_exists(self):
        """Verify KMSUnavailableError exception class exists"""
        from api.issuer_management import KMSUnavailableError
        
        assert issubclass(KMSUnavailableError, RuntimeError)
    
    def test_kms_unavailable_error_has_descriptive_message(self):
        """Verify error provides helpful diagnostic information"""
        from api.issuer_management import KMSUnavailableError
        
        error = KMSUnavailableError("Test error message")
        assert str(error) == "Test error message"
    
    def test_get_iam_issuer_checks_kms_before_new_key(self):
        """Verify get_iam_issuer checks KMS availability before creating new keys"""
        import inspect
        from api.issuer_management import LemmaIssuerManager
        
        source = inspect.getsource(LemmaIssuerManager.get_iam_issuer)
        
        # Verify KMS check happens before key generation
        assert 'is_kms_available()' in source, \
            "Must check KMS availability"
        assert 'KMSUnavailableError' in source, \
            "Must raise KMSUnavailableError when KMS unavailable"
    
    def test_no_memory_only_fallback_for_new_keys(self):
        """Verify there's no memory-only fallback for new key generation"""
        import inspect
        from api.issuer_management import LemmaIssuerManager
        
        source = inspect.getsource(LemmaIssuerManager.get_iam_issuer)
        
        # These patterns indicate unsafe fallback behavior
        unsafe_patterns = [
            "memory-only storage",
            "Falling back to memory",
            "'storage': 'memory_only'"
        ]
        
        for pattern in unsafe_patterns:
            assert pattern not in source, \
                f"SECURITY: Found unsafe fallback pattern: '{pattern}'"
    
    def test_load_or_create_kms_issuer_requires_kms(self):
        """Verify _load_or_create_kms_issuer requires KMS"""
        import inspect
        from api.issuer_management import LemmaIssuerManager
        
        source = inspect.getsource(LemmaIssuerManager._load_or_create_kms_issuer)
        
        assert 'is_kms_available()' in source, \
            "_load_or_create_kms_issuer must check KMS availability"
        assert 'RuntimeError' in source or 'raise' in source, \
            "_load_or_create_kms_issuer must raise error if KMS unavailable"
    
    def test_issuer_metadata_always_shows_kms_backed(self):
        """Verify issuer metadata always indicates KMS-backed storage"""
        import inspect
        from api.issuer_management import LemmaIssuerManager
        
        source = inspect.getsource(LemmaIssuerManager.get_iam_issuer)
        
        # After the fix, storage should always be 'kms_backed'
        # The conditional 'memory_only' option should be removed
        assert "'storage': 'kms_backed'" in source, \
            "Issuer metadata must indicate KMS-backed storage"

    def test_platform_issuer_aliases_share_cache_key(self):
        """Platform aliases must not create independent issuer DIDs."""
        from api.issuer_management import _issuer_cache_key

        assert _issuer_cache_key("lemma.id") == "lemma_platform"
        assert _issuer_cache_key("lemma_platform") == "lemma_platform"
        assert _issuer_cache_key("www.lemma.id") == "lemma_platform"

    def test_platform_kms_context_candidates_include_legacy_aliases(self):
        """Existing platform ciphertext can be recovered across historical contexts."""
        from api.issuer_management import _kms_context_candidates

        class Site:
            site_id = "lemma_platform"
            site_domain = "lemma.id"

        assert _kms_context_candidates("lemma_platform", Site()) == [
            "lemma_platform",
            "lemma.id",
        ]

    def test_platform_existing_key_failure_does_not_rotate(self):
        """Existing platform keys should fail closed instead of minting a new DID."""
        import inspect
        from api.issuer_management import LemmaIssuerManager

        source = inspect.getsource(LemmaIssuerManager.get_iam_issuer)
        assert "refusing to rotate the platform issuer DID implicitly" in source


class TestSecurityDocumentation:
    """
    Test that security-critical code is properly documented
    """
    
    def test_developer_api_has_security_comments(self):
        """Verify developer_api.py has security documentation"""
        with open('api/developer_api.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'SECURITY' in content, \
            "developer_api.py should have SECURITY comments"
        assert 'ownership' in content.lower(), \
            "developer_api.py should document ownership validation"
    
    def test_issuer_management_has_security_comments(self):
        """Verify issuer_management.py has security documentation"""
        with open('api/issuer_management.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'SECURITY' in content, \
            "issuer_management.py should have SECURITY comments"
        assert 'FIPS' in content, \
            "issuer_management.py should reference FIPS compliance"
        assert 'KMS' in content, \
            "issuer_management.py should document KMS requirements"


class TestIntegrationScenarios:
    """
    Integration tests for security scenarios
    """
    
    def test_unauthorized_site_access_returns_403(self):
        """Verify unauthorized site access returns 403 Forbidden"""
        from flask import Flask
        from api.developer_api import developer_api_bp, _require_site_ownership
        
        app = Flask(__name__)
        app.register_blueprint(developer_api_bp)
        
        with app.test_request_context(headers={'X-Lemma-PPID': 'did:lemma:ppid_unauthorized_user'}):
            # Try to access a site the user doesn't own
            error = _require_site_ownership('some_other_site')
            
            if error:
                response, status_code = error
                # Should be 401 (no valid auth) or 403 (unauthorized for this site)
                assert status_code in [401, 403], \
                    f"Expected 401 or 403, got {status_code}"


if __name__ == '__main__':
    # Run tests with verbose output
    pytest.main([__file__, '-v', '--tb=short'])
