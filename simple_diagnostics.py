#!/usr/bin/env python3
"""
Simple Heroku Diagnostics - Standalone script to check Rust engine status
"""

import sys
import os
import glob
import requests

def check_local_rust():
    """Check if Rust engine works locally"""
    print("🔍 Local Rust Engine Check")
    print("=" * 30)
    
    try:
        from lemma_crypto import PyLemmaCore, PyVerificationResult
        print("✅ SUCCESS: Rust engine imported successfully!")
        
        core = PyLemmaCore()
        print("✅ SUCCESS: Rust engine initialized successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        return False
    except Exception as e:
        print(f"❌ OTHER ERROR: {e}")
        return False

def check_heroku_deployment():
    """Check Heroku deployment status"""
    print("\n🌐 Heroku Deployment Check")
    print("=" * 30)
    
    try:
        # Test bot shield endpoint
        response = requests.get("https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/shield/status", timeout=10)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            engine = data.get('engine', 'unknown')
            print(f"Engine type: {engine}")
            
            if engine in ['rust_engine', 'rust_ready']:
                print(f"✅ SUCCESS: Heroku is using Rust engine! (Status: {engine})")
                return True
            elif engine == 'python_fallback':
                print("⚠️ FALLBACK: Heroku is using Python fallback")
                return False
            else:
                print(f"❓ UNKNOWN: Engine type '{engine}'")
                return False
        else:
            print(f"❌ ERROR: HTTP {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def check_build_artifacts():
    """Check for build artifacts"""
    print("\n📁 Build Artifacts Check")
    print("=" * 30)
    
    # Check for wheel files
    wheels = glob.glob("**/*.whl", recursive=True)
    if wheels:
        print(f"Found {len(wheels)} wheel files:")
        for wheel in wheels[:3]:  # Show first 3
            print(f"  - {wheel}")
    else:
        print("❌ No wheel files found")
    
    # Check for shared libraries
    shared_libs = glob.glob("**/*.so", recursive=True) + glob.glob("**/*.dll", recursive=True)
    if shared_libs:
        print(f"Found {len(shared_libs)} shared libraries:")
        for lib in shared_libs[:3]:  # Show first 3
            print(f"  - {lib}")
    else:
        print("❌ No shared libraries found")

def main():
    print("🔧 Lemma Rust Engine Diagnostics")
    print("================================")
    
    # Check local environment
    local_works = check_local_rust()
    
    # Check Heroku deployment
    heroku_works = check_heroku_deployment()
    
    # Check build artifacts
    check_build_artifacts()
    
    # Summary
    print("\n📊 Summary")
    print("=" * 30)
    print(f"Local Rust Engine: {'✅ Working' if local_works else '❌ Not Working'}")
    print(f"Heroku Deployment: {'✅ Working' if heroku_works else '❌ Not Working'}")
    
    if local_works and not heroku_works:
        print("\n💡 Recommendation: The Rust engine works locally but not on Heroku.")
        print("   This suggests a deployment/build issue. Check Heroku build logs.")
    elif not local_works and not heroku_works:
        print("\n💡 Recommendation: The Rust engine isn't working locally either.")
        print("   Focus on fixing the local build first, then deploy to Heroku.")
    elif heroku_works:
        print("\n🎉 Great! The Rust engine is working on Heroku!")

if __name__ == "__main__":
    main() 