import requests
import sys

# Test the problematic pages mentioned in the summary
test_pages = [
    '/protected',
    '/admin/login', 
    '/widget-test',
    '/api-docs',
    '/verify'
]

base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
print('Testing problematic pages for 500 errors...')
print('=' * 50)

for page in test_pages:
    try:
        response = requests.get(f'{base_url}{page}', timeout=10)
        status = response.status_code
        if status == 500:
            print(f'❌ {page}: {status} - SERVER ERROR')
            print(f'   Response: {response.text[:200]}...')
        elif status == 200:
            print(f'✅ {page}: {status} - OK')
        else:
            print(f'⚠️  {page}: {status} - {response.reason}')
    except Exception as e:
        print(f'💥 {page}: ERROR - {str(e)}')

print()
print('Test completed.') 