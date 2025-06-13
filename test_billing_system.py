#!/usr/bin/env python3
"""
🧪 LEMMA BILLING SYSTEM - COMPREHENSIVE TESTS
==============================================
End-to-end testing of usage metering and billing infrastructure
Tests the complete billing pipeline from events to invoices
"""

import json
import os
import sys
import time
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test imports
from lemma.billing.usage_logger import UsageEventLogger
from lemma.billing.rollup_engine import NightlyRollupEngine
from lemma.billing.billing_engine import BillingEngine

class TestUsageEventLogger:
    """Test the usage event logging system."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.logger = UsageEventLogger(storage_dir=self.temp_dir)
    
    def teardown_method(self):
        """Clean up test environment."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_log_verification_success(self):
        """Test logging successful verification events."""
        # Test basic event logging
        event_id = self.logger.log_verification_success(
            site_id="test_site_1",
            subject_did="did:test:user123",
            metadata={"test": True}
        )
        
        assert event_id is not None
        assert len(event_id) > 0
        
        # Flush buffer to ensure events are written
        self.logger.flush_all()
        
        # Check that event was stored
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        events = self.logger.get_daily_events(today)
        
        assert len(events) >= 1
        event = events[-1]  # Get last event
        assert event['site_id'] == "test_site_1"
        assert event['event_type'] == "verification_success"
        assert 'subject_did_hash' in event
        assert event['metadata']['test'] is True
    
    def test_multiple_sites_same_user(self):
        """Test same user verifying on multiple sites."""
        user_did = "did:test:user456"
        
        # Log events for same user on different sites
        self.logger.log_verification_success("site_a", user_did)
        self.logger.log_verification_success("site_b", user_did)
        self.logger.log_verification_success("site_c", user_did)
        
        self.logger.flush_all()
        
        # Check events were logged
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        events = self.logger.get_daily_events(today)
        
        assert len(events) >= 3
        
        # All events should have same DID hash
        did_hashes = [e['subject_did_hash'] for e in events[-3:]]
        assert len(set(did_hashes)) == 1  # Same user = same hash
        
        # But different site IDs
        site_ids = [e['site_id'] for e in events[-3:]]
        assert len(set(site_ids)) == 3  # Different sites
    
    def test_usage_stats(self):
        """Test usage statistics calculation."""
        # Log events across multiple days
        base_time = time.time() - 86400  # Yesterday
        
        for i in range(5):
            self.logger.log_verification_success(
                "test_site",
                f"did:test:user{i}",
                timestamp=base_time + (i * 1000)
            )
        
        self.logger.flush_all()
        
        # Get usage stats
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        stats = self.logger.get_usage_stats(yesterday, today)
        
        assert stats['total_verifications'] >= 5
        assert stats['unique_humans'] >= 5
        assert stats['sites'] >= 1
        assert 'test_site' in stats['site_breakdown']

