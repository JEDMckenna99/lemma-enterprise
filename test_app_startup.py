#!/usr/bin/env python3
"""
Test script to verify the application can start properly.
"""

import os
import sys

# Set environment variables to prevent production validation errors
os.environ['LEMMA_API_KEY'] = 'test-key'
os.environ['LEMMA_SECRET_KEY'] = 'test-secret-key'
os.environ['DATABASE_URL'] = 'sqlite:///test.db'
os.environ['FLASK_ENV'] = 'development'

try:
    print("Testing application startup...")
    from app import create_app
    
    print("Creating app...")
    app = create_app()
    
    print("App created successfully!")
    
    print("\nAvailable routes:")
    with app.app_context():
        for rule in app.url_map.iter_rules():
            print(f"  {rule.rule} -> {rule.endpoint}")
    
    print(f"\nTotal routes: {len(list(app.url_map.iter_rules()))}")
    
    # Test if root route exists
    root_routes = [rule for rule in app.url_map.iter_rules() if rule.rule == '/']
    if root_routes:
        print(f"✅ Root route (/) found: {root_routes[0].endpoint}")
    else:
        print("❌ Root route (/) NOT found")
    
    # Test if health routes exist
    health_routes = [rule for rule in app.url_map.iter_rules() if 'health' in rule.rule]
    if health_routes:
        print(f"✅ Health routes found: {[r.rule for r in health_routes]}")
    else:
        print("❌ Health routes NOT found")
        
    print("\n✅ Application startup test PASSED")
    
except Exception as e:
    print(f"❌ Application startup test FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1) 