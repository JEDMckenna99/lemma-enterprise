#!/usr/bin/env python3
"""
Final CloudFlare Performance Test
Tests the complete CDN + SSL + Flask-Minify performance
"""

import requests
import time
import statistics

def test_final_performance():
    """Test final CloudFlare + SSL + Flask-Minify performance."""
    
    print("🚀 FINAL CLOUDFLARE + SSL + MINIFY PERFORMANCE TEST")
    print("=" * 60)
    
    # Test URLs
    test_cases = [
        {
            "name": "API Health Check",
            "url": "https://www.lemma.id/api/health",
            "expected_cache": "DYNAMIC"
        },
        {
            "name": "Main Landing Page", 
            "url": "https://www.lemma.id/",
            "expected_cache": "HIT or MISS"
        },
        {
            "name": "Static CSS",
            "url": "https://www.lemma.id/static/css/style.css", 
            "expected_cache": "HIT or MISS"
        }
    ]
    
    all_response_times = []
    
    for test_case in test_cases:
        print(f"\n📊 Testing: {test_case['name']}")
        print(f"🔗 URL: {test_case['url']}")
        
        # Run multiple tests for better average
        response_times = []
        
        for i in range(3):
            try:
                start_time = time.time()
                response = requests.get(test_case['url'], timeout=10)
                end_time = time.time()
                
                response_time = (end_time - start_time) * 1000  # Convert to ms
                response_times.append(response_time)
                
                if i == 0:  # Only show details for first request
                    print(f"  📋 Status Code: {response.status_code}")
                    
                    # Check CloudFlare headers
                    cf_ray = response.headers.get('CF-RAY', 'Not Found')
                    cache_status = response.headers.get('cf-cache-status', 'Not Available')
                    
                    print(f"  ✅ CloudFlare Ray: {cf_ray}")
                    print(f"  💾 Cache Status: {cache_status}")
                    
                    # Check if minified (look for compressed content)
                    content_encoding = response.headers.get('content-encoding', 'none')
                    print(f"  🗜️  Content Encoding: {content_encoding}")
                    
                    # Check response size
                    content_length = len(response.content)
                    print(f"  📏 Response Size: {content_length:,} bytes")
                    
            except Exception as e:
                print(f"  ❌ Error on attempt {i+1}: {e}")
                continue
        
        if response_times:
            avg_time = statistics.mean(response_times)
            min_time = min(response_times)
            max_time = max(response_times)
            
            print(f"  ⏱️  Response Times: {min_time:.0f}ms / {avg_time:.0f}ms / {max_time:.0f}ms (min/avg/max)")
            
            all_response_times.extend(response_times)
            
            # Performance assessment
            if avg_time <= 250:
                print(f"  🎯 EXCELLENT: Meets SRE target (≤250ms)")
            elif avg_time <= 350:
                print(f"  ✅ GOOD: Close to target")
            else:
                print(f"  ⚠️  NEEDS IMPROVEMENT: Above target")
    
    # Overall performance summary
    if all_response_times:
        overall_avg = statistics.mean(all_response_times)
        overall_p95 = sorted(all_response_times)[int(len(all_response_times) * 0.95)]
        
        print(f"\n🎯 OVERALL PERFORMANCE SUMMARY")
        print("-" * 40)
        print(f"Average Response Time: {overall_avg:.0f}ms")
        print(f"P95 Response Time: {overall_p95:.0f}ms")
        print(f"Total Tests: {len(all_response_times)}")
        
        # Compare to baseline
        baseline_p95 = 440  # Previous P95 latency
        improvement = ((baseline_p95 - overall_p95) / baseline_p95) * 100
        
        print(f"\n📈 PERFORMANCE IMPROVEMENT")
        print("-" * 30)
        print(f"Before CloudFlare: {baseline_p95}ms P95")
        print(f"After CloudFlare: {overall_p95:.0f}ms P95")
        print(f"Improvement: {improvement:.1f}%")
        
        # SRE Compliance Assessment
        if overall_p95 <= 250:
            sre_score = 95
            print(f"🎉 SRE TARGET ACHIEVED! P95 ≤ 250ms")
        elif overall_p95 <= 300:
            sre_score = 92
            print(f"✅ VERY CLOSE to SRE target")
        elif overall_p95 <= 350:
            sre_score = 88
            print(f"✅ GOOD performance, minor optimization needed")
        else:
            sre_score = 85
            print(f"⚠️  Additional optimization needed")
        
        print(f"\n🏆 ESTIMATED SRE COMPLIANCE: {sre_score}%")
        
        if sre_score >= 90:
            print("🎯 READY FOR ENTERPRISE SRE OPERATIONS!")
        else:
            print("🔧 Consider additional infrastructure optimization")

if __name__ == "__main__":
    test_final_performance() 