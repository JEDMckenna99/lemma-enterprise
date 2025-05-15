#!/usr/bin/env python3
"""
DID Test Runner Script

This script runs all DID-related tests for the Lemma human verification system.
It allows testing the DID functionality on your Heroku deployment.
"""
import os
import sys
import argparse
import importlib.util
import subprocess
from pathlib import Path

# Get the current directory
SCRIPT_DIR = Path(__file__).resolve().parent

def print_header(title):
    """Print a formatted header for test sections."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def run_heroku_deployment_test(heroku_url):
    """Run the Heroku deployment test."""
    print_header("Running Heroku Deployment Test")
    
    script_path = SCRIPT_DIR / "test_heroku_deployment.py"
    result = subprocess.run([sys.executable, str(script_path), heroku_url], 
                          capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("ERRORS:")
        print(result.stderr)
    
    return result.returncode == 0

def run_did_resolution_test(heroku_url, did=None):
    """Run the DID resolution test."""
    print_header("Running DID Resolution Test")
    
    script_path = SCRIPT_DIR / "heroku_did_resolution_test.py"
    cmd = [sys.executable, str(script_path), heroku_url]
    if did:
        cmd.append(did)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("ERRORS:")
        print(result.stderr)
    
    return result.returncode == 0

def run_did_functionality_test(heroku_url):
    """Run the DID functionality test."""
    print_header("Running DID Functionality Test")
    
    script_path = SCRIPT_DIR / "test_did_functionality.py"
    result = subprocess.run([sys.executable, str(script_path), heroku_url], 
                          capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("ERRORS:")
        print(result.stderr)
    
    return result.returncode == 0

def run_browser_storage_test(heroku_url, user_id=None, visible=False):
    """Run the browser storage test."""
    print_header("Running Browser Storage Test")
    
    script_path = SCRIPT_DIR / "browser_storage_test.py"
    cmd = [sys.executable, str(script_path), "--url", heroku_url]
    
    if user_id:
        cmd.extend(["--user", user_id])
    if visible:
        cmd.append("--visible")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("ERRORS:")
        print(result.stderr)
    
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="Run DID tests for Lemma")
    parser.add_argument("--url", required=True, help="Heroku deployment URL")
    parser.add_argument("--did", help="Specific DID to test with")
    parser.add_argument("--user", help="User ID to test with")
    parser.add_argument("--visible", action="store_true", help="Run browser tests in visible mode")
    parser.add_argument("--skip-browser", action="store_true", help="Skip browser storage tests")
    parser.add_argument("--tests", nargs="+", choices=["deployment", "resolution", "functionality", "browser"],
                      default=["deployment", "resolution", "functionality", "browser"],
                      help="Specific tests to run")
    
    args = parser.parse_args()
    
    success = True
    
    # Set environment variables for API key if available
    api_key = os.environ.get('LEMMA_API_KEY')
    if api_key:
        print(f"Using API key from environment: {api_key[:4]}...")
    else:
        print("No API key found in environment. Some tests may fail.")
    
    # Run selected tests
    if "deployment" in args.tests:
        deployment_success = run_heroku_deployment_test(args.url)
        success = success and deployment_success
    
    if "resolution" in args.tests:
        resolution_success = run_did_resolution_test(args.url, args.did)
        success = success and resolution_success
    
    if "functionality" in args.tests:
        functionality_success = run_did_functionality_test(args.url)
        success = success and functionality_success
    
    if "browser" in args.tests and not args.skip_browser:
        browser_success = run_browser_storage_test(args.url, args.user, args.visible)
        success = success and browser_success
    
    print_header("Test Results Summary")
    if success:
        print("✅ All tests completed successfully!")
    else:
        print("❌ Some tests failed. See output above for details.")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 