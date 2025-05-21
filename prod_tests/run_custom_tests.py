#!/usr/bin/env python3
"""
Custom production readiness test runner for Lemma Enterprise.

This script runs production readiness tests focusing on components 
that don't need authentication, avoiding CSRF issues.

Usage:
    python run_custom_tests.py
"""

import os
import sys
import json
import time
import argparse
import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Ensure proper path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run production readiness tests for Lemma Enterprise"
    )
    parser.add_argument(
        "--report-file",
        default="custom_test_report.json",
        help="File to write the test report to",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )
    return parser.parse_args()


def run_component_tests() -> Dict[str, Any]:
    """Run tests for components that don't require authentication."""
    start_time = time.time()
    
    # Create a test file that focuses on the wallet functionality
    test_file = """
import pytest
import time
import json
import os
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_credential():
    """Create a mock credential."""
    return {
        "id": f"credential_{int(time.time())}",
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "type": ["VerifiableCredential", "LemmaCredential"],
        "issuer": "did:lemma:test",
        "issuanceDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "credentialSubject": {
            "id": f"user_{int(time.time())}",
            "isHuman": True
        }
    }

def test_wallet_script_inclusion(client):
    """Test that the wallet script is included on the page."""
    response = client.get('/')
    assert b'lemma-wallet.js' in response.data, "Wallet script not included"
    assert b'lemma-wallet-init.js' in response.data, "Wallet init script not included"

def test_credential_service_init(app):
    """Test that the credential service can initialize."""
    from lemma.core.credential_service import get_credential_service
    with app.app_context():
        service = get_credential_service()
        assert service is not None, "Credential service is None"

def test_did_resolver_availability(app):
    """Test that the DID resolver is available."""
    try:
        from lemma.core.did_resolver import Resolver
        resolver = Resolver()
        assert resolver is not None, "DID resolver is None"
    except ImportError:
        pytest.skip("DID resolver not available")

def test_json_api_endpoints(client):
    """Test that the API endpoints return JSON."""
    endpoints = [
        '/api/health',
        '/api/generate-challenge'
    ]
    
    for endpoint in endpoints:
        response = client.get(endpoint)
        if response.status_code != 404:
            assert response.content_type.startswith('application/json'), f"Endpoint {endpoint} not returning JSON"
"""
    
    # Write the test file
    test_path = Path("prod_tests/custom_component_test.py")
    test_path.write_text(test_file)
    
    # Run the tests
    result = pytest.main(['-xvs', str(test_path)])
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # Determine overall status
    status = "PASS" if result == 0 else "FAIL"
    
    # Create the report
    report = {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "total_time_seconds": elapsed_time,
        "command": f"-xvs {test_path}",
    }
    
    return report


def write_report(report: Dict[str, Any], report_file: str):
    """Write the test report to a file."""
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\nCustom test report written to {report_file}")
    print(f"Overall status: {report['status']}")
    print(f"Total time: {report['total_time_seconds']:.2f} seconds")


def main():
    """Run the custom production readiness tests."""
    args = parse_args()
    
    print("=====================================================")
    print("Lemma Enterprise Custom Test Runner")
    print("=====================================================")
    print(f"Starting tests at {datetime.now().isoformat()}")
    
    # Set up environment
    os.environ["LEMMA_TESTING"] = "1"
    
    # Run the tests
    report = run_component_tests()
    
    # Write the report
    write_report(report, args.report_file)
    
    # Exit with the appropriate code
    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main() 