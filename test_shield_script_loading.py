#!/usr/bin/env python3
"""
Test Shield Script Loading
Diagnoses if the shield widget script is loading and executing properly
"""

import requests
import re
import time

def test_shield_script_loading():
    """Test if the shield script is loading and has the expected content"""
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🔍 SHIELD SCRIPT LOADING DIAGNOSTIC")
    print("=" * 60)
    
    # Test 1: Check if the join_network page loads and includes the script
    print("\n📄 Step 1: Testing join_network page...")
    try:
        response = requests.get(f"{base_url}/join_network")
        if response.status_code == 200:
            content = response.text
            print(f"  ✅ Page loads: {response.status_code}")
            
            # Check for script tags
            script_patterns = [
                r'lemma-shield-widget\.js',
                r'lemma-wallet-background\.js',
                r'lemma-shield-flow-orchestrator\.js'
            ]
            
            found_scripts = []
            for pattern in script_patterns:
                if re.search(pattern, content):
                    clean_pattern = pattern.replace(r'\.', '.')
                    found_scripts.append(clean_pattern)
                    print(f"  ✅ Found script reference: {clean_pattern}")
                else:
                    clean_pattern = pattern.replace(r'\.', '.')
                    print(f"  ❌ Missing script reference: {clean_pattern}")
            
        else:
            print(f"  ❌ Page failed to load: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Page load error: {e}")
        return False
    
    # Test 2: Check if the shield widget script loads
    print("\n🛡️ Step 2: Testing shield widget script...")
    try:
        script_response = requests.get(f"{base_url}/static/js/lemma-shield-widget.js")
        if script_response.status_code == 200:
            script_content = script_response.text
            script_size = len(script_content)
            print(f"  ✅ Script loads: {script_response.status_code} ({script_size} bytes)")
            
            # Check for key components in the script
            checks = [
                ('LemmaShieldWidget class', 'class LemmaShieldWidget'),
                ('forceShow method', 'forceShow('),
                ('ULTRA-AGGRESSIVE fix', 'ULTRA-AGGRESSIVE'),
                ('IMMEDIATE fix', 'IMMEDIATE SYNCHRONOUS FIX'),
                ('emergencyForceShow', 'emergencyForceShow'),
                ('window.LemmaShieldWidget assignment', 'window.LemmaShieldWidget = LemmaShieldWidget')
            ]
            
            for check_name, check_pattern in checks:
                if check_pattern in script_content:
                    print(f"  ✅ Found: {check_name}")
                else:
                    print(f"  ❌ Missing: {check_name}")
                    
            # Check the very end of the script for our fixes
            script_end = script_content[-2000:]  # Last 2000 characters
            if 'IMMEDIATE SYNCHRONOUS FIX' in script_end:
                print(f"  ✅ Ultra-aggressive fix is at the end of script")
            else:
                print(f"  ❌ Ultra-aggressive fix not found at end of script")
                
        else:
            print(f"  ❌ Script failed to load: {script_response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Script load error: {e}")
        return False
    
    # Test 3: Check if there are any cache-busting parameters
    print("\n🔄 Step 3: Testing cache-busting...")
    try:
        # Try with cache-busting parameter
        timestamp = int(time.time())
        cache_bust_url = f"{base_url}/static/js/lemma-shield-widget.js?v={timestamp}"
        cache_response = requests.get(cache_bust_url)
        
        if cache_response.status_code == 200:
            print(f"  ✅ Cache-busted script loads: {cache_response.status_code}")
            
            # Compare content to see if it's the same
            if len(cache_response.text) == script_size:
                print(f"  ✅ Cache-busted script size matches: {len(cache_response.text)} bytes")
            else:
                print(f"  ⚠️ Cache-busted script size differs: {len(cache_response.text)} vs {script_size} bytes")
                
        else:
            print(f"  ❌ Cache-busted script failed: {cache_response.status_code}")
            
    except Exception as e:
        print(f"  ❌ Cache-bust test error: {e}")
    
    # Test 4: Create a simple inline test
    print("\n🧪 Step 4: Generating inline test code...")
    
    inline_test = """
    // IMMEDIATE DIAGNOSTIC TEST - Paste this in browser console
    console.log('🔍 DIAGNOSTIC: Script loading test');
    
    // Check if script elements exist
    const scriptElements = document.querySelectorAll('script[src*="lemma-shield-widget"]');
    console.log('📄 Shield widget script elements found:', scriptElements.length);
    
    scriptElements.forEach((script, index) => {
        console.log(`Script ${index + 1}:`, script.src);
        console.log('  - Loaded:', script.readyState || 'unknown');
        console.log('  - Error:', script.onerror ? 'has error handler' : 'no error handler');
    });
    
    // Check for any JavaScript errors
    window.addEventListener('error', (e) => {
        if (e.filename && e.filename.includes('lemma-shield-widget')) {
            console.error('🚨 Shield widget script error:', e.message, 'at line', e.lineno);
        }
    });
    
    // Try to manually load and execute the script
    const testScript = document.createElement('script');
    testScript.src = '/static/js/lemma-shield-widget.js?test=' + Date.now();
    testScript.onload = () => {
        console.log('✅ Manual script load successful');
        console.log('🔍 Post-load check:');
        console.log('  - LemmaShieldWidget:', typeof LemmaShieldWidget);
        console.log('  - window.lemmaShield:', typeof window.lemmaShield);
        console.log('  - window.emergencyForceShow:', typeof window.emergencyForceShow);
    };
    testScript.onerror = (e) => {
        console.error('❌ Manual script load failed:', e);
    };
    document.head.appendChild(testScript);
    """
    
    print("\n🎯 RECOMMENDATION:")
    print("Copy and paste this diagnostic code in your browser console:")
    print("-" * 60)
    print(inline_test)
    print("-" * 60)
    
    return True

if __name__ == "__main__":
    test_shield_script_loading() 