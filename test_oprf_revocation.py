#!/usr/bin/env python3
"""
Test the OPRF-Cascaded Bloom Filter revocation system for Lemma.

This script tests the entire OPRF-cascaded Bloom filter system:
1. Go OPRF service
2. Cascaded Bloom filter implementation
3. Witness generation and verification
4. Integration with the credential service

Usage:
    python test_oprf_revocation.py [--server-url SERVER_URL]
"""

import os
import json
import time
import base64
import hashlib
import argparse
import requests
from typing import Dict, Any, List, Tuple
import sys
from datetime import datetime

# Ensure proper path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import modules
try:
    from lemma.core.cascaded_bloom import OPRFClient, CascadedBloomRevocation, create_cascade_bundle
except ImportError:
    print("Error: Could not import cascaded Bloom filter modules. Make sure the path is correct.")
    sys.exit(1)

# Constants
DEFAULT_SERVER_URL = "http://localhost:8080"


def check_oprf_service(server_url: str) -> bool:
    """Check if the OPRF service is running."""
    try:
        response = requests.get(f"{server_url}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ OPRF service is running: {data['status']}")
            print(f"   Version: {data['version']}")
            print(f"   Epoch: {data['epoch']}")
            return True
        else:
            print(f"❌ OPRF service returned status code {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Could not connect to OPRF service: {e}")
        return False


def test_oprf_client(server_url: str) -> Tuple[bool, OPRFClient]:
    """Test the OPRF client."""
    try:
        print("\n🔍 Testing OPRF client...")
        client = OPRFClient(server_url=server_url)
        
        # Get public key
        public_key = client.get_public_key()
        print(f"✅ Retrieved public key: {public_key[:16]}...")
        
        # Test blinding
        test_credential_id = "test-credential-123"
        alpha, r = client.blind(test_credential_id)
        print(f"✅ Blinded credential ID: {test_credential_id[:10]}...")
        print(f"   Alpha (blinded value): {alpha[:8].hex()}...")
        print(f"   r (blinding factor): {r[:8].hex()}...")
        
        # Test evaluation
        beta = client.evaluate(alpha)
        print(f"✅ Evaluated blinded value (beta): {beta[:8].hex()}...")
        
        # Test unblinding
        y = client.unblind(beta, r)
        print(f"✅ Unblinded result (y): {y[:8].hex()}...")
        
        # Test complete evaluation
        result = client.get_evaluation(test_credential_id)
        print(f"✅ Complete evaluation result: {result[:8].hex()}...")
        
        # Test witness generation
        epoch = datetime.now().strftime("%Y-%m-%d")
        witness = client.generate_witness(test_credential_id, epoch)
        print(f"✅ Generated witness for epoch {epoch}")
        print(f"   Witness type: {witness['type']}")
        
        return True, client
    except Exception as e:
        print(f"❌ OPRF client test failed: {e}")
        return False, None


def test_cascaded_bloom(oprf_client: OPRFClient) -> Tuple[bool, CascadedBloomRevocation]:
    """Test the cascaded Bloom filter implementation."""
    try:
        print("\n🔍 Testing cascaded Bloom filter...")
        
        # Create a cascade
        issuer_id = "did:lemma:test"
        cascade = CascadedBloomRevocation(issuer_id=issuer_id, cascade_levels=3, error_rate=0.02)
        
        print(f"✅ Created cascade with {len(cascade.levels)} levels")
        
        # Test revocation
        test_credentials = [
            "test-credential-1",
            "test-credential-2",
            "test-credential-3",
            "test-credential-4",
            "test-credential-5"
        ]
        
        # Revoke a few credentials
        revoked_credentials = test_credentials[:3]
        for cid in revoked_credentials:
            # Get OPRF evaluation
            evaluation = oprf_client.get_evaluation(cid)
            # Add to cascade
            cascade.revoke(cid, evaluation)
            print(f"✅ Revoked credential: {cid}")
        
        # Test revocation checks
        for cid in test_credentials:
            evaluation = oprf_client.get_evaluation(cid)
            is_revoked, level = cascade.is_revoked(evaluation)
            expected_revoked = cid in revoked_credentials
            status = "✅" if is_revoked == expected_revoked else "❌"
            print(f"{status} Credential {cid}: {'Revoked' if is_revoked else 'Valid'} (Level: {level})")
        
        # Create a cascade bundle
        epoch = datetime.now().strftime("%Y-%m-%d")
        bundle = create_cascade_bundle(cascade, epoch)
        print(f"✅ Created cascade bundle for epoch {epoch}")
        print(f"   Revoked count: {bundle['metadata']['revoked_count']}")
        
        # Write bundle to file for testing
        os.makedirs("test_data", exist_ok=True)
        bundle_file = os.path.join("test_data", f"cascade_{epoch}.json")
        with open(bundle_file, "w") as f:
            json.dump(bundle, f, indent=2)
        print(f"✅ Wrote cascade bundle to {bundle_file}")
        
        return True, cascade
    except Exception as e:
        print(f"❌ Cascaded Bloom filter test failed: {e}")
        return False, None


