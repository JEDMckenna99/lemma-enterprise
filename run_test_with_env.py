#!/usr/bin/env python3
"""
Test Runner with Environment Setup for Lemma Enterprise

This script sets up the environment variables and runs the tests for the Lemma Human Verification System.
"""
import os
import sys
import subprocess

def setup_environment():
    """Set up environment variables for testing."""
    # Admin credentials
    os.environ["LEMMA_ADMIN_USER"] = "admin"
    os.environ["LEMMA_ADMIN_PASS"] = "password"
    os.environ["LEMMA_SECRET_KEY"] = "test-secret-key-for-development-only"
    
    # Flask settings
    os.environ["FLASK_DEBUG"] = "True"
    os.environ["FLASK_APP"] = "app.py"
    
    # Check for Twilio credentials
    if not os.environ.get("TWILIO_ACCOUNT_SID"):
        print("⚠️ Twilio credentials not set. SMS functionality will be simulated.")
        print("To enable real SMS, set the following environment variables:")
        print("  - TWILIO_ACCOUNT_SID")
        print("  - TWILIO_AUTH_TOKEN")
        print("  - TWILIO_PHONE_NUMBER")
    else:
        print("✅ Twilio credentials found. SMS functionality will be tested.")
    
    print("Environment variables set for testing.")

def run_basic_tests():
    """Run the basic tests."""
    print("\n=== Running Basic Tests ===")
    result = subprocess.run([sys.executable, "test_basic.py"], capture_output=True, text=True)
    print(result.stdout)
    return result.returncode == 0

def run_app_tests():
    """Start the application and run tests against it."""
    print("\n=== Testing Application ===")
    
    # Start the Flask application in the background
    print("Starting Flask application...")
    flask_process = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait a moment for the app to start
    import time
    time.sleep(5)
    
    # Check if the process is still running
    if flask_process.poll() is None:
        print("✅ Flask application started successfully")
        
        # Run tests against the running application
        print("\nTesting API endpoints...")
        try:
            import requests
            response = requests.get("http://localhost:5000/", timeout=5)
            if response.status_code == 200:
                print("✅ Home page accessible")
            else:
                print(f"❌ Home page returned status code {response.status_code}")
            
            # Test admin login page
            response = requests.get("http://localhost:5000/admin/login", timeout=5)
            if response.status_code == 200:
                print("✅ Admin login page accessible")
            else:
                print(f"❌ Admin login page returned status code {response.status_code}")
            
            print("\n✅ Application tests completed")
            
        except Exception as e:
            print(f"❌ Error during application tests: {e}")
        finally:
            # Terminate the Flask process
            flask_process.terminate()
            flask_process.wait()
            print("Flask application stopped")
    else:
        print("❌ Flask application failed to start")
        print("Error output:")
        print(flask_process.stderr.read().decode())
        return False
    
    return True

def main():
    """Main function to run all tests with environment setup."""
    print("=== LEMMA ENTERPRISE TEST RUNNER ===\n")
    
    # Set up environment
    setup_environment()
    
    # Run tests
    basic_result = run_basic_tests()
    app_result = run_app_tests()
    
    # Print summary
    print("\n=== TEST SUMMARY ===")
    print(f"Basic Tests: {'✅ PASSED' if basic_result else '❌ FAILED'}")
    print(f"Application Tests: {'✅ PASSED' if app_result else '❌ FAILED'}")
    
    all_passed = basic_result and app_result
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nYour verified human network is functioning properly and ready for deployment.")
    else:
        print("\n❌ SOME TESTS FAILED. Please fix the issues before deploying.")
    
    return all_passed

if __name__ == "__main__":
    main()
