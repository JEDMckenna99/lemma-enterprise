#!/usr/bin/env python3
import webbrowser
import time
from pathlib import Path

def run_tests():
    print("🚀 Starting Lemma Wallet Test...")
    
    try:
        import requests
        response = requests.get("http://localhost:5000/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Flask app is running")
        else:
            print("❌ Flask app is not responding correctly")
            return
    except:
        print("❌ Flask app is not running. Please start it with 'python app.py'")
        return
    
    test_file = Path("wallet_tests/wallet_test.html")
    
    if test_file.exists():
        print("🌐 Opening wallet test...")
        webbrowser.open(f"file://{test_file.absolute()}")
    else:
        print("❌ Test file not found")
    
    print("\n📋 Test Instructions:")
    print("1. Test page will open in your browser")
    print("2. Click the test buttons to run wallet functionality tests")
    print("3. Check for green ✅ success messages and red ❌ error messages")

if __name__ == "__main__":
    run_tests()