class TestNightlyRollupEngine:
    """Test the nightly rollup processing."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.usage_logger = UsageEventLogger(storage_dir=self.temp_dir)
        self.rollup_engine = NightlyRollupEngine(storage_dir=self.temp_dir)
        # Connect the usage logger to the rollup engine for testing
        self.rollup_engine.set_usage_logger(self.usage_logger)
        # Reset global human registry for clean test
        self.rollup_engine.global_humans = set()
    
    def teardown_method(self):
        """Clean up test environment."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_daily_rollup_processing(self):
        """Test processing daily events into rollup metrics."""
        # Create test events
        test_date = "2025-01-15"
        base_timestamp = datetime.strptime(test_date, '%Y-%m-%d').timestamp()
        
        # Simulate verification events
        events_data = [
            ("site_a", "did:test:user1"),
            ("site_a", "did:test:user2"),
            ("site_a", "did:test:user1"),  # Repeat user
            ("site_b", "did:test:user2"),  # Cross-site user
            ("site_b", "did:test:user3"),  # New user
        ]
        
        for site_id, user_did in events_data:
            self.usage_logger.log_verification_success(
                site_id, user_did, timestamp=base_timestamp
            )
        
        self.usage_logger.flush_all()
        
        # Run rollup for the test date
        result = self.rollup_engine.force_daily_rollup(test_date)
        
        assert result['success'] is True, f"Rollup failed: {result.get('error', 'Unknown error')}"
        
        # Check rollup metrics
        rollup_data = self.rollup_engine.get_daily_rollup(test_date)
        assert rollup_data is not None, "No rollup data found"
        
        metrics = rollup_data['metrics']
        
        # Global summary checks
        global_summary = metrics['global_summary']
        assert global_summary['total_verifications'] == 5, f"Expected 5 verifications, got {global_summary['total_verifications']}"
        assert global_summary['global_unique_humans'] == 3, f"Expected 3 unique humans, got {global_summary['global_unique_humans']}"  # user1, user2, user3
        assert global_summary['active_sites'] == 2, f"Expected 2 active sites, got {global_summary['active_sites']}"
        
        # Site-specific checks
        site_metrics = metrics['site_metrics']
        assert 'site_a' in site_metrics, f"site_a not found in site_metrics: {list(site_metrics.keys())}"
        assert 'site_b' in site_metrics, f"site_b not found in site_metrics: {list(site_metrics.keys())}"
        
        site_a_metrics = site_metrics['site_a']
        assert site_a_metrics['total_verifications'] == 3, f"site_a: Expected 3 verifications, got {site_a_metrics['total_verifications']}"
        assert site_a_metrics['monthly_active_humans'] == 2, f"site_a: Expected 2 MAH, got {site_a_metrics['monthly_active_humans']}"  # user1, user2
        
        site_b_metrics = site_metrics['site_b']
        assert site_b_metrics['total_verifications'] == 2, f"site_b: Expected 2 verifications, got {site_b_metrics['total_verifications']}"
        assert site_b_metrics['monthly_active_humans'] == 2, f"site_b: Expected 2 MAH, got {site_b_metrics['monthly_active_humans']}"  # user2, user3
    
    def test_new_human_detection(self):
        """Test detection of new humans globally."""
        # First day - all users are new
        day1_date = "2025-01-10"
        day1_timestamp = datetime.strptime(day1_date, '%Y-%m-%d').timestamp()
        
        self.usage_logger.log_verification_success("site_a", "did:test:user1", timestamp=day1_timestamp)
        self.usage_logger.log_verification_success("site_a", "did:test:user2", timestamp=day1_timestamp)
        self.usage_logger.flush_all()
        
        # Process first day
        result1 = self.rollup_engine.force_daily_rollup(day1_date)
        assert result1['success'] is True
        
        rollup1 = self.rollup_engine.get_daily_rollup(day1_date)
        site_metrics1 = rollup1['metrics']['site_metrics']['site_a']
        assert site_metrics1['new_humans'] == 2  # Both users are new
        
        # Second day - one returning user, one new user
        day2_date = "2025-01-11"
        day2_timestamp = datetime.strptime(day2_date, '%Y-%m-%d').timestamp()
        
        self.usage_logger.log_verification_success("site_a", "did:test:user1", timestamp=day2_timestamp)  # Returning
        self.usage_logger.log_verification_success("site_a", "did:test:user3", timestamp=day2_timestamp)  # New
        self.usage_logger.flush_all()
        
        # Process second day
        result2 = self.rollup_engine.force_daily_rollup(day2_date)
        assert result2['success'] is True
        
        rollup2 = self.rollup_engine.get_daily_rollup(day2_date)
        site_metrics2 = rollup2['metrics']['site_metrics']['site_a']
        assert site_metrics2['new_humans'] == 1  # Only user3 is new
        assert site_metrics2['monthly_active_humans'] == 2  # user1 and user3 active
    
    def test_monthly_aggregation(self):
        """Test monthly rollup aggregation."""
        # Process multiple days in January 2025
        dates = ["2025-01-10", "2025-01-11", "2025-01-12"]
        
        for i, date in enumerate(dates):
            timestamp = datetime.strptime(date, '%Y-%m-%d').timestamp()
            
            # Different usage patterns each day
            for j in range(i + 1):  # Increasing usage
                self.usage_logger.log_verification_success(
                    "site_test", f"did:test:user{j}", timestamp=timestamp
                )
            
            self.usage_logger.flush_all()
            result = self.rollup_engine.force_daily_rollup(date)
            assert result['success'] is True
        
        # Check monthly aggregation
        monthly_data = self.rollup_engine.get_monthly_rollup("2025-01")
        assert monthly_data is not None
        
        monthly_summary = monthly_data['monthly_summary']
        assert monthly_summary['days_processed'] == 3
        assert monthly_summary['total_verifications'] == 6  # 1 + 2 + 3
        assert len(monthly_summary['monthly_active_humans']) == 3  # user0, user1, user2

