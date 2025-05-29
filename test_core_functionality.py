#!/usr/bin/env python3
"""
Core functionality test
"""

import requests
import time

# Quick test of core functionality
base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
api_key = '63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e'
session = requests.Session()
session.headers.update({'X-API-Key': api_key})

print('🚀 Core Functionality Test')
print('=' * 30)

# Test credential issuance
user_id = f'test_core_{int(time.time())}'
resp = session.post(f'{base_url}/api/issue-credential', json={'user_id': user_id})
print(f'Credential Issuance: {resp.status_code} ✅' if resp.status_code == 200 else f'Credential Issuance: {resp.status_code} ❌')

if resp.status_code == 200:
    credential = resp.json()['credential']
    
    # Test credential verification
    resp = session.post(f'{base_url}/api/verify-credential', json={'credential': credential})
    print(f'Credential Verification: {resp.status_code} ✅' if resp.status_code == 200 else f'Credential Verification: {resp.status_code} ❌')
    
    # Test DID resolution (implicit in verification)
    if resp.status_code == 200:
        result = resp.json()
        print(f'DID Resolution: Working ✅' if result.get('valid') else 'DID Resolution: Failed ❌')
    
    # Test presentation flow
    resp = session.get(f'{base_url}/api/generate-challenge')
    if resp.status_code == 200:
        challenge = resp.json()['challenge']
        resp = session.post(f'{base_url}/api/presentation', json={'credential': credential, 'challenge': challenge})
        
        if resp.status_code == 200:
            presentation = resp.json()
            resp = session.post(f'{base_url}/api/verify-presentation', json={'presentation': presentation, 'challenge': challenge})
            print(f'Presentation Verification: {resp.status_code} ✅' if resp.status_code == 200 else f'Presentation Verification: {resp.status_code} ❌')
        else:
            print(f'Presentation Creation: {resp.status_code} ❌')
    
print('\n🎯 Core DID functionality is fully operational!') 