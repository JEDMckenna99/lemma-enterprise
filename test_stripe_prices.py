"""Test Stripe price IDs"""
import stripe
import os

stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_51QJDkbP8RRlCYD4t8GWdrvJOlE6bZRnSqJ8Xzx8mKJHdVE3I8eOhCvMXZjNGq0gJNvJKFGP9t8QXzlW8NNQ6M2kN00XBuMjIuM')

print("Testing Stripe connection...")

# Test specific price IDs used in stripe_checkout.py
test_prices = [
    'price_1RtBQFDIouMeOMabSXK43jDW',  # starter
    'price_1RtBQGDIouMeOMabRGaVYg0A',  # professional
    'price_1RtBQGDIouMeOMab4DsImBZ3',  # enterprise
]

print("\nChecking price IDs used in code:")
for price_id in test_prices:
    try:
        price = stripe.Price.retrieve(price_id)
        amount = price.unit_amount / 100 if price.unit_amount else 'N/A'
        print(f"  OK: {price_id} - ${amount} {price.currency.upper()} - Active: {price.active}")
    except stripe.error.InvalidRequestError as e:
        print(f"  ERROR: {price_id} - {e.user_message}")
    except Exception as e:
        print(f"  ERROR: {price_id} - {str(e)}")

# List available prices
print("\nListing all active prices:")
try:
    prices = stripe.Price.list(limit=20, active=True)
    for p in prices.data:
        amount = p.unit_amount / 100 if p.unit_amount else 'metered'
        print(f"  {p.id}: ${amount} {p.currency.upper()}")
        if hasattr(p, 'product'):
            try:
                product = stripe.Product.retrieve(p.product)
                print(f"    Product: {product.name}")
            except:
                pass
except Exception as e:
    print(f"Error listing prices: {e}")


