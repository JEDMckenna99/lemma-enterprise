#!/usr/bin/env python3
"""
Test Credential Immutability
=============================

Verifies that credentials are tamper-resistant via Ed25519 signatures.

Tests:
1. Valid credential passes verification
2. Modified scope fails verification
3. Modified expiry fails verification
4. Modified permission ID fails verification
5. Modified claims fail verification
6. Message construction matches between issue and verify

EXPECTED RESULT: ALL tampering attempts should FAIL verification
"""

import json
import time
import sys
from typing import Dict, Tuple

try:
    from lemma_crypto import PyMinimalIssuer, PyOptimizedVerifier
    RUST_AVAILABLE = True
except ImportError:
    print("[ERROR] Rust crypto engine not available")
    print("   Run: pip install -e lemma-crypto")
    sys.exit(1)


class ImmutabilityTester:
    def __init__(self):
        print("[SECURITY] Initializing Credential Immutability Test")
        print("=" * 70)
        
        # Create issuer (site's signing key)
        self.issuer = PyMinimalIssuer()
        self.issuer_did = self.issuer.get_did()
        
        # Create verifier
        self.verifier = PyOptimizedVerifier()
        
        print(f"[OK] Issuer created: {self.issuer_did[:50]}...")
        print(f"[OK] Verifier initialized\n")
        
        self.test_count = 0
        self.passed = 0
        self.failed = 0
    
    def issue_test_credential(self) -> Dict:
        """Issue a test permission credential"""
        user_did = "did:lemma:test_user_abc123"
        current_time = int(time.time())
        
        claims = {
            'packageType': 'permission',
            'siteId': 'test_site_123',
            'siteDomain': 'testsite.com',
            'permissionId': 'editor',
            'displayName': 'Editor',
            'scope': str(['posts:read', 'posts:write', 'posts:delete']),  # Original scope (as string)
            'issuedAt': str(current_time),
            'expiresAt': str(current_time + 86400),  # 24 hours
        }
        
        # Issue credential
        credential_json = self.issuer.issue_credential(user_did, claims)
        credential = json.loads(credential_json)
        
        # Debug: Print credential structure
        print(f"\n[DEBUG] Credential structure:")
        print(f"  Keys: {list(credential.keys())}")
        if 'credentialSubject' in credential:
            print(f"  credentialSubject keys: {list(credential['credentialSubject'].keys())}")
        if 'claims' in credential:
            print(f"  claims keys: {list(credential['claims'].keys())}")
        
        return credential
    
    def verify_credential(self, credential: Dict) -> Tuple[bool, float]:
        """Verify credential and return (is_valid, time_us)"""
        start_time = time.perf_counter()
        
        credential_json = json.dumps(credential)
        result = self.verifier.verify_credential(credential_json)
        
        # Extract is_valid from result
        is_valid = result.verified if hasattr(result, 'verified') else result.get('verified', False)
        
        verification_time = (time.perf_counter() - start_time) * 1_000_000
        
        return is_valid, verification_time
    
    def run_test(self, test_name: str, credential: Dict, expected_valid: bool, attack_description: str = None):
        """Run a single immutability test"""
        self.test_count += 1
        
        print(f"\n{'='*70}")
        print(f"Test #{self.test_count}: {test_name}")
        if attack_description:
            print(f"Attack: {attack_description}")
        print(f"{'='*70}")
        
        # Show credential details (use credentialSubject, not claims)
        claims = credential.get('credentialSubject', credential.get('claims', {}))
        print(f"Credential ID: {credential.get('id', 'N/A')}")
        print(f"Permission ID: {claims.get('permissionId', 'N/A')}")
        print(f"Scope: {claims.get('scope', 'N/A')}")
        print(f"Expires At: {claims.get('expiresAt', 'N/A')}")
        print(f"Signature: {credential.get('proof', {}).get('signatureValue', 'N/A')[:32]}...")
        
        # Verify
        is_valid, verify_time = self.verify_credential(credential)
        
        print(f"\nVerification Result: {'[VALID]' if is_valid else '[INVALID]'}")
        print(f"Verification Time: {verify_time:.2f}µs")
        
        # Check if result matches expectation
        if is_valid == expected_valid:
            print(f"[PASS] TEST PASSED - Got expected result ({expected_valid})")
            self.passed += 1
        else:
            print(f"[FAIL] TEST FAILED - Expected {expected_valid}, got {is_valid}")
            self.failed += 1
    
    def test_valid_credential(self):
        """Test 1: Valid credential should pass"""
        credential = self.issue_test_credential()
        
        self.run_test(
            "Valid Credential",
            credential,
            expected_valid=True,
            attack_description="No tampering - should pass verification"
        )
        
        return credential
    
    def test_tamper_scope_add_permission(self, original_credential: Dict):
        """Test 2: Adding permission to scope should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Add 'posts:admin' to scope
        # Note: scope is stored as a string representation of a list
        original_scope = tampered['credentialSubject']['scope']
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Original scope: {original_scope}")
        import ast
        scope_list = ast.literal_eval(original_scope) if isinstance(original_scope, str) else original_scope
        tampered_scope = scope_list + ['posts:admin']  # Add admin permission!
        tampered['credentialSubject']['scope'] = str(tampered_scope)
        print(f"   Tampered scope: {tampered['credentialSubject']['scope']}")
        
        self.run_test(
            "Tamper: Add Permission to Scope",
            tampered,
            expected_valid=False,
            attack_description="User tries to add 'posts:admin' to scope array"
        )
    
    def test_tamper_scope_escalate(self, original_credential: Dict):
        """Test 3: Escalating scope should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Change scope to wildcard
        original_scope = tampered['credentialSubject']['scope']
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Original scope: {original_scope}")
        tampered['credentialSubject']['scope'] = str(['*'])  # Give self admin access!
        print(f"   Tampered scope: {tampered['credentialSubject']['scope']}")
        
        self.run_test(
            "Tamper: Escalate Scope to Wildcard",
            tampered,
            expected_valid=False,
            attack_description="User tries to change scope to ['*'] (full access)"
        )
    
    def test_tamper_extend_expiry(self, original_credential: Dict):
        """Test 4: Extending expiry should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Extend expiration by 1 year
        original_expiry = int(tampered['credentialSubject']['expiresAt'])
        tampered_expiry = original_expiry + (365 * 24 * 60 * 60)  # +1 year
        
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Original expiry: {original_expiry} ({time.ctime(original_expiry)})")
        print(f"   Tampered expiry: {tampered_expiry} ({time.ctime(tampered_expiry)})")
        
        tampered['credentialSubject']['expiresAt'] = str(tampered_expiry)
        
        self.run_test(
            "Tamper: Extend Expiration Date",
            tampered,
            expected_valid=False,
            attack_description="User tries to extend credential expiry by 1 year"
        )
    
    def test_tamper_change_permission_id(self, original_credential: Dict):
        """Test 5: Changing permission ID should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Change permission from 'editor' to 'admin'
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Original permission: {tampered['credentialSubject']['permissionId']}")
        tampered['credentialSubject']['permissionId'] = 'admin'  # Escalate to admin!
        print(f"   Tampered permission: {tampered['credentialSubject']['permissionId']}")
        
        self.run_test(
            "Tamper: Change Permission ID",
            tampered,
            expected_valid=False,
            attack_description="User tries to change permissionId from 'editor' to 'admin'"
        )
    
    def test_tamper_add_custom_claim(self, original_credential: Dict):
        """Test 6: Adding new claims should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Add a new claim
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Adding new claim: superuser = true")
        tampered['credentialSubject']['superuser'] = 'true'  # Add superuser flag
        
        self.run_test(
            "Tamper: Add Custom Claim",
            tampered,
            expected_valid=False,
            attack_description="User tries to add 'superuser: true' claim"
        )
    
    def test_tamper_modify_site_id(self, original_credential: Dict):
        """Test 7: Changing site ID should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Change site ID to use credential on different site
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Original siteId: {tampered['credentialSubject']['siteId']}")
        tampered['credentialSubject']['siteId'] = 'different_site_456'  # Use on different site
        print(f"   Tampered siteId: {tampered['credentialSubject']['siteId']}")
        
        self.run_test(
            "Tamper: Change Site ID",
            tampered,
            expected_valid=False,
            attack_description="User tries to use credential on different site"
        )
    
    def test_tamper_remove_expiry(self, original_credential: Dict):
        """Test 8: Removing expiry should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Remove expiration (make credential never expire)
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Removing expiresAt claim to make credential never expire")
        del tampered['credentialSubject']['expiresAt']
        
        self.run_test(
            "Tamper: Remove Expiration",
            tampered,
            expected_valid=False,
            attack_description="User tries to remove expiry to make credential permanent"
        )
    
    def test_tamper_signature_bytes(self, original_credential: Dict):
        """Test 9: Modifying signature bytes should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Flip a bit in the signature
        original_sig = tampered['proof']['signatureValue']
        
        # Flip first byte
        sig_bytes = list(original_sig)
        sig_bytes[0] = 'f' if sig_bytes[0] != 'f' else '0'
        tampered_sig = ''.join(sig_bytes)
        
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Original signature: {original_sig[:32]}...")
        print(f"   Tampered signature: {tampered_sig[:32]}...")
        
        tampered['proof']['signatureValue'] = tampered_sig
        
        self.run_test(
            "Tamper: Modify Signature Bytes",
            tampered,
            expected_valid=False,
            attack_description="User tries to modify signature bytes directly"
        )
    
    def test_replay_different_user(self, original_credential: Dict):
        """Test 10: Using credential for different user should fail"""
        tampered = json.loads(json.dumps(original_credential))
        
        # ATTACK: Change subject DID (use someone else's credential)
        original_subject = tampered['subject']
        tampered_subject = "did:lemma:attacker_xyz789"
        
        print(f"\n[ATTACK] TAMPERING ATTEMPT:")
        print(f"   Original subject: {original_subject}")
        print(f"   Tampered subject: {tampered_subject}")
        
        tampered['subject'] = tampered_subject
        
        self.run_test(
            "Tamper: Change Subject DID",
            tampered,
            expected_valid=False,
            attack_description="Attacker tries to use stolen credential by changing subject DID"
        )
    
    def run_all_tests(self):
        """Run complete immutability test suite"""
        print("\n" + "=" * 70)
        print("[SECURITY] CREDENTIAL IMMUTABILITY TEST SUITE")
        print("=" * 70)
        print("Testing Ed25519 signature verification catches all tampering attempts\n")
        
        # Test 1: Valid credential
        original_credential = self.test_valid_credential()
        
        # Test 2-10: Various tampering attacks
        self.test_tamper_scope_add_permission(original_credential)
        self.test_tamper_scope_escalate(original_credential)
        self.test_tamper_extend_expiry(original_credential)
        self.test_tamper_change_permission_id(original_credential)
        self.test_tamper_add_custom_claim(original_credential)
        self.test_tamper_modify_site_id(original_credential)
        self.test_tamper_remove_expiry(original_credential)
        self.test_tamper_signature_bytes(original_credential)
        self.test_replay_different_user(original_credential)
        
        # Summary
        print("\n" + "=" * 70)
        print("[RESULTS] TEST SUMMARY")
        print("=" * 70)
        print(f"Total Tests: {self.test_count}")
        print(f"[OK] Passed: {self.passed}")
        print(f"[FAIL] Failed: {self.failed}")
        print(f"Success Rate: {(self.passed/self.test_count)*100:.1f}%")
        
        if self.failed == 0:
            print("\n[SUCCESS] ALL TESTS PASSED!")
            print("[OK] Credential immutability is correctly implemented")
            print("[OK] Ed25519 signatures successfully prevent all tampering")
            print("[OK] VULN-004 confirmed: Tampering is cryptographically impossible")
            return 0
        else:
            print(f"\n[WARNING] {self.failed} TEST(S) FAILED!")
            print("[ERROR] Credential immutability may have issues")
            return 1


def main():
    """Main test execution"""
    tester = ImmutabilityTester()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()

