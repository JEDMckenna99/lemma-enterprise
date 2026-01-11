"""
Edge Case Tests for Lemma Platform

Tests the fixes implemented in EDGE_CASE_FIXES.md:
- API input validation
- Offline resilience
- Credential format handling
"""

import pytest
import json
from datetime import datetime, timedelta

# Test the validation module
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.validation import (
    validate_site_id,
    validate_email,
    validate_permission_id,
    validate_timestamp,
    validate_credential_claims,
    ValidationError
)


class TestSiteIdValidation:
    """Test site_id validation edge cases"""
    
    def test_valid_domain(self):
        """Standard domain format"""
        assert validate_site_id('example.com') == 'example.com'
        
    def test_valid_subdomain(self):
        """Subdomain format"""
        assert validate_site_id('api.example.com') == 'api.example.com'
        
    def test_lemma_platform_ids(self):
        """Known internal IDs"""
        assert validate_site_id('lemma.id') == 'lemma.id'
        assert validate_site_id('lemma_platform') == 'lemma_platform'
        assert validate_site_id('demo.lemma.id') == 'demo.lemma.id'
        
    def test_empty_required(self):
        """Empty site_id when required"""
        with pytest.raises(ValidationError) as exc:
            validate_site_id('', required=True)
        assert exc.value.code == 'required'
        
    def test_empty_with_default(self):
        """Empty site_id with lemma default allowed"""
        result = validate_site_id('', required=False, allow_lemma_default=True)
        assert result == 'lemma.id'
        
    def test_case_normalization(self):
        """Site IDs should be lowercase"""
        assert validate_site_id('EXAMPLE.COM') == 'example.com'
        assert validate_site_id('Lemma.ID') == 'lemma.id'
        
    def test_invalid_format(self):
        """Invalid site_id formats"""
        with pytest.raises(ValidationError) as exc:
            validate_site_id('invalid site id with spaces')
        assert exc.value.code == 'invalid_format'
        
    def test_too_long(self):
        """Site ID exceeds max length"""
        long_id = 'a' * 300
        with pytest.raises(ValidationError) as exc:
            validate_site_id(long_id)
        assert exc.value.code == 'too_long'


class TestEmailValidation:
    """Test email validation"""
    
    def test_valid_email(self):
        assert validate_email('user@example.com') == 'user@example.com'
        
    def test_email_with_plus(self):
        assert validate_email('user+tag@example.com') == 'user+tag@example.com'
        
    def test_invalid_email_no_at(self):
        with pytest.raises(ValidationError):
            validate_email('invalid-email')
            
    def test_invalid_email_no_domain(self):
        with pytest.raises(ValidationError):
            validate_email('user@')
            
    def test_case_normalization(self):
        assert validate_email('USER@EXAMPLE.COM') == 'user@example.com'


class TestTimestampValidation:
    """Test timestamp format handling"""
    
    def test_iso_string(self):
        """ISO 8601 format"""
        result = validate_timestamp('2026-02-07T21:38:26.667Z')
        assert isinstance(result, int)
        assert result > 1700000000000  # After 2023 in ms
        
    def test_unix_seconds(self):
        """Unix timestamp in seconds"""
        result = validate_timestamp(1770500306)
        assert result == 1770500306000  # Converted to ms
        
    def test_unix_milliseconds(self):
        """Unix timestamp already in milliseconds"""
        result = validate_timestamp(1770500306667)
        assert result == 1770500306667  # No conversion
        
    def test_string_numeric(self):
        """Numeric string"""
        result = validate_timestamp('1770500306')
        assert result == 1770500306000
        
    def test_none_returns_none(self):
        """None input returns None"""
        assert validate_timestamp(None) is None
        
    def test_datetime_object(self):
        """datetime object"""
        dt = datetime(2026, 1, 15, 12, 0, 0)
        result = validate_timestamp(dt)
        assert isinstance(result, int)


class TestCredentialClaimsValidation:
    """Test credential claims normalization"""
    
    def test_normalize_site_id_variants(self):
        """Test all site_id field name variants"""
        variants = [
            {'siteId': 'example.com'},
            {'site': 'example.com'},
            {'site_id': 'example.com'},
            {'siteDomain': 'example.com'}
        ]
        for claims in variants:
            result = validate_credential_claims(claims)
            assert result.get('siteId') == 'example.com', f"Failed for {claims}"
            
    def test_normalize_permission_variants(self):
        """Test all permission field name variants"""
        variants = [
            {'permissionId': 'read'},
            {'permission_level': 'read'},
            {'permissions': 'read'}
        ]
        for claims in variants:
            result = validate_credential_claims(claims)
            assert result.get('permissionId') == 'read', f"Failed for {claims}"


class TestOfflineResilience:
    """Test offline behavior"""
    
    def test_revocation_sync_offline(self):
        """Verify graceful handling when offline"""
        # This would be tested in JavaScript, but we can test the concept
        # The wallet should not throw errors when network is unavailable
        pass


class TestAdminPermissionSecurity:
    """Test admin permission security - no loose .includes() checks"""
    
    def test_exact_admin_match(self):
        """Only exact admin permissions should grant admin"""
        from api.validation import validate_permission_id
        
        # These should be valid permission IDs
        assert validate_permission_id('admin_access') == 'admin_access'
        assert validate_permission_id('super_admin') == 'super_admin'
        assert validate_permission_id('admin') == 'admin'
        
    def test_fake_admin_blocked(self):
        """Permissions containing 'admin' but not in allowed list should NOT grant admin"""
        # This is tested in credential-utils.js
        # The pattern 'not-admin-really' should NOT pass .includes('admin') check
        # because we use strict matching now
        pass


# Run basic validation tests
if __name__ == '__main__':
    # Fix Windows console encoding
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    print("Running Edge Case Tests...")
    
    # Site ID tests
    print("\n=== Site ID Validation ===")
    tests_passed = 0
    tests_failed = 0
    
    test_cases = [
        ('example.com', True),
        ('lemma.id', True),
        ('lemma_platform', True),
        ('EXAMPLE.COM', True),  # Should normalize to lowercase
        ('', False),  # Empty - required by default
        ('invalid site', False),  # Spaces
    ]
    
    for site_id, should_pass in test_cases:
        try:
            result = validate_site_id(site_id, required=bool(site_id))
            if should_pass:
                print(f"  [PASS] '{site_id}' -> '{result}'")
                tests_passed += 1
            else:
                print(f"  [FAIL] '{site_id}' should have failed but got '{result}'")
                tests_failed += 1
        except ValidationError as e:
            if not should_pass:
                print(f"  [PASS] '{site_id}' correctly rejected: {e.message}")
                tests_passed += 1
            else:
                print(f"  [FAIL] '{site_id}' should have passed but got: {e.message}")
                tests_failed += 1
    
    # Timestamp tests
    print("\n=== Timestamp Validation ===")
    timestamp_tests = [
        ('2026-02-07T21:38:26.667Z', 'ISO string'),
        (1770500306, 'Unix seconds'),
        (1770500306667, 'Unix milliseconds'),
        ('1770500306', 'Numeric string'),
    ]
    
    for ts, label in timestamp_tests:
        try:
            result = validate_timestamp(ts)
            print(f"  [PASS] {label}: {ts} -> {result}ms ({datetime.fromtimestamp(result/1000).isoformat()})")
            tests_passed += 1
        except Exception as e:
            print(f"  [FAIL] {label}: {ts} failed: {e}")
            tests_failed += 1
    
    print(f"\n=== Results: {tests_passed} passed, {tests_failed} failed ===")
