"""Create and verify a Stripe checkout session"""
import stripe

# Use the STRIPE_SECRET_KEY from Heroku
api_key = "sk_test_51RJNLBDIouMeOMablPrCc6aZzxvHYK2RDQcTAPFdBeeInO3Oo763Md4naHlIuD4f2fsw6TRgrN9AbAZbPym3KZrA00h5jdtmDA"
stripe.api_key = api_key

print("Creating checkout session...")

try:
    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price': 'price_1RtBQFDIouMeOMabSXK43jDW',  # Starter $29
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://lemma.id/subscription/success?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='https://lemma.id/pricing?canceled=true',
        metadata={
            'plan_type': 'starter',
            'plan_name': 'Lemma Shield - Starter'
        }
    )
    
    print(f"Session ID: {checkout_session.id}")
    print(f"Session URL: {checkout_session.url}")
    print(f"Status: {checkout_session.status}")
    print(f"\nOpen this URL in your browser:")
    print(checkout_session.url)
    
except Exception as e:
    print(f"Error: {e}")