class TestBillingEngine:
    """Test the billing calculation engine."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.usage_logger = UsageEventLogger(storage_dir=self.temp_dir)
        self.rollup_engine = NightlyRollupEngine(storage_dir=self.temp_dir)
        self.billing_engine = BillingEngine(storage_dir=self.temp_dir)
        # Connect the usage logger to the rollup engine for testing
        self.rollup_engine.set_usage_logger(self.usage_logger)
        # Connect the rollup engine to the billing engine for testing
        self.billing_engine.set_rollup_engine(self.rollup_engine)
        # Reset global human registry for clean test
        self.rollup_engine.global_humans = set()
    
    def teardown_method(self):
        """Clean up test environment."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_monthly_bill_calculation(self):
        """Test monthly billing calculation."""
        # Set up test data for January 2025
        month = "2025-01"
        site_id = "test_customer_site"
        
        # Create events and process them
        test_dates = ["2025-01-15", "2025-01-16", "2025-01-17"]
        
        for i, date in enumerate(test_dates):
            timestamp = datetime.strptime(date, '%Y-%m-%d').timestamp()
            
            # Day 1: 3 users (all new)
            # Day 2: 2 users (1 returning, 1 new) 
            # Day 3: 4 users (2 returning, 2 new)
            
            if i == 0:  # Day 1
                users = ["user1", "user2", "user3"]
            elif i == 1:  # Day 2
                users = ["user1", "user4"]  # user1 returning, user4 new
            else:  # Day 3
                users = ["user2", "user3", "user5", "user6"]  # 2 returning, 2 new
            
            for user in users:
                self.usage_logger.log_verification_success(
                    site_id, f"did:test:{user}", timestamp=timestamp
                )
            
            self.usage_logger.flush_all()
            result = self.rollup_engine.force_daily_rollup(date)
            assert result['success'] is True
        
        # Calculate monthly bill
        billing_data = self.billing_engine.calculate_monthly_bill(site_id, month)
        
        assert billing_data['success'] is True
        assert billing_data['site_id'] == site_id
        assert billing_data['month'] == month
        
        # Check usage metrics
        usage = billing_data['usage']
        assert usage['monthly_active_humans'] == 6  # user1, user2, user3, user4, user5, user6
        assert usage['new_humans'] == 6  # All users are new globally
        assert usage['total_verifications'] == 9  # 3 + 2 + 4
        
        # Check billing calculation (default rates: $0.10 MAH, $2.00 new humans)
        charges = billing_data['charges']
        expected_mah_charge = Decimal("6") * Decimal("0.10")  # 6 MAH × $0.10
        expected_new_charge = Decimal("6") * Decimal("2.00")  # 6 new × $2.00
        expected_total = expected_mah_charge + expected_new_charge  # $0.60 + $12.00 = $12.60
        
        assert Decimal(charges['mah_charge']) == expected_mah_charge
        assert Decimal(charges['new_humans_charge']) == expected_new_charge
        assert Decimal(charges['total_amount']) == expected_total
    
    def test_custom_contract_pricing(self):
        """Test billing with custom contract rates."""
        site_id = "enterprise_customer"
        
        # Create custom contract with different rates
        contract_terms = {
            "mah_rate": "0.08",      # $0.08 per MAH (enterprise discount)
            "new_human_rate": "1.50", # $1.50 per new human
            "currency": "USD",
            "volume_discounts": [
                {"min_usage": 10, "discount_percent": 5.0},   # 5% discount for 10+ users
                {"min_usage": 50, "discount_percent": 10.0}   # 10% discount for 50+ users
            ]
        }
        
        success = self.billing_engine.create_contract(site_id, contract_terms)
        assert success is True
        
        # Set up test data
        month = "2025-01"
        date = "2025-01-20"
        timestamp = datetime.strptime(date, '%Y-%m-%d').timestamp()
        
        # Create 15 users to trigger volume discount
        for i in range(15):
            self.usage_logger.log_verification_success(
                site_id, f"did:test:user{i}", timestamp=timestamp
            )
        
        self.usage_logger.flush_all()
        result = self.rollup_engine.force_daily_rollup(date)
        assert result['success'] is True
        
        # Calculate bill with custom rates
        billing_data = self.billing_engine.calculate_monthly_bill(site_id, month)
        
        assert billing_data['success'] is True
        
        # Check custom rates are applied
        assert billing_data['rates']['mah_rate'] == "0.08"
        assert billing_data['rates']['new_human_rate'] == "1.50"
        
        # Check usage
        usage = billing_data['usage']
        assert usage['monthly_active_humans'] == 15
        assert usage['new_humans'] == 15
        
        # Check billing with volume discount
        charges = billing_data['charges']
        base_mah = Decimal("15") * Decimal("0.08")     # $1.20
        base_new = Decimal("15") * Decimal("1.50")     # $22.50
        subtotal = base_mah + base_new                 # $23.70
        
        # 5% discount applies (15 users >= 10)
        discount_amount = subtotal * Decimal("0.05")   # $1.185
        expected_total = subtotal - discount_amount    # $22.515 → $22.52
        
        assert Decimal(charges['subtotal']) == subtotal
        assert charges['discount_percent'] == 5.0
        assert abs(Decimal(charges['total_amount']) - expected_total) < Decimal("0.01")
    
    def test_invoice_generation(self):
        """Test PDF and CSV invoice generation."""
        # Set up minimal billing data
        site_id = "invoice_test_site"
        month = "2025-01"
        date = "2025-01-25"
        timestamp = datetime.strptime(date, '%Y-%m-%d').timestamp()
        
        # Create some test usage
        for i in range(3):
            self.usage_logger.log_verification_success(
                site_id, f"did:test:invoice_user{i}", timestamp=timestamp
            )
        
        self.usage_logger.flush_all()
        self.rollup_engine.force_daily_rollup(date)
        
        # Generate billing data
        billing_data = self.billing_engine.calculate_monthly_bill(site_id, month)
        assert billing_data['success'] is True
        
        # Test PDF generation
        pdf_bytes = self.billing_engine.generate_invoice_pdf(billing_data)
        assert len(pdf_bytes) > 1000  # PDF should be substantial
        assert pdf_bytes.startswith(b'%PDF')  # PDF header
        
        # Test CSV generation
        csv_content = self.billing_engine.generate_invoice_csv(billing_data)
        assert len(csv_content) > 100
        assert "Lemma Verification Invoice" in csv_content
        assert billing_data['site_id'] in csv_content
        assert billing_data['charges']['total_amount'] in csv_content
        
        # Test saving invoices
        saved_files = self.billing_engine.save_invoice(billing_data, ["pdf", "csv", "json"])
        
        assert "pdf" in saved_files
        assert "csv" in saved_files
        assert "json" in saved_files
        
        # Check files exist and have content
        for file_path in saved_files.values():
            assert os.path.exists(file_path)
            assert os.path.getsize(file_path) > 0

