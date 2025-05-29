import requests

print('🔐 Testing Security Logging Endpoint...')

session = requests.Session()

# Get CSRF token
csrf_resp = session.get('https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/generate-csrf')
csrf_token = csrf_resp.json()['csrf_token']
print(f'CSRF Token: {csrf_token[:20]}...')

# Test security logging
log_resp = session.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/v2/security-log',
    json={'event': 'crypto_status_verified', 'data': {'test': True}},
    headers={'X-CSRF-Token': csrf_token}
)

print(f'Security Log Status: {log_resp.status_code}')
if log_resp.status_code == 200:
    print(f'✅ Response: {log_resp.json()}')
else:
    print(f'❌ Error: {log_resp.text}') 