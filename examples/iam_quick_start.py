"""
Lemma IAM - Quick Start Example
Shows how to integrate IAM-only (no PoH required) in 5 minutes
"""

import requests
import json

# Configuration
LEMMA_API_BASE = "https://lemma.id"
YOUR_API_KEY = "your-api-key-here"  # Get from lemma.id/register
YOUR_SITE_ID = "your-site-id-here"  # Get from registration

def step1_register_site():
    """
    Step 1: Register your site (one-time setup)
    """
    print("\n" + "="*60)
    print("STEP 1: Register Your Site")
    print("="*60)
    
    response = requests.post(
        f"{LEMMA_API_BASE}/api/v1/sites/register",
        headers={"X-API-Key": YOUR_API_KEY},
        json={
            "site_domain": "yourcompany.com",
            "company_name": "Your Company Inc",
            "admin_email": "admin@yourcompany.com",
            "plan": "professional"
        }
    )
    
    data = response.json()
    print(f"✅ Site registered!")
    print(f"   Site ID: {data['site_id']}")
    print(f"   API Key: {data['api_key']}")
    print(f"   Issuer DID: {data['issuer_did'][:50]}...")
    print(f"\n💡 Save these credentials - you'll need them!")
    
    return data

def step2_define_permissions(site_id: str, api_key: str):
    """
    Step 2: Define your permission levels
    """
    print("\n" + "="*60)
    print("STEP 2: Define Permissions")
    print("="*60)
    
    # Define admin permission
    response = requests.post(
        f"{LEMMA_API_BASE}/api/v1/sites/{site_id}/permissions",
        headers={"X-API-Key": api_key},
        json={
            "permission_id": "admin",
            "display_name": "Administrator",
            "scope": ["*"],  # Full access
            "description": "Full administrative access"
        }
    )
    
    print(f"✅ Created 'admin' permission (full access)")
    
    # Define user permission
    response = requests.post(
        f"{LEMMA_API_BASE}/api/v1/sites/{site_id}/permissions",
        headers={"X-API-Key": api_key},
        json={
            "permission_id": "user",
            "display_name": "Regular User",
            "scope": ["profile:*", "posts:read"],  # Limited access
            "description": "Regular user access"
        }
    )
    
    print(f"✅ Created 'user' permission (limited access)")

def step3_grant_permission(site_id: str, api_key: str, user_email: str):
    """
    Step 3: Grant permission to a user
    """
    print("\n" + "="*60)
    print("STEP 3: Grant Permission to User")
    print("="*60)
    
    # Create user DID (in production, user would have their own DID)
    user_did = f"did:lemma:user_{user_email.replace('@', '_at_')}"
    
    response = requests.post(
        f"{LEMMA_API_BASE}/api/v1/sites/{site_id}/users/{user_did}/permissions",
        headers={"X-API-Key": api_key},
        json={
            "permission_id": "admin",
            "expiry_days": 90
        }
    )
    
    data = response.json()
    credential = data['credential']
    
    print(f"✅ Permission granted to {user_email}")
    print(f"   Credential ID: {credential['id']}")
    print(f"   ⚡ Issue time: {data['issue_time_us']:.2f}µs")
    print(f"\n💡 Send this credential to user's browser to store in wallet:")
    print(f"   window.lemmaWallet.storeCredential({json.dumps(credential, indent=2)})")
    
    return user_did, credential

def step4_verify_access(site_id: str, user_did: str, credential: dict):
    """
    Step 4: Verify user access (this happens on every request)
    """
    print("\n" + "="*60)
    print("STEP 4: Verify User Access")
    print("="*60)
    
    # Check if user can access /admin/users
    response = requests.post(
        f"{LEMMA_API_BASE}/api/v1/auth/verify",
        json={
            "site_id": site_id,
            "user_did": user_did,
            "resource": "/admin/users",
            "action": "read",
            "user_lemmas": [credential]
        }
    )
    
    data = response.json()
    
    if data['has_access']:
        print(f"✅ Access GRANTED")
        print(f"   Resource: /admin/users")
        print(f"   Action: read")
        print(f"   ⚡ Verification time: {data['verification_time_us']:.2f}µs")
        print(f"   🚀 That's 2,000-10,000x faster than Auth0!")
    else:
        print(f"❌ Access DENIED")

def client_side_example():
    """
    Step 5: Client-side integration (JavaScript)
    """
    print("\n" + "="*60)
    print("STEP 5: Client-Side Integration")
    print("="*60)
    
    js_code = """
// Initialize Lemma IAM
const lemmaIAM = new LemmaIAM({
    apiKey: 'your-api-key',
    siteId: 'your-site-id',
    useClientSide: true  // 0.36µs verification!
});

// Protect a route
async function checkAccess(resource, action) {
    const result = await lemmaIAM.verifyAccess(resource, action);
    
    if (result.hasAccess) {
        console.log(`✅ Access granted (${result.verificationTimeUs}µs)`);
        // Show protected content
    } else {
        console.log('❌ Access denied');
        // Show error or redirect
    }
}

// Example: Protect admin page
checkAccess('/admin/users', 'read');
"""
    
    print("Add this to your HTML:")
    print(js_code)

def pricing_comparison():
    """
    Show pricing comparison
    """
    print("\n" + "="*60)
    print("💰 PRICING COMPARISON")
    print("="*60)
    
    users = [100, 1000, 10000]
    
    print(f"\n{'Users':<10} {'Lemma IAM':<15} {'Auth0':<15} {'Savings':<15}")
    print("-" * 60)
    
    for user_count in users:
        lemma_cost = user_count * 0.15
        auth0_cost = user_count * 3.5  # Average Auth0 pricing
        savings = ((auth0_cost - lemma_cost) / auth0_cost) * 100
        
        print(f"{user_count:<10} ${lemma_cost:<14.2f} ${auth0_cost:<14.2f} {savings:.0f}% cheaper")
    
    print("\n💡 Lemma IAM: $0.15/MAU (no Stripe Identity required)")
    print("💡 Auth0: $2-5/MAU")
    print("💡 Duo: $3-8/MAU")

def main():
    """
    Run complete quick start example
    """
    print("\n" + "="*80)
    print("🔐 LEMMA IAM - QUICK START GUIDE (5 MINUTES)")
    print("="*80)
    print("\nThis example shows how to:")
    print("  1. Register your site")
    print("  2. Define permissions")
    print("  3. Grant permissions to users")
    print("  4. Verify access (31-94µs!)")
    print("  5. Integrate client-side (0.36µs!)")
    
    # Uncomment to run real API calls:
    # site_data = step1_register_site()
    # step2_define_permissions(site_data['site_id'], site_data['api_key'])
    # user_did, credential = step3_grant_permission(
    #     site_data['site_id'], 
    #     site_data['api_key'],
    #     'john@yourcompany.com'
    # )
    # step4_verify_access(site_data['site_id'], user_did, credential)
    
    # Show client-side integration
    client_side_example()
    
    # Show pricing comparison
    pricing_comparison()
    
    print("\n" + "="*80)
    print("✅ QUICK START COMPLETE!")
    print("="*80)
    print("\n📚 Next steps:")
    print("  1. Sign up at https://lemma.id/register")
    print("  2. Get your API key")
    print("  3. Run this script with real credentials")
    print("  4. Integrate into your application")
    print("\n💬 Questions? Contact support@lemma.id")

if __name__ == "__main__":
    main()