def test_end_to_end_billing_pipeline():
    """Test the complete billing pipeline end-to-end."""
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Initialize all components
        usage_logger = UsageEventLogger(storage_dir=temp_dir)
        rollup_engine = NightlyRollupEngine(storage_dir=temp_dir)
        billing_engine = BillingEngine(storage_dir=temp_dir)
        # Connect the usage logger to the rollup engine for testing
        rollup_engine.set_usage_logger(usage_logger)
        # Connect the rollup engine to the billing engine for testing
        billing_engine.set_rollup_engine(rollup_engine)
        # Reset global human registry for clean test
        rollup_engine.global_humans = set()
        
        # Simulate real-world usage over several days
        sites = ["ecommerce_site", "social_platform", "enterprise_app"]
        users = [f"did:lemma:user{i:04d}" for i in range(50)]
        
        # Day 1: Initial users
        day1 = "2025-01-10"
        day1_ts = datetime.strptime(day1, '%Y-%m-%d').timestamp()
        
        for i, site in enumerate(sites):
            for j in range(5 + i * 3):  # Different usage per site
                user = users[j % len(users)]
                usage_logger.log_verification_success(site, user, timestamp=day1_ts)
        
        usage_logger.flush_all()
        result1 = rollup_engine.force_daily_rollup(day1)
        assert result1['success'] is True
        
        # Day 2: Mix of returning and new users
        day2 = "2025-01-11"
        day2_ts = datetime.strptime(day2, '%Y-%m-%d').timestamp()
        
        for i, site in enumerate(sites):
            # Some returning users
            for j in range(3):
                user = users[j]
                usage_logger.log_verification_success(site, user, timestamp=day2_ts)
            
            # Some new users
            for j in range(15, 18 + i):
                user = users[j % len(users)]
                usage_logger.log_verification_success(site, user, timestamp=day2_ts)
        
        usage_logger.flush_all()
        result2 = rollup_engine.force_daily_rollup(day2)
        assert result2['success'] is True
        
        # Generate bills for each site
        month = "2025-01"
        all_bills = []
        
        for site in sites:
            billing_data = billing_engine.calculate_monthly_bill(site, month)
            assert billing_data['success'] is True
            
            # Validate billing data structure
            assert 'usage' in billing_data
            assert 'charges' in billing_data
            assert 'rates' in billing_data
            assert billing_data['currency'] == 'USD'
            
            # Save invoice files
            saved_files = billing_engine.save_invoice(billing_data, ["pdf", "csv"])
            assert len(saved_files) == 2
            
            all_bills.append(billing_data)
        
        # Verify different sites have different usage
        site_totals = [bill['charges']['total_amount'] for bill in all_bills]
        assert len(set(site_totals)) > 1  # Sites should have different totals
        
        # Verify monthly aggregation
        monthly_data = rollup_engine.get_monthly_rollup(month)
        assert monthly_data is not None
        assert monthly_data['monthly_summary']['days_processed'] == 2
        
        print("✅ End-to-end billing pipeline test completed successfully!")
        print(f"📊 Processed {len(sites)} sites over 2 days")
        print(f"💰 Generated {len(all_bills)} invoices")
        
        for i, bill in enumerate(all_bills):
            usage = bill['usage']
            charges = bill['charges']
            print(f"   {sites[i]}: {usage['monthly_active_humans']} MAH, "
                  f"{usage['new_humans']} new, ${charges['total_amount']}")
        
    finally:
        # Clean up
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    # Run individual test classes
    print("🚀 Testing Lemma Billing System Components...")
    
    # Test usage logger
    print("\n📝 Testing Usage Event Logger...")
    test_logger = TestUsageEventLogger()
    test_logger.setup_method()
    test_logger.test_log_verification_success()
    test_logger.test_multiple_sites_same_user()
    test_logger.test_usage_stats()
    test_logger.teardown_method()
    print("✅ Usage logger tests passed!")
    
    # Test rollup engine
    print("\n📊 Testing Nightly Rollup Engine...")
    test_rollup = TestNightlyRollupEngine()
    test_rollup.setup_method()
    test_rollup.test_daily_rollup_processing()
    test_rollup.test_new_human_detection()
    test_rollup.test_monthly_aggregation()
    test_rollup.teardown_method()
    print("✅ Rollup engine tests passed!")
    
    # Test billing engine
    print("\n💰 Testing Billing Engine...")
    test_billing = TestBillingEngine()
    test_billing.setup_method()
    test_billing.test_monthly_bill_calculation()
    test_billing.test_custom_contract_pricing()
    test_billing.test_invoice_generation()
    test_billing.teardown_method()
    print("✅ Billing engine tests passed!")
    
    # Test end-to-end pipeline
    print("\n🔄 Testing End-to-End Pipeline...")
    test_end_to_end_billing_pipeline()
    
    print("\n🎉 ALL BILLING SYSTEM TESTS PASSED!")
    print("📈 Lemma Enterprise billing infrastructure is ready for production!") 