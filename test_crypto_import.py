#!/usr/bin/env python3
"""Test crypto import and available classes"""

try:
    import lemma_crypto
    print("✅ Successfully imported lemma_crypto")
    
    # Check what's available
    available = [x for x in dir(lemma_crypto) if not x.startswith('_')]
    print(f"📋 Available classes/functions: {available}")
    
    # Try to create instances of available classes
    for class_name in available:
        if class_name.startswith('Py'):
            try:
                cls = getattr(lemma_crypto, class_name)
                print(f"✅ Found class: {class_name}")
                if class_name == 'PyCredentialIssuer':
                    instance = cls()
                    print(f"✅ Created PyCredentialIssuer instance")
                    did = instance.get_did()
                    print(f"✅ Got DID: {did[:50]}...")
                elif class_name == 'PyLemmaCore':
                    instance = cls()
                    print(f"✅ Created PyLemmaCore instance")
            except Exception as e:
                print(f"❌ Failed to create {class_name}: {e}")
    
except ImportError as e:
    print(f"❌ Failed to import lemma_crypto: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
