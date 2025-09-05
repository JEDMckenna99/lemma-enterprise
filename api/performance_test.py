"""
Performance Testing API - Test and Compare Shield Performance
============================================================
This module provides endpoints to test and benchmark the shield performance
"""

from flask import Blueprint, request, jsonify
import time
import json
from .optimized_shield import get_optimized_engine
from typing import Dict, List, Any

# Create blueprint
performance_bp = Blueprint('performance', __name__, url_prefix='/api/performance')

@performance_bp.route('/test-verification', methods=['POST'])
def test_verification():
    """Test verification performance with sample credentials"""
    data = request.get_json() or {}
    iterations = min(data.get('iterations', 100), 1000)  # Cap at 1000 for safety
    
    engine = get_optimized_engine()
    
    # Sample credentials for testing
    test_credentials = [
        {
            'id': f'test_credential_{i}',
            'issuer': 'did:lemma:federated:issuer',
            'subject': f'did:lemma:user:test_{i}',
            'claims': {
                'isHuman': True,
                'verificationMethod': 'stripe_identity',
                'verifiedAt': int(time.time())
            }
        }
        for i in range(min(iterations, 10))  # Max 10 unique credentials
    ]
    
    # Run performance test
    start_time = time.time_ns()
    results = []
    
    for i in range(iterations):
        credential = test_credentials[i % len(test_credentials)]
        result = engine.verify_credential_optimized(credential)
        results.append(result)
    
    total_time_ns = time.time_ns() - start_time
    
    # Calculate statistics
    verification_times = [r['verification_time_ns'] for r in results]
    rust_verifications = [r for r in results if r['method'] == 'rust_engine']
    python_verifications = [r for r in results if r['method'] == 'python_optimized']
    cache_hits = [r for r in results if r.get('cache_hit', False)]
    
    return jsonify({
        'test_summary': {
            'iterations': iterations,
            'total_time_ns': total_time_ns,
            'total_time_ms': total_time_ns / 1_000_000,
            'avg_time_per_verification_ns': total_time_ns // iterations,
            'avg_time_per_verification_us': (total_time_ns // iterations) / 1000,
            'throughput_per_second': iterations / (total_time_ns / 1_000_000_000)
        },
        'method_breakdown': {
            'rust_verifications': len(rust_verifications),
            'python_verifications': len(python_verifications),
            'cache_hits': len(cache_hits),
            'cache_hit_rate': len(cache_hits) / iterations * 100
        },
        'performance_stats': {
            'min_verification_ns': min(verification_times),
            'max_verification_ns': max(verification_times),
            'avg_verification_ns': sum(verification_times) / len(verification_times),
            'min_verification_us': min(verification_times) / 1000,
            'max_verification_us': max(verification_times) / 1000,
            'avg_verification_us': sum(verification_times) / len(verification_times) / 1000
        },
        'engine_report': engine.get_performance_report(),
        'sample_results': results[:5]  # First 5 results for debugging
    })

@performance_bp.route('/benchmark', methods=['GET'])
def benchmark():
    """Run comprehensive performance benchmark"""
    engine = get_optimized_engine()
    
    # Test different scenarios
    scenarios = [
        ('valid_credential', {
            'id': 'benchmark_valid',
            'issuer': 'did:lemma:federated:issuer',
            'subject': 'did:lemma:user:benchmark',
            'claims': {'isHuman': True, 'verificationMethod': 'stripe_identity'}
        }),
        ('invalid_credential', {
            'id': 'benchmark_invalid',
            'issuer': 'unknown_issuer',
        }),
        ('minimal_credential', {
            'id': 'benchmark_minimal',
            'issuer': 'lemma-hybrid-shield',
            'subject': 'test',
            'claims': {'isHuman': True}
        })
    ]
    
    benchmark_results = {}
    
    for scenario_name, credential in scenarios:
        # Run each scenario multiple times
        times = []
        for _ in range(50):  # 50 iterations per scenario
            start = time.time_ns()
            result = engine.verify_credential_optimized(credential)
            end = time.time_ns()
            times.append(end - start)
        
        benchmark_results[scenario_name] = {
            'min_ns': min(times),
            'max_ns': max(times),
            'avg_ns': sum(times) / len(times),
            'min_us': min(times) / 1000,
            'max_us': max(times) / 1000,
            'avg_us': sum(times) / len(times) / 1000,
            'p50_us': sorted(times)[len(times)//2] / 1000,
            'p95_us': sorted(times)[int(len(times)*0.95)] / 1000,
            'p99_us': sorted(times)[int(len(times)*0.99)] / 1000
        }
    
    return jsonify({
        'benchmark_results': benchmark_results,
        'overall_performance': engine.get_performance_report(),
        'performance_targets': {
            'rust_engine_target_us': '0.05-1.0',
            'python_optimized_target_us': '<1000',
            'current_status': 'rust_available' if engine.rust_engine else 'python_fallback'
        }
    })

@performance_bp.route('/status', methods=['GET'])  
def performance_status():
    """Get current performance status and metrics"""
    engine = get_optimized_engine()
    
    return jsonify({
        'status': 'operational',
        'engine_report': engine.get_performance_report(),
        'rust_engine_available': engine.rust_engine is not None,
        'optimization_level': 'high' if engine.rust_engine else 'medium',
        'ready_for_production': True
    }) 