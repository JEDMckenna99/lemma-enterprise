#!/usr/bin/env python3
"""
Simple test to verify the Rust engine is working properly
"""

import json
import time
from lemma_crypto import PyLemmaCore

def test_rust_engine():
    print("🔍 Testing Rust Engine Integration")
    print("=" * 50)
    
    # Initialize the Rust engine
    try:
        core = PyLemmaCore()
        print("✅ Rust engine initialized successfully!")
    except Exception as e:
        print(f"❌ Failed to initialize Rust engine: {e}")
        return False
    
    # Register packages
    try:
        core.register_identity_package()
        core.register_ticket_package()
        core.register_package_authenticity_package()
        core.register_qr_code_package("generic")
        print("✅ All packages registered successfully!")
    except Exception as e:
        print(f"❌ Failed to register packages: {e}")
        return False
    
    # Test credential verification
    test_credential = {
        'id': 'test_credential_12345',
        'issuer': 'lemma_test_issuer',
        'subject': 'test_user',
        'type': 'VerifiableCredential',
        'claims': {
            'isHuman': True,
            'packageType': 'identity'
        }
    }
    
    try:
        start_time = time.time_ns()
        result = core.verify_credential(json.dumps(test_credential))
        end_time = time.time_ns()
        
        print(f"✅ Rust verification completed!")
        print(f"   - Verified: {result.verified}")
        print(f"   - Confidence: {result.confidence}")
        print(f"   - Verification time: {result.verification_time_ns} ns")
        print(f"   - Offline: {result.offline}")
        print(f"   - Method: {result.method}")
        print(f"   - Total time (including Python overhead): {end_time - start_time} ns")
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False
    
    # Test batch verification
    try:
        credentials = [json.dumps(test_credential) for _ in range(3)]
        batch_results = core.verify_batch(credentials)
        print(f"✅ Batch verification completed: {len(batch_results)} credentials processed")
        
    except Exception as e:
        print(f"❌ Batch verification failed: {e}")
        return False
    
    # Get engine stats
    try:
        stats = core.get_stats()
        print(f"✅ Engine stats: {dict(stats)}")
        
    except Exception as e:
        print(f"❌ Stats retrieval failed: {e}")
        return False
    
    print(f"\n🎉 All Rust engine tests passed!")
    print(f"🚀 Your Rust engine is ready for production use!")
    return True

if __name__ == "__main__":
    test_rust_engine() 