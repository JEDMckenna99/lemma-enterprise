#!/usr/bin/env python3

import requests
import time

def test_deployed_methods():
    """Test if forceShow methods are now available after emergency fix"""
    
    url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/join-network"
    
    # JavaScript to test method availability after emergency fix
    test_script = """
    console.log('🔧 TESTING EMERGENCY PROTOTYPE FIX');
    
    // Wait for page to fully load
    setTimeout(() => {
        console.log('=== GLOBAL VARIABLES (POST-FIX) ===');
        console.log('LemmaShieldWidget:', typeof window.LemmaShieldWidget);
        console.log('lemmaShield:', typeof window.lemmaShield);
        console.log('lemmaShieldWidget:', typeof window.lemmaShieldWidget);
        console.log('LemmaShieldWidget.instance:', window.LemmaShieldWidget?.instance ? 'exists' : 'missing');
        
        console.log('\\n=== STATIC METHODS ON CLASS (POST-FIX) ===');
        if (window.LemmaShieldWidget) {
            console.log('Static methods:', Object.getOwnPropertyNames(window.LemmaShieldWidget));
            console.log('forceShow static:', typeof window.LemmaShieldWidget.forceShow);
            console.log('reset static:', typeof window.LemmaShieldWidget.reset);
        }
        
        console.log('\\n=== INSTANCE METHODS (POST-FIX) ===');
        if (window.LemmaShieldWidget?.instance) {
            console.log('Using LemmaShieldWidget.instance');
            console.log('forceShow instance:', typeof window.LemmaShieldWidget.instance.forceShow);
        }
        
        console.log('\\n=== PROTOTYPE METHODS (NEW) ===');
        if (window.LemmaShieldWidget) {
            console.log('forceShow on prototype:', typeof window.LemmaShieldWidget.prototype.forceShow);
            console.log('Prototype methods:', Object.getOwnPropertyNames(window.LemmaShieldWidget.prototype));
        }
        
        console.log('\\n=== CONVENIENCE METHODS (POST-FIX) ===');
        if (window.lemmaShield) {
            console.log('lemmaShield.forceShow:', typeof window.lemmaShield.forceShow);
            console.log('lemmaShield.show:', typeof window.lemmaShield.show);
            console.log('lemmaShield.getInstance:', typeof window.lemmaShield.getInstance);
        }
        
        console.log('\\n=== METHOD EXECUTION TESTS (POST-FIX) ===');
        
        // Test 1: Static method
        try {
            if (typeof window.LemmaShieldWidget?.forceShow === 'function') {
                console.log('✅ LemmaShieldWidget.forceShow() - AVAILABLE');
                // Don't actually call it in test
            } else {
                console.log('❌ LemmaShieldWidget.forceShow() - NOT A FUNCTION');
            }
        } catch (e) {
            console.log('❌ LemmaShieldWidget.forceShow() - ERROR:', e.message);
        }
        
        // Test 2: Instance method
        try {
            if (typeof window.lemmaShieldWidget?.forceShow === 'function') {
                console.log('✅ lemmaShieldWidget.forceShow() - AVAILABLE');
            } else {
                console.log('❌ lemmaShieldWidget.forceShow() - NOT AVAILABLE');
            }
        } catch (e) {
            console.log('❌ lemmaShieldWidget.forceShow() - ERROR:', e.message);
        }
        
        // Test 3: Convenience method
        try {
            if (typeof window.lemmaShield?.forceShow === 'function') {
                console.log('✅ lemmaShield.forceShow() - AVAILABLE');
            } else {
                console.log('❌ lemmaShield.forceShow() - NOT AVAILABLE');
            }
        } catch (e) {
            console.log('❌ lemmaShield.forceShow() - ERROR:', e.message);
        }
        
        // Test 4: Prototype method (new)
        try {
            if (window.LemmaShieldWidget?.instance && typeof window.LemmaShieldWidget.instance.forceShow === 'function') {
                console.log('✅ instance.forceShow() via prototype - AVAILABLE');
            } else {
                console.log('❌ instance.forceShow() via prototype - NOT AVAILABLE');
            }
        } catch (e) {
            console.log('❌ instance.forceShow() via prototype - ERROR:', e.message);
        }
        
        console.log('\\n🎯 EMERGENCY FIX TEST COMPLETE');
    }, 2000);
    """
    
    print("🧪 Testing emergency prototype fix deployment...")
    print(f"URL: {url}")
    print("=" * 50)
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print("✅ Page loads successfully")
            print("\n📋 Copy and paste this JavaScript into browser console:")
            print("=" * 50)
            print(test_script)
            print("=" * 50)
            print("\n🔍 Expected results after emergency fix:")
            print("✅ LemmaShieldWidget.forceShow: function (via prototype)")
            print("✅ lemmaShieldWidget.forceShow: function (via prototype)")
            print("✅ lemmaShield.forceShow: function (via convenience wrapper)")
            print("✅ LemmaShieldWidget.prototype.forceShow: function (NEW)")
            
        else:
            print(f"❌ Page load failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_deployed_methods() 