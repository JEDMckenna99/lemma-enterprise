#!/usr/bin/env python3
"""
Test Complete Lemma Crypto System
Tests: Ed25519 + OPRF + ZKP + Real Performance
"""

import time
import json

def test_complete_crypto_system():
    """Test the complete working crypto system"""
    print("🔐 COMPLETE LEMMA CRYPTO SYSTEM TEST")
    print("Testing: Ed25519 + OPRF + ZKP + Real Performance")
    print("=" * 60)
    
    try:
        # Import the working crypto engine
        import lemma_crypto
        print("✅ Successfully imported clean lemma_crypto")
        
        # Check what's available
        available = [x for x in dir(lemma_crypto) if not x.startswith('_')]
        print(f"📋 Available components: {available}")
        
        # Test 1: Basic credential creation and verification
        print("\n1. Testing basic Ed25519 credential system...")
        issuer = lemma_crypto.PyMinimalIssuer()
        issuer_did = issuer.get_did()
        public_key = issuer.get_public_key_hex()
        
        print(f"✅ Issuer created:")
        print(f"   DID: {issuer_did[:50]}...")
        print(f"   Key: {public_key[:16]}...{public_key[-16:]}")
        
        # Create credential
        claims = {
            "packageType": "identity",
            "isHuman": "true",
            "age": "25",
            "membership": "premium",
            "verificationLevel": "high"
        }
        
        credential_json = issuer.issue_credential("did:lemma:user_alice", claims)
        credential = json.loads(credential_json)
        
        print(f"✅ Credential created: {credential['id']}")
        print(f"   Claims: {list(credential['claims'].keys())}")
        print(f"   Signature: {credential['proof']['signature_value'][:32]}...")
        
        # Test 2: Complete verification (Ed25519 + OPRF revocation)
        print("\n2. Testing complete verification (Ed25519 + OPRF)...")
        verifier = lemma_crypto.PyCompleteVerifier()
        
        start_time = time.perf_counter_ns()
        result = verifier.verify_credential(credential_json)
        end_time = time.perf_counter_ns()
        
        verification_time_us = (end_time - start_time) / 1000
        
        print(f"✅ Complete verification result:")
        print(f"   Verified: {result.verified}")
        print(f"   Signature Valid: {result.signature_valid}")
        print(f"   Not Revoked: {result.not_revoked}")
        print(f"   Confidence: {result.confidence}")
        print(f"   Total Time: {verification_time_us:.3f} μs")
        print(f"   Signature Time: {result.signature_time_ns / 1000:.3f} μs")
        print(f"   Revocation Time: {result.revocation_time_ns / 1000:.3f} μs")
        
        assert result.verified, "Credential should be verified"
        assert result.signature_valid, "Signature should be valid"
        assert result.not_revoked, "Credential should not be revoked"
        
        # Test 3: ZKP Claims (validated by complete verification)
        print("\n3. Testing ZKP claims validated by complete verification...")
        zkp_verifier = lemma_crypto.PyZKPVerifier()
        
        # Create ZKP credential with claims
        zkp_claims = ["age_above_21", "premium_membership"]
        zkp_credential_json = zkp_verifier.create_zkp_credential(credential_json, zkp_claims)
        zkp_credential = json.loads(zkp_credential_json)
        
        print(f"✅ ZKP credential created:")
        print(f"   Base credential: {zkp_credential['base_credential']['id']}")
        print(f"   ZKP claims: {len(zkp_credential['zkp_claims'])}")
        print(f"   Validated by lemma: {zkp_credential['zkp_claims'][0]['verified_by_lemma']}")
        print(f"   Validation hash: {zkp_credential['validation_result_hash'][:32]}...")
        
        # Verify ZKP credential
        zkp_result = zkp_verifier.verify_zkp_credential(zkp_credential_json)
        print(f"✅ ZKP credential verification:")
        print(f"   Verified: {zkp_result.verified}")
        print(f"   Confidence: {zkp_result.confidence}")
        
        assert zkp_result.verified, "ZKP credential should be verified"
        
        # Test 4: Revocation testing
        print("\n4. Testing revocation system...")
        print("   Revoking credential...")
        verifier.revoke_credential(credential['id'])
        
        # Verify revoked credential
        revoked_result = verifier.verify_credential(credential_json)
        print(f"✅ Revoked credential check:")
        print(f"   Verified: {revoked_result.verified} (should be False)")
        print(f"   Signature Valid: {revoked_result.signature_valid} (should be True)")
        print(f"   Not Revoked: {revoked_result.not_revoked} (should be False)")
        
        assert not revoked_result.verified, "Revoked credential should fail verification"
        assert revoked_result.signature_valid, "Signature should still be valid"
        assert not revoked_result.not_revoked, "Credential should be revoked"
        
        # Test 5: ZKP credential after revocation
        print("\n5. Testing ZKP credential after base revocation...")
        zkp_revoked_result = zkp_verifier.verify_zkp_credential(zkp_credential_json)
        print(f"✅ ZKP credential after revocation:")
        print(f"   Verified: {zkp_revoked_result.verified} (should be False)")
        print(f"   Confidence: {zkp_revoked_result.confidence} (should be 0.0)")
        
        assert not zkp_revoked_result.verified, "ZKP credential should fail after base revocation"
        assert zkp_revoked_result.confidence == 0.0, "Confidence should be 0 after revocation"
        
        # Test 6: Performance benchmarking
        print("\n6. Performance benchmarking real crypto system...")
        
        # Create fresh credential for performance testing
        fresh_credential_json = issuer.issue_credential("did:lemma:perf_test", claims)
        fresh_verifier = lemma_crypto.PyCompleteVerifier()
        
        num_tests = 100
        times = []
        
        for i in range(num_tests):
            start = time.perf_counter_ns()
            result = fresh_verifier.verify_credential(fresh_credential_json)
            end = time.perf_counter_ns()
            
            if result.verified:
                times.append((end - start) / 1000)  # Convert to microseconds
        
        if times:
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            throughput = 1_000_000 / avg_time if avg_time > 0 else 0
            
            print(f"✅ Real crypto performance ({len(times)} successful tests):")
            print(f"   Average: {avg_time:.3f} μs")
            print(f"   Min: {min_time:.3f} μs")
            print(f"   Max: {max_time:.3f} μs")
            print(f"   Throughput: {throughput:.0f} verifications/second")
            
            # Performance assertions
            if avg_time > 100:
                print(f"⚠️  Performance warning: {avg_time:.1f}μs is slower than expected")
            else:
                print(f"🏆 Excellent performance: {avg_time:.1f}μs is within target")
        
        print("\n" + "=" * 60)
        print("🏆 COMPLETE LEMMA CRYPTO SYSTEM SUCCESS!")
        print("✅ Real Ed25519 signature verification working")
        print("✅ Real OPRF privacy-preserving revocation working")
        print("✅ Real ZKP claims validated by complete verification")
        print("✅ Real performance measured and benchmarked")
        print("✅ Complete authentication pipeline functional")
        print("=" * 60)
        
        return {
            "success": True,
            "ed25519_working": True,
            "oprf_working": True,
            "zkp_working": True,
            "revocation_working": True,
            "average_time_us": avg_time if times else 0,
            "throughput": throughput if times else 0,
            "real_crypto": True
        }
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return {"success": False, "error": "import_failed", "message": str(e)}
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return {"success": False, "error": "test_failed", "message": str(e)}

if __name__ == "__main__":
    result = test_complete_crypto_system()
    
    if result["success"]:
        print(f"\n🎉 ALL TESTS PASSED!")
        print(f"Real crypto performance: {result.get('average_time_us', 0):.3f} μs")
    else:
        print(f"\n❌ TESTS FAILED: {result.get('message', 'Unknown error')}")
        exit(1)
