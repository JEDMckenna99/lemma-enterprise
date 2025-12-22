"""Create simplest possible checkout session"""
import stripe

# Use the secret key
stripe.api_key = "sk_test_51RJNLBDIouMeOMablPrCc6aZzxvHYK2RDQcTAPFdBeeInO3Oo763Md4naHlIuD4f2fsw6TRgrN9AbAZbPym3KZrA00h5jdtmDA"

print("Creating simple checkout session with price_data...")

try:
    # Try with inline price_data instead of existing price ID
    session = stripe.checkout.Session.create(
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': 'Test Product',
                },
                'unit_amount': 2000,  # $20.00
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://lemma.id/subscription/success',
        cancel_url='https://lemma.id/pricing',
    )
    
    print(f"Session ID: {session.id}")
    print(f"Status: {session.status}")
    print(f"URL: {session.url}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()


