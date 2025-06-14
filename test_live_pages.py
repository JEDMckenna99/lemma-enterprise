#!/usr/bin/env python3
"""
Test Live Site Page Structure
Check which pages actually exist on the deployed site
"""

import requests
import time

base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'

# Test main pages that should exist based on diagrams
pages_to_test = [
    '/',
    '/onboarding',
    '/onboarding/register', 
    '/onboarding/verify',
    '/onboarding/dashboard',
    '/onboarding/api-keys',
    '/onboarding/usage',
    '/onboarding/integration',
    '/admin/login',
    '/admin',
    '/verify',
    '/protected',
    '/gate-demo',
    '/api-docs',
    '/billing/invoices',
    '/billing/payment-methods',
    '/billing/identity-complete',
    '/widget-test',
    '/error'
]

def test_pages():
    print('🔍 LIVE SITE PAGE STRUCTURE TEST')
    print('=' * 50)
    print(f'Testing: {base_url}')
    print()

    working_pages = []
    missing_pages = []
    redirect_pages = []

    for page in pages_to_test:
        try:
            r = requests.get(base_url + page, timeout=10, allow_redirects=False)
            if r.status_code == 200:
                print(f'✅ {page} - Working ({r.status_code})')
                working_pages.append(page)
            elif r.status_code in [301, 302, 303, 307, 308]:
                print(f'🔄 {page} - Redirect ({r.status_code})')
                redirect_pages.append(page)
            elif r.status_code == 404:
                print(f'❌ {page} - Not Found (404)')
                missing_pages.append(page)
            else:
                print(f'⚠️  {page} - Status {r.status_code}')
                missing_pages.append(page)
        except Exception as e:
            print(f'❌ {page} - Error: {str(e)[:50]}')
            missing_pages.append(page)

    print()
    print('📊 SUMMARY')
    print('-' * 20)
    print(f'Working Pages: {len(working_pages)}/{len(pages_to_test)}')
    print(f'Redirect Pages: {len(redirect_pages)}')
    print(f'Missing Pages: {len(missing_pages)}')

    if missing_pages:
        print()
        print('❌ MISSING PAGES:')
        for page in missing_pages:
            print(f'   {page}')
    
    if redirect_pages:
        print()
        print('🔄 REDIRECT PAGES:')
        for page in redirect_pages:
            print(f'   {page}')

    print()
    print('✅ WORKING PAGES:')
    for page in working_pages:
        print(f'   {page}')

    return working_pages, missing_pages, redirect_pages

if __name__ == "__main__":
    test_pages() 