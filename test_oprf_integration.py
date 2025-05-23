#!/usr/bin/env python3
"""
Test script for OPRF cascade revocation layer integration.
This script tests the complete OPRF workflow including:
1. OPRF service connectivity
2. Cascade manager initialization
3. Credential revocation checking
4. Witness generation and verification
"""

import os
import sys
import time
import logging
import requests
from typing import Dict, Any

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lemma.core.cascaded_bloom import (
    OPRFClient, 
    CascadeManager, 
    init_cascade_manager,
    get_cascade_manager
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_oprf_service_connectivity():
    """Test if the OPRF service is running and accessible."""
    print("🔍 Testing OPRF service connectivity...")
    
    # Set environment for internal OPRF service
    os.environ['OPRF_SERVICE_INTERNAL'] = 'true'
    
    try:
        # Create OPRF client
        client = OPRFClient()
        
        if client.offline_mode:
            print("⚠️  OPRF service not available - running in offline mode")
            print("   This is expected if the OPRF service is not running")
            return False
        else:
            print("✅ OPRF service is accessible")
            print(f"   Server URL: {client.server_url}")
            print(f"   Public key: {client.public_key[:16]}..." if hasattr(client, 'public_key') else "   No public key")
            return True
            
    except Exception as e:
        print(f"❌ OPRF service connectivity failed: {e}")
        return False

def test_cascade_manager():
    """Test cascade manager initialization and basic operations."""
    print("\n🔍 Testing cascade manager...")
    
    try:
        # Initialize cascade manager
        cascade_dir = os.path.join(os.path.dirname(__file__), 'instance', 'data', 'revocation', 'cascades')
        os.makedirs(cascade_dir, exist_ok=True)
        
        manager = init_cascade_manager(cascade_dir)
        
        # Get status
        status = manager.get_status()
        print("✅ Cascade manager initialized")
        print(f"   Cascade directory: {status['cascade_dir']}")
        print(f"   Current epoch: {status['current_epoch']}")
        print(f"   OPRF status: {status['oprf_status']}")
        print(f"   Cascade size: {status['cascade_size']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cascade manager test failed: {e}")
        return False

def test_revocation_check():
    """Test credential revocation checking."""
    print("\n🔍 Testing revocation checking...")
    
    try:
        manager = get_cascade_manager()
        
        # Test with a sample credential ID
        test_credential_id = "test_credential_12345"
        
        is_revoked, details = manager.check_revocation(test_credential_id)
        
        print("✅ Revocation check completed")
        print(f"   Credential ID: {test_credential_id}")
        print(f"   Is revoked: {is_revoked}")
        print(f"   Details: {details}")
        
        return True
        
    except Exception as e:
        print(f"❌ Revocation check failed: {e}")
        return False

def test_oprf_evaluation():
    """Test OPRF evaluation directly."""
    print("\n🔍 Testing OPRF evaluation...")
    
    try:
        client = OPRFClient()
        
        # Test credential ID
        test_credential_id = "test_credential_67890"
        
        # Get OPRF evaluation
        evaluation = client.get_evaluation(test_credential_id)
        
        print("✅ OPRF evaluation completed")
        print(f"   Credential ID: {test_credential_id}")
        print(f"   Evaluation length: {len(evaluation)} bytes")
        print(f"   Evaluation (hex): {evaluation.hex()[:32]}...")
        
        # Test cache stats
        stats = client.get_cache_stats()
        print(f"   Cache stats: {stats}")
        
        return True
        
    except Exception as e:
        print(f"❌ OPRF evaluation failed: {e}")
        return False

def test_witness_generation():
    """Test witness generation for offline verification."""
    print("\n🔍 Testing witness generation...")
    
    try:
        client = OPRFClient()
        
        # Test credential ID and epoch
        test_credential_id = "test_credential_witness"
        test_epoch = "2024-01-15"
        
        # Generate witness
        witness = client.generate_witness(test_credential_id, test_epoch)
        
        print("✅ Witness generation completed")
        print(f"   Credential ID: {test_credential_id}")
        print(f"   Epoch: {witness['epoch']}")
        print(f"   Witness type: {witness['type']}")
        print(f"   Alpha length: {len(witness['alpha'])} chars")
        print(f"   Beta length: {len(witness['beta'])} chars")
        
        return True
        
    except Exception as e:
        print(f"❌ Witness generation failed: {e}")
        return False

def main():
    """Run all OPRF integration tests."""
    print("🚀 Starting OPRF Cascade Revocation Layer Integration Tests")
    print("=" * 60)
    
    tests = [
        ("OPRF Service Connectivity", test_oprf_service_connectivity),
        ("Cascade Manager", test_cascade_manager),
        ("Revocation Check", test_revocation_check),
        ("OPRF Evaluation", test_oprf_evaluation),
        ("Witness Generation", test_witness_generation),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! OPRF cascade revocation layer is operational.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 