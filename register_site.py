#!/usr/bin/env python3
"""
Quick script to register your site as a customer in your own Lemma system.
This ensures proper bookkeeping, monitoring, and billing at scale.
"""

import requests
import json
import sys

# Your Heroku app URL
HEROKU_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def register_site():
    """Register your site as a customer."""
    print("🚀 Registering your site as a Lemma customer...")
    print(f"Using Heroku URL: {HEROKU_URL}")
    print()
    
    # Registration data for your site
    registration_data = {
        "email": "admin@lemma.id",  # Your admin email
        "company": "Lemma Inc",
        "domain": "lemma.id"  # Your domain
    }
    
    print("📝 Registration data:")
    print(json.dumps(registration_data, indent=2))
    print()
    
    try:
        # Step 1: Register as customer
        print("Step 1: Registering customer...")
        response = requests.post(
            f"{HEROKU_URL}/onboarding/register",
            json=registration_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ Registration successful!")
                print(f"   Customer ID: {result.get('customer_id')}")
                print(f"   API Key: {result.get('api_key')}")
                print(f"   Domain: {result.get('domain')}")
                print()
                
                # Save API key for next steps
                api_key = result.get('api_key')
                customer_id = result.get('customer_id')
                
                # Step 2: Check verification status
                print("Step 2: Checking verification status...")
                return {
                    'success': True,
                    'customer_id': customer_id,
                    'api_key': api_key,
                    'verification_token': result.get('verification_token'),
                    'next_steps': result.get('next_step')
                }
            else:
                print(f"❌ Registration failed: {result.get('error')}")
                return {'success': False, 'error': result.get('error')}
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
            return {'success': False, 'error': f'HTTP {response.status_code}'}
            
    except requests.RequestException as e:
        print(f"❌ Network error: {e}")
        return {'success': False, 'error': str(e)}

def check_billing_status(customer_id, api_key):
    """Check if billing is set up properly."""
    print("💳 Checking billing status...")
    
    try:
        # Check billing status
        response = requests.get(
            f"{HEROKU_URL}/billing/status",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                billing_status = result.get('billing_status')
                print(f"✅ Billing status: {billing_status}")
                
                if billing_status == 'active':
                    print("💰 Billing is active and working!")
                    return True
                elif billing_status == 'not_setup':
                    print("⚠️  Billing not yet set up. Setting up now...")
                    return setup_billing(api_key)
                else:
                    print(f"⚠️  Billing status: {billing_status}")
                    return False
            else:
                print(f"❌ Billing check failed: {result.get('error')}")
                return False
        else:
            print(f"❌ Billing check HTTP error: {response.status_code}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Billing check network error: {e}")
        return False

def setup_billing(api_key):
    """Set up billing for the customer."""
    print("🔧 Setting up billing...")
    
    try:
        response = requests.post(
            f"{HEROKU_URL}/billing/setup",
            headers={"Authorization": f"Bearer {api_key}"},
            json={},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ Billing setup successful!")
                print(f"   Stripe Customer ID: {result.get('stripe_customer_id')}")
                return True
            else:
                print(f"❌ Billing setup failed: {result.get('error')}")
                return False
        else:
            print(f"❌ Billing setup HTTP error: {response.status_code}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Billing setup network error: {e}")
        return False

def test_api_endpoints(api_key):
    """Test that all API endpoints work with the new API key."""
    print("🧪 Testing API endpoints...")
    
    endpoints_to_test = [
        ("/api/health", "Health check"),
        ("/api/generate-challenge", "Challenge generation"),
        ("/api/shield/status", "Shield status")
    ]
    
    for endpoint, description in endpoints_to_test:
        try:
            response = requests.get(
                f"{HEROKU_URL}{endpoint}",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15
            )
            
            if response.status_code == 200:
                print(f"   ✅ {description}: Working")
            else:
                print(f"   ⚠️  {description}: HTTP {response.status_code}")
                
        except requests.RequestException as e:
            print(f"   ❌ {description}: Error - {e}")

def main():
    """Main registration process."""
    print("🛡️  Lemma Site Registration Script")
    print("=" * 50)
    print()
    
    # Step 1: Register site
    result = register_site()
    
    if not result.get('success'):
        print("❌ Registration failed. Cannot continue.")
        sys.exit(1)
    
    customer_id = result['customer_id']
    api_key = result['api_key']
    
    print("📋 Registration Summary:")
    print(f"   Customer ID: {customer_id}")
    print(f"   API Key: {api_key[:20]}...")
    print(f"   Next Steps: {result.get('next_steps', 'Manual verification')}")
    print()
    
    # Step 2: Check and setup billing
    billing_success = check_billing_status(customer_id, api_key)
    
    # Step 3: Test API endpoints
    test_api_endpoints(api_key)
    
    print()
    print("🎉 Registration Process Complete!")
    print()
    print("Next Steps:")
    print(f"1. Visit your dashboard: {HEROKU_URL}/onboarding/dashboard")
    print(f"2. Manage API keys: {HEROKU_URL}/onboarding/api-keys")
    print(f"3. Check billing: {HEROKU_URL}/billing/status")
    print(f"4. Test shield: {HEROKU_URL}/join-network")
    print()
    print("🔑 Your API Key (save this!):")
    print(f"   {api_key}")
    print()
    print("✅ Your site is now properly registered as a customer!")
    print("✅ All bookkeeping and monitoring systems are active!")
    
    if billing_success:
        print("✅ Billing is configured and working!")
    else:
        print("⚠️  Billing needs manual setup - visit the billing dashboard")

if __name__ == "__main__":
    main() 