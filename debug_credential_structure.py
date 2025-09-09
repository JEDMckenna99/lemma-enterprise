#!/usr/bin/env python3
"""Debug credential structure to see W3C compliance changes"""

import json

def debug_credential_structure():
    print("🔍 Debugging Current Credential Structure")
    print("=" * 50)
    
    try:
        import lemma_crypto
        
        # Create test credential
        issuer = lemma_crypto.PyMinimalIssuer()
        
        test_claims = {
            "packageType": "identity",
            "isHuman": "true",
            "verificationLevel": "high"
        }
        
        credential_json = issuer.issue_credential("did:lemma:test_subject", test_claims)
        credential = json.loads(credential_json)
        
        print("📋 Current Credential Structure:")
        print(json.dumps(credential, indent=2))
        
        print(f"\n🔍 Field Analysis:")
        for key, value in credential.items():
            print(f"   {key}: {type(value).__name__}")
            if key == 'credentialSubject':
                print(f"      Claims: {list(value.keys())}")
        
        return credential
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        return None

if __name__ == "__main__":
    debug_credential_structure()