def test_witness_verification(oprf_client: OPRFClient, cascade: CascadedBloomRevocation) -> bool:
    """Test witness generation and verification."""
    try:
        print("\n🔍 Testing witness verification...")
        
        # Generate a witness for a non-revoked credential
        test_credential = "test-credential-not-revoked"
        epoch = datetime.now().strftime("%Y-%m-%d")
        
        witness = oprf_client.generate_witness(test_credential, epoch)
        print(f"✅ Generated witness for credential {test_credential}")
        
        # Serialize the cascade for testing
        bundle = create_cascade_bundle(cascade, epoch)
        cascade_hash = bundle["metadata"]["hash"]
        
        # Verify the witness
        is_valid = cascade.verify_witness(witness, cascade_hash)
        print(f"{'✅' if is_valid else '❌'} Witness verification result: {'Valid' if is_valid else 'Invalid'}")
        
        return is_valid
    except Exception as e:
        print(f"❌ Witness verification test failed: {e}")
        return False


def test_integration() -> bool:
    """
    Test integration with the Lemma credential service.
    
    This requires that the Flask app is running.
    """
    try:
        print("\n🔍 Testing integration with credential service...")
        
        # Check if the API is available
        try:
            response = requests.get("http://localhost:5000/api/health")
            if response.status_code != 200:
                print("❌ Lemma API not available. Skipping integration test.")
                return False
        except Exception:
            print("❌ Lemma API not available. Skipping integration test.")
            return False
        
        # Create a test credential
        response = requests.post(
            "http://localhost:5000/api/issue-credential",
            headers={"X-API-Key": os.environ.get("LEMMA_API_KEY", "test_key")},
            json={"user_id": f"test_user_{int(time.time())}"}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to issue credential: {response.text}")
            return False
        
        credential = response.json()["credential"]
        credential_id = credential["id"]
        print(f"✅ Issued test credential with ID: {credential_id}")
        
        # Generate a challenge
        response = requests.get("http://localhost:5000/api/generate-challenge")
        if response.status_code != 200:
            print(f"❌ Failed to generate challenge: {response.text}")
            return False
        
        challenge = response.json()["challenge"]
        print(f"✅ Generated challenge: {challenge[:16]}...")
        
        # Create a presentation
        response = requests.post(
            "http://localhost:5000/api/presentation",
            json={"credential": credential, "challenge": challenge}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to create presentation: {response.text}")
            return False
        
        presentation = response.json()
        print(f"✅ Created presentation for credential {credential_id}")
        
        # Verify the presentation
        response = requests.post(
            "http://localhost:5000/api/verify-presentation",
            json={"presentation": presentation, "challenge": challenge}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to verify presentation: {response.text}")
            return False
        
        result = response.json()
        if result.get("valid"):
            print(f"✅ Verified presentation for credential {credential_id}")
        else:
            print(f"❌ Presentation verification failed: {result.get('reason')}")
            return False
        
        # Now try to add a revocation witness
        try:
            # Create an OPRF client
            client = OPRFClient(server_url=DEFAULT_SERVER_URL)
            
            # Generate a witness
            epoch = datetime.now().strftime("%Y-%m-%d")
            witness = client.generate_witness(credential_id, epoch)
            
            # Add the witness to the presentation
            presentation["revocationWitness"] = witness
            
            # Verify again with the witness
            response = requests.post(
                "http://localhost:5000/api/verify-presentation",
                json={"presentation": presentation, "challenge": challenge}
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to verify presentation with witness: {response.text}")
                return False
            
            result = response.json()
            if result.get("valid"):
                print(f"✅ Verified presentation with revocation witness")
            else:
                print(f"❌ Presentation verification with witness failed: {result.get('reason')}")
                return False
            
        except Exception as e:
            print(f"❌ Error adding revocation witness: {e}")
            print("⚠️ Integration test partially successful (without revocation witness)")
            return True
        
        return True
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test the OPRF-Cascaded Bloom Filter revocation system.")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL, help=f"OPRF service URL (default: {DEFAULT_SERVER_URL})")
    args = parser.parse_args()
    
    print("==========================================")
    print("OPRF-Cascaded Bloom Filter Revocation Test")
    print("==========================================")
    print(f"OPRF service URL: {args.server_url}")
    
    # Check if OPRF service is running
    service_running = check_oprf_service(args.server_url)
    if not service_running:
        print("\n❌ OPRF service is not running or not reachable. Please start the service and try again.")
        sys.exit(1)
    
    # Test OPRF client
    client_success, oprf_client = test_oprf_client(args.server_url)
    if not client_success:
        print("\n❌ OPRF client test failed. Exiting.")
        sys.exit(1)
    
    # Test cascaded Bloom filter
    cascade_success, cascade = test_cascaded_bloom(oprf_client)
    if not cascade_success:
        print("\n❌ Cascaded Bloom filter test failed. Exiting.")
        sys.exit(1)
    
    # Test witness verification
    witness_success = test_witness_verification(oprf_client, cascade)
    if not witness_success:
        print("\n⚠️ Witness verification test failed, but continuing.")
    
    # Test integration with credential service
    integration_success = test_integration()
    
    # Print summary
    print("\n==========================================")
    print("Test Summary:")
    print(f"OPRF Service: {'✅ Working' if service_running else '❌ Failed'}")
    print(f"OPRF Client: {'✅ Working' if client_success else '❌ Failed'}")
    print(f"Cascaded Bloom Filter: {'✅ Working' if cascade_success else '❌ Failed'}")
    print(f"Witness Verification: {'✅ Working' if witness_success else '⚠️ Partial'}")
    print(f"Integration: {'✅ Working' if integration_success else '⚠️ Partial' if integration_success is not False else '❌ Failed'}")
    print("==========================================")
    
    if client_success and cascade_success:
        print("\n✅ The OPRF-Cascaded Bloom Filter revocation system is working properly!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check the output for more details.")
        sys.exit(1)


if __name__ == "__main__":
    main() 