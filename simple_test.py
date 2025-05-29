import requests

print('🧪 Testing CSRF Token and JavaScript Loading...')

try:
    response = requests.get('https://lemma-enterprise-0f6ba17076c1.herokuapp.com')
    print(f'Status: {response.status_code}')
    
    if 'csrf-token' in response.text:
        print('✅ CSRF meta tag found')
    else:
        print('❌ CSRF meta tag missing')

    scripts = ['lemma-wallet.js', 'lemma-gate-secure.js', 'lemma-crypto-hardened.js', 'lemma-gate-enhanced.js']
    for script in scripts:
        if script in response.text:
            print(f'✅ Found {script}')
        else:
            print(f'❌ Missing {script}')
            
    # Test CSRF endpoint
    print('\n🔑 Testing CSRF endpoint...')
    session = requests.Session()
    csrf_response = session.get('https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/generate-csrf')
    if csrf_response.status_code == 200:
        print('✅ CSRF endpoint working')
        print(f'Response: {csrf_response.json()}')
    else:
        print(f'❌ CSRF endpoint failed: {csrf_response.status_code}')
        
except Exception as e:
    print(f'❌ Error: {e}') 