"""Check Stripe account configuration"""
import stripe

# API keys from Heroku
secret_key = "sk_test_51RJNLBDIouMeOMablPrCc6aZzxvHYK2RDQcTAPFdBeeInO3Oo763Md4naHlIuD4f2fsw6TRgrN9AbAZbPym3KZrA00h5jdtmDA"
publishable_key = "pk_test_51RJNLBDIouMeOMab56ZoLLf7qyXOfw2dWq8dDnhihzcc9hOHhw2xqyvzEUXbfZDsYyAnZNa5ADkycRpqUvDzMr3G00CgiM8efu"

print("Checking Stripe account configuration...")
print()

# Extract account IDs from keys
# Format: sk_test_51{ACCOUNT_ID}...
secret_account = secret_key.split('_')[2][:10] if len(secret_key.split('_')) > 2 else "Unknown"
pub_account = publishable_key.split('_')[2][:10] if len(publishable_key.split('_')) > 2 else "Unknown"

print(f"Secret Key Account Prefix: {secret_account}")
print(f"Publishable Key Account Prefix: {pub_account}")
print(f"Keys match: {secret_account == pub_account}")
print()

stripe.api_key = secret_key

# Get account info
try:
    account = stripe.Account.retrieve()
    print(f"Connected Account ID: {account.id}")
    print(f"Account Email: {account.email if hasattr(account, 'email') else 'N/A'}")
    print(f"Country: {account.country if hasattr(account, 'country') else 'N/A'}")
    print(f"Charges Enabled: {account.charges_enabled if hasattr(account, 'charges_enabled') else 'N/A'}")
    print(f"Payouts Enabled: {account.payouts_enabled if hasattr(account, 'payouts_enabled') else 'N/A'}")
except Exception as e:
    print(f"Error getting account: {e}")

print()

# Create a session and show its full details
print("Creating test checkout session...")
try:
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price': 'price_1RtBQFDIouMeOMabSXK43jDW',
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://lemma.id/subscription/success?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='https://lemma.id/pricing',
    )
    
    print(f"Session ID: {session.id}")
    print(f"Status: {session.status}")
    print(f"Mode: {session.mode}")
    print(f"Payment Status: {session.payment_status}")
    print(f"URL: {session.url}")
    print()
    print("Session livemode:", session.livemode)
    
except Exception as e:
    print(f"Error: {e}")


