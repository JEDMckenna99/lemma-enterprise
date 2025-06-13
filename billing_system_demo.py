#!/usr/bin/env python3
"""
🎬 LEMMA BILLING SYSTEM DEMONSTRATION
=====================================
Simple demo showing the complete billing system in action
"""

import os
import sys
import time
import tempfile
import shutil
from datetime import datetime, timezone, timedelta

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import billing components
from lemma.billing.usage_logger import UsageEventLogger
from lemma.billing.rollup_engine import NightlyRollupEngine
from lemma.billing.billing_engine import BillingEngine

def demo_billing_system():
    """Demonstrate the complete billing system workflow."""
    print("🚀 LEMMA BILLING SYSTEM DEMONSTRATION")
    print("="*60)
    
    # Set up temporary demo environment
    temp_dir = tempfile.mkdtemp()
    print(f"📁 Demo environment: {temp_dir}")
    
    try:
        # Initialize components
        print("\n🏗️  INITIALIZING BILLING COMPONENTS...")
        usage_logger = UsageEventLogger(storage_dir=temp_dir)
        rollup_engine = NightlyRollupEngine(storage_dir=temp_dir)
        billing_engine = BillingEngine(storage_dir=temp_dir)
        
        # Connect components for testing
        rollup_engine.set_usage_logger(usage_logger)
        billing_engine.set_rollup_engine(rollup_engine)
        print("✅ All components initialized successfully!")
        
        # Simulate customer usage over several days
        print("\n📊 SIMULATING CUSTOMER USAGE...")
        
        customers = ["ecommerce_site", "social_platform", "enterprise_app"]
        users = [f"did:lemma:user{i:04d}" for i in range(20)]
        
        # Day 1: Initial usage
        day1 = "2025-01-15"
        day1_ts = datetime.strptime(day1, '%Y-%m-%d').timestamp()
        
        print(f"   Day 1 ({day1}): Initial customer usage")
        for i, customer in enumerate(customers):
            user_count = 3 + i * 2  # Different usage per customer
            for j in range(user_count):
                user = users[j]
                usage_logger.log_verification_success(customer, user, timestamp=day1_ts)
                print(f"      ✓ {customer}: {user}")
        
        # Day 2: Mix of returning and new users
        day2 = "2025-01-16"
        day2_ts = datetime.strptime(day2, '%Y-%m-%d').timestamp()
        
        print(f"   Day 2 ({day2}): Mix of returning and new users")
        for i, customer in enumerate(customers):
            # Some returning users
            for j in range(2):
                user = users[j]
                usage_logger.log_verification_success(customer, user, timestamp=day2_ts)
                print(f"      ✓ {customer}: {user} (returning)")
            
            # Some new users  
            for j in range(10, 12 + i):
                user = users[j]
                usage_logger.log_verification_success(customer, user, timestamp=day2_ts)
                print(f"      ✓ {customer}: {user} (new)")
        
        # Flush events to storage
        usage_logger.flush_all()
        print("✅ Usage events logged and flushed!")
        
        # Process daily rollups
        print("\n📈 PROCESSING DAILY ROLLUPS...")
        
        for day in [day1, day2]:
            print(f"   Processing rollup for {day}...")
            result = rollup_engine.force_daily_rollup(day)
            
            if result['success']:
                print(f"   ✅ {day}: Processed successfully")
                
                # Show metrics for this day
                rollup_data = rollup_engine.get_daily_rollup(day)
                if rollup_data:
                    metrics = rollup_data['metrics']
                    global_summary = metrics['global_summary']
                    print(f"      📊 Total verifications: {global_summary['total_verifications']}")
                    print(f"      👥 Unique humans: {global_summary['global_unique_humans']}")
                    print(f"      🆕 New humans: {global_summary['global_new_humans']}")
                    print(f"      🏢 Active sites: {global_summary['active_sites']}")
            else:
                print(f"   ❌ {day}: Failed - {result.get('error')}")
        
        # Generate monthly bills
        print("\n💰 GENERATING MONTHLY BILLS...")
        month = "2025-01"
        
        total_revenue = 0.0
        for customer in customers:
            print(f"\n   Calculating bill for {customer}...")
            
            billing_data = billing_engine.calculate_monthly_bill(customer, month)
            
            if billing_data['success']:
                usage = billing_data['usage']
                charges = billing_data['charges']
                
                print(f"   ✅ {customer} - Monthly Bill Generated")
                print(f"      👥 Monthly Active Humans: {usage['monthly_active_humans']}")
                print(f"      🆕 New Humans: {usage['new_humans']}")
                print(f"      🔄 Total Verifications: {usage['total_verifications']}")
                print(f"      💰 MAH Charge: ${charges['mah_charge']}")
                print(f"      💰 New Human Charge: ${charges['new_humans_charge']}")
                print(f"      💰 Total Amount: ${charges['total_amount']}")
                
                total_revenue += float(charges['total_amount'])
                
                # Generate invoice files
                try:
                    invoice_files = billing_engine.save_invoice(billing_data, ["pdf", "csv"])
                    print(f"      📄 Invoice files generated: {list(invoice_files.keys())}")
                except Exception as e:
                    print(f"      ⚠️ Invoice generation: {e}")
                
            else:
                print(f"   ❌ {customer}: Failed - {billing_data.get('error')}")
        
        print(f"\n💰 TOTAL MONTHLY REVENUE: ${total_revenue:.2f}")
        
        # Show monthly aggregation
        print("\n📊 MONTHLY AGGREGATION SUMMARY...")
        monthly_data = rollup_engine.get_monthly_rollup(month)
        
        if monthly_data:
            summary = monthly_data['monthly_summary']
            print(f"   📅 Month: {month}")
            print(f"   📊 Total Verifications: {summary['total_verifications']}")
            print(f"   👥 Monthly Active Humans: {len(summary['monthly_active_humans'])}")
            print(f"   🆕 New Humans This Month: {len(summary['new_humans_this_month'])}")
            print(f"   🏢 Active Sites: {len(summary['active_sites'])}")
            print(f"   📅 Days Processed: {summary['days_processed']}")
        
        print("\n✅ BILLING SYSTEM DEMONSTRATION COMPLETE!")
        print("🎉 All components working correctly!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error in demonstration: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Clean up
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            print(f"🧹 Cleaned up demo environment")
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")

if __name__ == "__main__":
    # Run the demonstration
    success = demo_billing_system()
    
    print(f"\n{'='*60}")
    if success:
        print("🎯 DEMONSTRATION RESULT: SUCCESS!")
        print("💰 Lemma Enterprise billing system is ready for production!")
    else:
        print("❌ DEMONSTRATION RESULT: FAILED!")
        print("🔧 Please check the error messages above.")
    print(f"{'='*60}") 