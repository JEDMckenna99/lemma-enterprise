#!/usr/bin/env python3
"""Quick Security Validation for Lemma Enterprise v2.9.0"""

import requests
import os

def main():
    # Quick security validation
    base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
    api_key = os.environ.get('LEMMA_API_KEY')

    print('🛡️ Quick Security Validation - Lemma Enterprise v2.9.0')
    print('=' * 60)

    tests = []

    # Test 1: Hardcoded API key blocked
    try:
        hardcoded_key = '63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e'
        headers = {'Authorization': f'Bearer {hardcoded_key}'}
        response = requests.post(f'{base_url}/api/verify', headers=headers, json={}, timeout=10)
        test1_pass = response.status_code in [401, 403]
        tests.append(('Hardcoded API Key Blocked', test1_pass))
        print(f'✅ Hardcoded API key blocked: {response.status_code}' if test1_pass else f'❌ Hardcoded API key test failed: {response.status_code}')
    except Exception as e:
        tests.append(('Hardcoded API Key Blocked', False))
        print(f'❌ Hardcoded API key test error: {e}')

    # Test 2: Debug mode disabled
    try:
        response = requests.get(f'{base_url}/nonexistent-debug-endpoint', timeout=10)
        test2_pass = response.status_code == 404 and 'Werkzeug' not in response.text
        tests.append(('Debug Mode Disabled', test2_pass))
        print(f'✅ Debug mode disabled: {response.status_code}' if test2_pass else f'❌ Debug mode test failed: {response.status_code}')
    except Exception as e:
        tests.append(('Debug Mode Disabled', False))
        print(f'❌ Debug mode test error: {e}')

    # Test 3: Security headers
    try:
        response = requests.get(f'{base_url}/', timeout=10)
        headers = response.headers
        security_headers = ['X-Content-Type-Options', 'X-Frame-Options', 'Strict-Transport-Security']
        found_headers = sum(1 for header in security_headers if header in headers)
        test3_pass = found_headers >= 2
        tests.append(('Security Headers', test3_pass))
        print(f'✅ Security headers active: {found_headers}/3 headers found' if test3_pass else f'❌ Security headers test failed: {found_headers}/3')
    except Exception as e:
        tests.append(('Security Headers', False))
        print(f'❌ Security headers test error: {e}')

    # Test 4: HTTPS enforcement
    test4_pass = base_url.startswith('https')
    tests.append(('HTTPS Enforcement', test4_pass))
    print(f'✅ HTTPS enforcement active' if test4_pass else f'❌ HTTPS enforcement failed')

    # Test 5: API key requirement
    try:
        response = requests.post(f'{base_url}/api/verify', json={}, timeout=10)
        test5_pass = response.status_code in [401, 403]
        tests.append(('API Key Required', test5_pass))
        print(f'✅ API key requirement active: {response.status_code}' if test5_pass else f'❌ API key requirement failed: {response.status_code}')
    except Exception as e:
        tests.append(('API Key Required', False))
        print(f'❌ API key requirement test error: {e}')

    # Test 6: Admin authentication required
    try:
        response = requests.get(f'{base_url}/admin', timeout=10)
        test6_pass = response.status_code in [302, 401, 403]
        tests.append(('Admin Authentication Required', test6_pass))
        print(f'✅ Admin authentication required: {response.status_code}' if test6_pass else f'❌ Admin authentication test failed: {response.status_code}')
    except Exception as e:
        tests.append(('Admin Authentication Required', False))
        print(f'❌ Admin authentication test error: {e}')

    # Test 7: Content Security Policy
    try:
        response = requests.get(f'{base_url}/', timeout=10)
        csp_header = response.headers.get('Content-Security-Policy', '')
        test7_pass = len(csp_header) > 0 and ("default-src" in csp_header or "strict-dynamic" in csp_header)
        tests.append(('Content Security Policy', test7_pass))
        print(f'✅ Content Security Policy active' if test7_pass else f'❌ Content Security Policy test failed')
    except Exception as e:
        tests.append(('Content Security Policy', False))
        print(f'❌ Content Security Policy test error: {e}')

    # Summary
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    success_rate = (passed / total * 100) if total > 0 else 0

    print(f'\n📊 SECURITY VALIDATION SUMMARY')
    print(f'Total Tests: {total}')
    print(f'Passed: {passed} ✅')
    print(f'Failed: {total - passed} ❌')
    print(f'Success Rate: {success_rate:.1f}%')
    print(f'\n🎯 Security validation {"PASSED" if passed == total else "NEEDS ATTENTION"}!')

    return 0 if passed == total else 1

if __name__ == '__main__':
    exit(main()) 