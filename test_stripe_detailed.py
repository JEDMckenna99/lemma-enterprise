"""Detailed Stripe account and checkout session diagnostics"""
import stripe
import json

# Use the secret key
stripe.api_key = "sk_test_51RJNLBDIouMeOMablPrCc6aZzxvHYK2RDQcTAPFdBeeInO3Oo763Md4naHlIuD4f2fsw6TRgrN9AbAZbPym3KZrA00h5jdtmDA"

print("=" * 60)
print("STRIPE DIAGNOSTICS")
print("=" * 60)

# 1. Check account
print("\n1. ACCOUNT INFO:")
try:
    account = stripe.Account.retrieve()
    print(f"  Account ID: {account.id}")
    print(f"  Type: {account.type if hasattr(account, 'type') else 'N/A'}")
    print(f"  Charges Enabled: {account.charges_enabled}")
    print(f"  Details Submitted: {account.details_submitted if hasattr(account, 'details_submitted') else 'N/A'}")
    
    # Check capabilities
    if hasattr(account, 'capabilities'):
        print(f"  Capabilities: {dict(account.capabilities)}")
except Exception as e:
    print(f"  Error: {e}")

# 2. Check if checkout is available
print("\n2. CHECKOUT SESSIONS LIST:")
try:
    sessions = stripe.checkout.Session.list(limit=5)
    print(f"  Found {len(sessions.data)} recent sessions")
    for s in sessions.data[:3]:
        print(f"    - {s.id}: {s.status}, payment_status={s.payment_status}")
except Exception as e:
    print(f"  Error: {e}")

# 3. Try payment link instead
print("\n3. TESTING PAYMENT LINK:")
try:
    # Create a payment link which is simpler
    payment_link = stripe.PaymentLink.create(
        line_items=[{
            'price': 'price_1RtBQFDIouMeOMabSXK43jDW',
            'quantity': 1,
        }],
    )
    print(f"  Payment Link ID: {payment_link.id}")
    print(f"  URL: {payment_link.url}")
    print(f"  Active: {payment_link.active}")
except Exception as e:
    print(f"  Error: {e}")

# 4. Retrieve and check session details
print("\n4. CREATING AND CHECKING SESSION:")
try:
    session = stripe.checkout.Session.create(
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {'name': 'Test'},
                'unit_amount': 1000,
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://lemma.id/success',
        cancel_url='https://lemma.id/cancel',
    )
    print(f"  Session ID: {session.id}")
    print(f"  Status: {session.status}")
    print(f"  URL present: {'Yes' if session.url else 'No'}")
    
    # Retrieve it back
    retrieved = stripe.checkout.Session.retrieve(session.id)
    print(f"  Retrieved Status: {retrieved.status}")
    print(f"  Amount Total: {retrieved.amount_total}")
    print(f"  Currency: {retrieved.currency}")
    
except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("DIAGNOSIS COMPLETE")
print("=" * 60)

