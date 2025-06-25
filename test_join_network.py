#!/usr/bin/env python3
"""Test the join-network page to see if bot shield is working."""

import requests

def test_join_network_page():
    """Test if the join-network page loads successfully."""
    try:
        print("🔍 Testing join-network page...")
        
        # Test the main site
        r = requests.get('https://lemma-enterprise-0f6ba17076c1.herokuapp.com/join-network')
        print(f"Status: {r.status_code}")
        
        if r.status_code == 200:
            print("✅ Page loads successfully!")
            
            # Check if the page contains shield-related content
            content = r.text.lower()
            
            if 'shield' in content:
                print("✅ Shield content detected on page")
            else:
                print("⚠️  No shield content found")
                
            if 'api_key' in content or 'lemma_demo_site_key' in content:
                print("✅ API key configuration detected")
            else:
                print("⚠️  No API key configuration found")
                
            if 'lemma-shield' in content:
                print("✅ Shield SDK detected")
            else:
                print("⚠️  Shield SDK not detected")
                
        else:
            print(f"❌ Page failed to load with status: {r.status_code}")
            print(f"Response: {r.text[:500]}...")
            
    except Exception as e:
        print(f"❌ Error testing page: {e}")

if __name__ == "__main__":
    test_join_network_page() 