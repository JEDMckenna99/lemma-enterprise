#!/usr/bin/env python3
"""
Quick Test: Prometheus Metrics Fix Validation
Tests the fixed Prometheus metrics export to ensure all 5 metrics are working
"""

import requests
import time
import json

def test_prometheus_metrics_fix():
    """Test that all 5 Prometheus metrics are now properly exported."""
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🔧 TESTING PROMETHEUS METRICS FIX")
    print("=" * 50)
    
    # Step 1: Generate some traffic to create metrics data
    print("📊 Step 1: Generating sample traffic...")
    
    # Generate successful requests
    for i in range(5):
        try:
            requests.get(f"{base_url}/api/health", timeout=5)
            requests.get(f"{base_url}/api/ping", timeout=5)
        except:
            pass  # Ignore errors, we just want to generate traffic
    
    # Generate an error to create error metrics
    try:
        requests.get(f"{base_url}/api/nonexistent-endpoint", timeout=5)
    except:
        pass
    
    time.sleep(2)  # Allow metrics to be recorded
    
    # Step 2: Test Prometheus endpoint
    print("🔍 Step 2: Testing Prometheus metrics export...")
    
    try:
        response = requests.get(f"{base_url}/api/sre/metrics/prometheus", timeout=10)
        
        if response.status_code == 200:
            metrics_text = response.text
            print(f"✅ Prometheus endpoint responding (200)")
            print(f"📊 Metrics size: {len(metrics_text)} bytes")
            
            # Check for all 5 expected metrics
            expected_metrics = [
                'lemma_latency_ms',
                'lemma_error_rate', 
                'lemma_mah_total',
                'lemma_bloom_filter_size',
                'lemma_revocation_lag_seconds'
            ]
            
            metrics_found = {}
            for metric in expected_metrics:
                if metric in metrics_text:
                    metrics_found[metric] = True
                    # Count how many instances of this metric we have
                    count = metrics_text.count(metric + '{')
                    if count == 0:
                        count = metrics_text.count(metric + ' ')
                    print(f"  ✅ {metric} - Found ({count} instances)")
                else:
                    metrics_found[metric] = False
                    print(f"  ❌ {metric} - Missing")
            
            # Print the actual metrics for debugging
            print(f"\n📋 Raw Prometheus Output:")
            print("-" * 40)
            print(metrics_text)
            print("-" * 40)
            
            # Calculate score
            found_count = sum(metrics_found.values())
            percentage = (found_count / len(expected_metrics)) * 100
            
            print(f"\n🎯 PROMETHEUS METRICS SCORE: {found_count}/{len(expected_metrics)} ({percentage:.1f}%)")
            
            if percentage == 100:
                print("🎉 SUCCESS! All 5 Prometheus metrics are now working!")
                print("📈 This brings SRE compliance from 83% to ~85%")
            elif percentage >= 80:
                print("✅ GOOD! Most metrics working, minor fixes needed")
            else:
                print("⚠️ Some metrics still missing, further investigation needed")
                
        else:
            print(f"❌ Prometheus endpoint error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing Prometheus endpoint: {e}")
    
    # Step 3: Test overall SRE health
    print(f"\n🔍 Step 3: Testing overall SRE health...")
    
    try:
        # Test SRE dashboard to see overall health
        sre_response = requests.get(f"{base_url}/api/sre/dashboard/metrics", 
                                  headers={"X-API-Key": "63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e"},
                                  timeout=10)
        
        if sre_response.status_code == 200:
            sre_data = sre_response.json()
            print("✅ SRE Dashboard responding")
            
            if 'dashboard' in sre_data:
                dashboard = sre_data['dashboard']
                components = len([k for k in dashboard.keys() if k != 'timestamp'])
                print(f"📊 Dashboard components: {components}")
                
                # Check if latency metrics exist
                if 'latency_metrics' in dashboard:
                    latency_data = dashboard['latency_metrics']
                    if 'latency_stats' in latency_data:
                        endpoints = len(latency_data['latency_stats'])
                        print(f"📈 Endpoints with latency data: {endpoints}")
        else:
            print(f"⚠️ SRE Dashboard error: {sre_response.status_code}")
            
    except Exception as e:
        print(f"⚠️ Error testing SRE dashboard: {e}")

if __name__ == "__main__":
    test_prometheus_metrics_fix() 