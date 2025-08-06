"""
Stripe Setup for Lemma Shield Subscriptions
Creates recurring monthly subscription prices
"""

import stripe
import os

# Use the same key that's working in the MCP tools
stripe.api_key = "sk_test_51QJDkbP8RRlCYD4t8GWdrvJOlE6bZRnSqJ8Xzx8mKJHdVE3I8eOhCvMXZjNGq0gJNvJKFGP9t8QXzlW8NNQ6M2kN00XBuMjIuM"

# Product IDs from the MCP creation
PRODUCTS = {
    'starter': 'prod_Sop4wNXXfKeLgF',
    'professional': 'prod_Sop4S5445NMOoJ', 
    'enterprise': 'prod_Sop4MBtTEhYNms'
}

def create_subscription_prices():
    """Create monthly recurring subscription prices"""
    
    prices_config = [
        {
            'product': PRODUCTS['starter'],
            'amount': 2900,  # $29/month
            'nickname': 'Starter Monthly Subscription',
            'name': 'Starter'
        },
        {
            'product': PRODUCTS['professional'], 
            'amount': 9900,  # $99/month
            'nickname': 'Professional Monthly Subscription',
            'name': 'Professional'
        },
        {
            'product': PRODUCTS['enterprise'],
            'amount': 49900,  # $499/month  
            'nickname': 'Enterprise Monthly Subscription',
            'name': 'Enterprise'
        }
    ]
    
    created_prices = []
    
    for config in prices_config:
        try:
            price = stripe.Price.create(
                product=config['product'],
                unit_amount=config['amount'],
                currency='usd',
                recurring={'interval': 'month'},
                nickname=config['nickname']
            )
            created_prices.append({
                'name': config['name'],
                'price_id': price.id,
                'amount': config['amount'],
                'product_id': config['product']
            })
            print(f"✅ Created {config['name']} subscription: {price.id}")
        except Exception as e:
            print(f"❌ Failed to create {config['name']} subscription: {e}")
    
    return created_prices

if __name__ == "__main__":
    print("🚀 Creating Lemma Shield subscription prices...")
    prices = create_subscription_prices()
    
    print(f"\n✅ Created {len(prices)} subscription prices:")
    for price in prices:
        amount_dollars = price['amount'] / 100
        print(f"  - {price['name']}: ${amount_dollars}/month (ID: {price['price_id']})")