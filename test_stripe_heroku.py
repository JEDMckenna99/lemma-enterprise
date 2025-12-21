"""Test Stripe with Heroku keys"""
import stripe
import os

# Use the STRIPE_SECRET_KEY from Heroku
api_key = "sk_test_51RJNLBDIouMeOMablPrCc6aZzxvHYK2RDQcTAPFdBeeInO3Oo763Md4naHlIuD4f2fsw6TRgrN9AbAZbPym3KZrA00h5jdtmDA"
stripe.api_key = api_key

print(f"Testing with key ending in: ...{api_key[-6:]}")

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
        print(f"  INVALID: {price_id} - {e.user_message}")
    except Exception as e:
        print(f"  ERROR: {price_id} - {str(e)}")

# List available prices
print("\nListing all active prices in this Stripe account:")
try:
    prices = stripe.Price.list(limit=20, active=True)
    print(f"Found {len(prices.data)} active prices")
    for p in prices.data:
        amount = p.unit_amount / 100 if p.unit_amount else 'metered'
        print(f"  {p.id}: ${amount} {p.currency.upper()}")
        try:
            product = stripe.Product.retrieve(p.product)
            print(f"    -> Product: {product.name}")
        except:
            pass
except Exception as e:
    print(f"Error listing prices: {e}")

# List products
print("\nListing all products:")
try:
    products = stripe.Product.list(limit=20, active=True)
    print(f"Found {len(products.data)} active products")
    for prod in products.data:
        print(f"  {prod.id}: {prod.name}")
except Exception as e:
    print(f"Error listing products: {e}")

