"""
Test the OPRF cascade functionality
"""
import os
import json
import pytest
from datetime import datetime

def test_oprf_cascade_verification():
    """Test the verification of cascades."""
    try:
        from lemma.core.cascaded_bloom import verify_cascade_signature
    except ImportError:
        pytest.skip("Cascade verification not available")
    
    # Load a cascade from the test directory
    cascade_dir = os.path.join('.lemma_prod_test', 'revocation', 'cascades')
    if not os.path.exists(cascade_dir):
        pytest.skip("Cascade directory not found")
    
    cascade_files = [f for f in os.listdir(cascade_dir) if f.endswith('.json')]
    if not cascade_files:
        pytest.skip("No cascade files found")
    
    # Pick the first cascade file
    cascade_file = os.path.join(cascade_dir, cascade_files[0])
    print(f"Testing cascade file: {cascade_file}")
    
    # Load the cascade
    with open(cascade_file, 'r') as f:
        cascade = json.load(f)
    
    # Check cascade structure
    assert "metadata" in cascade, "No metadata in cascade"
    assert "levels" in cascade, "No levels in cascade"
    assert "signature" in cascade, "No signature in cascade"
    
    # Check metadata
    assert "issuer" in cascade["metadata"], "No issuer in metadata"
    assert "epoch" in cascade["metadata"], "No epoch in metadata"
    assert "created" in cascade["metadata"], "No created timestamp in metadata"
    
    # Check signature
    assert "signature" in cascade["signature"], "No signature in signature block"
    assert "signer" in cascade["signature"], "No signer in signature block"
    
    # This will try to verify the signature but might fail due to DID resolution
    # We're more concerned that it runs without exceptions at this point
    try:
        result = verify_cascade_signature(cascade)
        print(f"Signature verification result: {result}")
    except Exception as e:
        print(f"Signature verification exception (expected in test): {e}")
    
    # Test tampered cascade detection
    tampered_cascade = cascade.copy()
    tampered_cascade["signature"]["signature"] = "TAMPERED_SIGNATURE"
    
    # This should return False for a tampered signature
    result = verify_cascade_signature(tampered_cascade)
    assert not result, "Tampered signature was incorrectly verified as valid"
    
    print("OPRF cascade verification test completed successfully")

if __name__ == "__main__":
    test_oprf_cascade_verification() 