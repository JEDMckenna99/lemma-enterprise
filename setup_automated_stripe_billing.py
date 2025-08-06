#!/usr/bin/env python3
"""
Setup Fully Automated Stripe Billing for Lemma Shield
- Creates Meter for tracking verified users
- Sets up metered pricing for $0.10/user/month
- Creates setup fee product for $2.00/new user
- Enables automatic recurring billing
"""

import stripe
import os
import json

# Set up Stripe API key
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_51QJDkbP8RRlCYD4t8GWdrvJOlE6bZRnSqJ8Xzx8mKJHdVE3I8eOhCvMXZjNGq0gJNvJKFGP9t8QXzlW8NNQ6M2kN00XBuMjIuM')

def setup_automated_billing():
    """Set up fully automated metered billing system"""
    
    config = {}
    
    try:
        print("🚀 Setting up Automated Stripe Billing for Lemma Shield")
        print("=" * 60)
        
        # Step 1: Create Meter for tracking verified users
        print("\n1️⃣ Creating Meter for verified users...")
        meter = stripe.billing.Meter.create(
            display_name="Lemma Shield - Verified Users",
            event_name="lemma_verified_user",
            customer_mapping={
                "event_payload_key": "customer_id",
                "type": "by_id"
            },
            default_aggregation={
                "formula": "sum"
            }
        )
        config['meter_id'] = meter.id
        print(f"✅ Meter created: {meter.id}")
        
        # Step 2: Create Product for per-user billing
        print("\n2️⃣ Creating product for per-user billing...")
        per_user_product = stripe.Product.create(
            name="Lemma Shield - Per User",
            description="Monthly billing for verified users ($0.10 per user per month)",
            metadata={
                "service": "lemma_shield",
                "billing_type": "per_user_monthly"
            }
        )
        config['per_user_product_id'] = per_user_product.id
        print(f"✅ Product created: {per_user_product.id}")
        
        # Step 3: Create Metered Price for $0.10/user/month
        print("\n3️⃣ Creating metered price for $0.10/user/month...")
        metered_price = stripe.Price.create(
            product=per_user_product.id,
            unit_amount=10,  # $0.10 in cents
            currency="usd",
            recurring={
                "interval": "month",
                "usage_type": "metered"
            },
            billing_scheme="per_unit",
            meter=meter.id,
            nickname="Per User Monthly"
        )
        config['metered_price_id'] = metered_price.id
        print(f"✅ Metered price created: {metered_price.id}")
        
        # Step 4: Create Product for setup fee
        print("\n4️⃣ Creating product for setup fee...")
        setup_product = stripe.Product.create(
            name="Lemma Shield - Setup Fee",
            description="One-time setup fee for new user verification ($2.00 per user)",
            metadata={
                "service": "lemma_shield", 
                "billing_type": "setup_fee"
            }
        )
        config['setup_product_id'] = setup_product.id
        print(f"✅ Setup product created: {setup_product.id}")
        
        # Step 5: Create One-time Price for $2.00 setup fee
        print("\n5️⃣ Creating one-time price for $2.00 setup fee...")
        setup_price = stripe.Price.create(
            product=setup_product.id,
            unit_amount=200,  # $2.00 in cents
            currency="usd",
            nickname="Setup Fee Per User"
        )
        config['setup_price_id'] = setup_price.id
        print(f"✅ Setup price created: {setup_price.id}")
        
        # Step 6: Create Checkout Session template
        print("\n6️⃣ Testing Checkout Session creation...")
        # This is just a test - in production, we'll create sessions dynamically
        test_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{
                'price': metered_price.id,
                'quantity': 1,
            }],
            success_url='https://lemma.id/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='https://lemma.id/pricing',
            metadata={
                'service': 'lemma_shield',
                'billing_type': 'per_user'
            }
        )
        print(f"✅ Test checkout session created: {test_session.id}")
        
        # Save configuration
        config_file = 'stripe_config.json'
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Display final configuration
        print("\n" + "=" * 60)
        print("🎉 AUTOMATED BILLING SETUP COMPLETE!")
        print("=" * 60)
        print(f"Meter ID:           {config['meter_id']}")
        print(f"Per-User Product:   {config['per_user_product_id']}")
        print(f"Metered Price:      {config['metered_price_id']}")
        print(f"Setup Product:      {config['setup_product_id']}")
        print(f"Setup Price:        {config['setup_price_id']}")
        print(f"Config saved to:    {config_file}")
        print("=" * 60)
        
        print("\n✅ FEATURES ENABLED:")
        print("• Automatic monthly billing based on usage")
        print("• Real-time user tracking with Meter API")
        print("• Stripe Checkout for subscription signup")
        print("• Automated invoice generation")
        print("• Usage-based pricing: $0.10/user/month")
        print("• Setup fee: $2.00/new user")
        
        return config
        
    except Exception as e:
        print(f"❌ Error setting up automated billing: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    config = setup_automated_billing()
    if config:
        print(f"\n🚀 Ready to implement automated billing!")
        print("Next: Update your application code to use these IDs")
    else:
        print("\n💥 Setup failed - check errors above")