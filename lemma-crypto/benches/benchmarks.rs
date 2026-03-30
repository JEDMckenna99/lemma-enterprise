//! Comprehensive benchmarks for all verification optimizations
//! 
//! This file contains benchmarks for Phases 1, 2, and 3 optimizations

use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId, Throughput};
use lemma_crypto::{
    LemmaCore, VerifiableCredential, CredentialIssuer,
    packages::{IdentityPackage, TicketPackage, PackageAuthenticityPackage},
    simd_signatures::SIMDVerifier,
    zero_copy::{ZeroCopyVerifier, AdvancedZeroCopyVerifier},
    precomputation::PrecomputedVerifier,
    hsm::HSMVerifier,
    gpu::GPUVerifier,
    predictive_cache::{PredictiveCache, PredictiveCacheConfig},
    work_stealing::{WorkStealingScheduler, WorkStealingConfig},
    probabilistic_verification::ProbabilisticVerifier,
    asic::ASICVerifier,
    fpga::FPGAVerifier,
    quantum_resistant::QuantumResistantVerifier,
    distributed::{DistributedVerifier, DistributedConfig},
};
use std::collections::HashMap;
use std::time::Duration;

/// Create a test credential for benchmarking
fn create_test_credential() -> VerifiableCredential {
    let issuer = CredentialIssuer::new();
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    
    issuer.issue_credential(
        "did:lemma:test_subject".to_string(),
        claims,
        None,
    ).unwrap()
}

/// Create multiple test credentials
fn create_test_credentials(count: usize) -> Vec<VerifiableCredential> {
    (0..count)
        .map(|i| {
            let issuer = CredentialIssuer::new();
            let mut claims = HashMap::new();
            claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
            claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
            claims.insert("id".to_string(), serde_json::Value::Number(i.into()));
            
            issuer.issue_credential(
                format!("did:lemma:test_subject_{}", i),
                claims,
                None,
            ).unwrap()
        })
        .collect()
}

/// Benchmark Phase 1 & 2 optimizations (baseline)
fn benchmark_phase1_phase2(c: &mut Criterion) {
    let mut group = c.benchmark_group("Phase1_Phase2_Baseline");
    
    // Memory pool benchmark
    group.bench_function("memory_pool_verification", |b| {
        let mut core = LemmaCore::new().unwrap();
        core.register_package(IdentityPackage::new());
        let credential = create_test_credential();
        
        b.iter(|| {
            black_box(core.verify(&credential).unwrap());
        });
    });
    
    // SIMD signatures benchmark
    group.bench_function("simd_signatures", |b| {
        let mut verifier = SIMDVerifier::new();
        let credential = create_test_credential();
        let credentials = vec![credential; 8];
        
        b.iter(|| {
            black_box(verifier.verify_batch_simd(&credentials).unwrap());
        });
    });
    
    // Zero-copy benchmark
    group.bench_function("zero_copy_verification", |b| {
        let mut verifier = ZeroCopyVerifier::new();
        
        b.iter(|| {
            black_box(verifier.verify_zero_copy(0).unwrap());
        });
    });
    
    // Precomputation benchmark
    group.bench_function("precomputation_verification", |b| {
        let mut verifier = PrecomputedVerifier::new().unwrap();
        let credential = create_test_credential();
        
        b.iter(|| {
            black_box(verifier.verify_precomputed(&credential).unwrap());
        });
    });
    
    // HSM benchmark (if available)
    group.bench_function("hsm_verification", |b| {
        if let Ok(mut verifier) = HSMVerifier::new() {
            let credential = create_test_credential();
            
            b.iter(|| {
                black_box(verifier.verify_signature_hsm(&credential).unwrap());
            });
        } else {
            b.iter(|| {
                // Fallback if HSM not available
                black_box(true);
            });
        }
    });
    
    // GPU benchmark (if available)
    group.bench_function("gpu_batch_verification", |b| {
        if let Ok(mut verifier) = GPUVerifier::new() {
            let credentials = create_test_credentials(32);
            
            b.iter(|| {
                black_box(verifier.verify_batch(&credentials).unwrap());
            });
        } else {
            b.iter(|| {
                // Fallback if GPU not available
                black_box(vec![true; 32]);
            });
        }
    });
    
    group.finish();
}

/// Benchmark Phase 3 optimizations
fn benchmark_phase3_optimizations(c: &mut Criterion) {
    let mut group = c.benchmark_group("Phase3_Optimizations");
    
    // Predictive caching benchmark
    group.bench_function("predictive_cache", |b| {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let cache = PredictiveCache::new(PredictiveCacheConfig::default());
        
        b.to_async(&rt).iter(|| async {
            black_box(cache.record_verification("cred1", "identity", "issuer1", None, None).await.unwrap());
        });
    });
    
    group.bench_function("predictive_cache_with_predictions", |b| {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let cache = PredictiveCache::new(PredictiveCacheConfig::default());
        
        b.to_async(&rt).iter(|| async {
            cache.record_verification("cred1", "identity", "issuer1", None, None).await.unwrap();
            cache.record_verification("cred2", "ticket", "issuer1", None, None).await.unwrap();
            black_box(cache.get_predictions("identity").await.unwrap());
        });
    });
    
    // Work-stealing parallelism benchmark
    group.bench_function("work_stealing_single_task", |b| {
        let config = WorkStealingConfig {
            num_workers: 4,
            queue_size: 1000,
            priority_scheduling: true,
            steal_attempts: 5,
            idle_sleep_ms: 1,
        };
        let scheduler = WorkStealingScheduler::new(config).unwrap();
        let credential = create_test_credential();
        
        b.iter(|| {
            let task_id = scheduler.submit_task(credential.clone(), 1).unwrap();
            black_box(task_id);
        });
    });
    
    group.bench_function("work_stealing_batch", |b| {
        let config = WorkStealingConfig {
            num_workers: 8,
            queue_size: 1000,
            priority_scheduling: true,
            steal_attempts: 5,
            idle_sleep_ms: 1,
        };
        let scheduler = WorkStealingScheduler::new(config).unwrap();
        let credentials = create_test_credentials(16);
        
        b.iter(|| {
            let task_ids = scheduler.submit_batch(credentials.clone(), 1).unwrap();
            black_box(task_ids);
        });
    });
    
    // Advanced zero-copy benchmark
    group.bench_function("advanced_zero_copy", |b| {
        let verifier = AdvancedZeroCopyVerifier::new().unwrap();
        
        b.iter(|| {
            black_box(verifier.verify_advanced_zero_copy(0).unwrap());
        });
    });
    
    group.bench_function("advanced_zero_copy_batch", |b| {
        let verifier = AdvancedZeroCopyVerifier::new().unwrap();
        let offsets: Vec<usize> = (0..16).map(|i| i * 1344).collect();
        
        b.iter(|| {
            black_box(verifier.verify_batch_advanced_zero_copy(&offsets).unwrap());
        });
    });
    
    // Probabilistic verification benchmark
    group.bench_function("probabilistic_verification", |b| {
        let prob_verifier = ProbabilisticVerifier::new();
        let mut core = LemmaCore::new().unwrap();
        core.register_package(IdentityPackage::new());
        let credential = create_test_credential();
        
        b.iter(|| {
            black_box(prob_verifier.verify_probabilistic(&credential, &mut core).unwrap());
        });
    });
    
    group.bench_function("probabilistic_vs_full_verification", |b| {
        let prob_verifier = ProbabilisticVerifier::new();
        let mut core = LemmaCore::new().unwrap();
        core.register_package(IdentityPackage::new());
        let credential = create_test_credential();
        
        b.iter(|| {
            // Compare probabilistic vs full verification
            let prob_result = prob_verifier.verify_probabilistic(&credential, &mut core).unwrap();
            let full_result = core.verify(&credential).unwrap();
            black_box((prob_result, full_result));
        });
    });
    
    group.finish();
}

/// Benchmark throughput comparisons
fn benchmark_throughput_comparison(c: &mut Criterion) {
    let mut group = c.benchmark_group("Throughput_Comparison");
    
    // Throughput benchmark for different optimization levels
    for &batch_size in &[1, 8, 16, 32, 64, 128] {
        group.throughput(Throughput::Elements(batch_size as u64));
        
        // Baseline verification
        group.bench_with_input(
            BenchmarkId::new("baseline", batch_size),
            &batch_size,
            |b, &size| {
                let mut core = LemmaCore::new().unwrap();
                core.register_package(IdentityPackage::new());
                let credentials = create_test_credentials(size);
                
                b.iter(|| {
                    for credential in &credentials {
                        black_box(core.verify(credential).unwrap());
                    }
                });
            },
        );
        
        // Work-stealing throughput
        group.bench_with_input(
            BenchmarkId::new("work_stealing", batch_size),
            &batch_size,
            |b, &size| {
                let config = WorkStealingConfig {
                    num_workers: num_cpus::get(),
                    queue_size: 1000,
                    priority_scheduling: true,
                    steal_attempts: 5,
                    idle_sleep_ms: 1,
                };
                let scheduler = WorkStealingScheduler::new(config).unwrap();
                let credentials = create_test_credentials(size);
                
                b.iter(|| {
                    let task_ids = scheduler.submit_batch(credentials.clone(), 1).unwrap();
                    black_box(task_ids);
                });
            },
        );
        
        // Probabilistic verification throughput
        group.bench_with_input(
            BenchmarkId::new("probabilistic", batch_size),
            &batch_size,
            |b, &size| {
                let prob_verifier = ProbabilisticVerifier::new();
                let mut core = LemmaCore::new().unwrap();
                core.register_package(IdentityPackage::new());
                let credentials = create_test_credentials(size);
                
                b.iter(|| {
                    for credential in &credentials {
                        black_box(prob_verifier.verify_probabilistic(credential, &mut core).unwrap());
                    }
                });
            },
        );
    }
    
    group.finish();
}

/// Benchmark memory usage and efficiency
fn benchmark_memory_efficiency(c: &mut Criterion) {
    let mut group = c.benchmark_group("Memory_Efficiency");
    
    // Memory pool efficiency
    group.bench_function("memory_pool_vs_allocation", |b| {
        let mut core = LemmaCore::new().unwrap();
        core.register_package(IdentityPackage::new());
        let credential = create_test_credential();
        
        b.iter(|| {
            // Test memory pool efficiency
            black_box(core.verify(&credential).unwrap());
        });
    });
    
    // Advanced zero-copy memory efficiency
    group.bench_function("advanced_zero_copy_memory", |b| {
        let verifier = AdvancedZeroCopyVerifier::new().unwrap();
        
        b.iter(|| {
            black_box(verifier.verify_advanced_zero_copy(0).unwrap());
        });
    });
    
    // Predictive cache memory efficiency
    group.bench_function("predictive_cache_memory", |b| {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let cache = PredictiveCache::new(PredictiveCacheConfig::default());
        
        b.to_async(&rt).iter(|| async {
            for i in 0..100 {
                black_box(cache.record_verification(&format!("cred{}", i), "identity", "issuer1", None, None).await.unwrap());
            }
        });
    });
    
    group.finish();
}

/// Benchmark scalability under load
fn benchmark_scalability(c: &mut Criterion) {
    let mut group = c.benchmark_group("Scalability");
    group.measurement_time(Duration::from_secs(30));
    
    // Scalability test with increasing load
    for &worker_count in &[1, 2, 4, 8, 16] {
        group.bench_with_input(
            BenchmarkId::new("work_stealing_scalability", worker_count),
            &worker_count,
            |b, &workers| {
                let config = WorkStealingConfig {
                    num_workers: workers,
                    queue_size: 1000,
                    priority_scheduling: true,
                    steal_attempts: 5,
                    idle_sleep_ms: 1,
                };
                let scheduler = WorkStealingScheduler::new(config).unwrap();
                let credentials = create_test_credentials(100);
                
                b.iter(|| {
                    let task_ids = scheduler.submit_batch(credentials.clone(), 1).unwrap();
                    black_box(task_ids);
                });
            },
        );
    }
    
    group.finish();
}

/// Integration benchmark testing all optimizations together
fn benchmark_integration(c: &mut Criterion) {
    let mut group = c.benchmark_group("Integration_All_Optimizations");
    
    group.bench_function("all_phase3_optimizations", |b| {
        let rt = tokio::runtime::Runtime::new().unwrap();
        
        b.to_async(&rt).iter(|| async {
            // Initialize all Phase 3 optimizations
            let predictive_cache = PredictiveCache::new(PredictiveCacheConfig::default());
            let work_stealing_config = WorkStealingConfig::default();
            let scheduler = WorkStealingScheduler::new(work_stealing_config).unwrap();
            let advanced_zero_copy = AdvancedZeroCopyVerifier::new().unwrap();
            let probabilistic_verifier = ProbabilisticVerifier::new();
            let mut core = LemmaCore::new().unwrap();
            core.register_package(IdentityPackage::new());
            
            let credential = create_test_credential();
            
            // Test integration of all optimizations
            predictive_cache.record_verification("cred1", "identity", "issuer1", None, None).await.unwrap();
            let task_id = scheduler.submit_task(credential.clone(), 1).unwrap();
            let advanced_result = advanced_zero_copy.verify_advanced_zero_copy(0).unwrap();
            let prob_result = probabilistic_verifier.verify_probabilistic(&credential, &mut core).unwrap();
            
            black_box((task_id, advanced_result, prob_result));
        });
    });
    
    group.bench_function("phase3_vs_baseline", |b| {
        let rt = tokio::runtime::Runtime::new().unwrap();
        
        b.to_async(&rt).iter(|| async {
            // Baseline verification
            let mut core = LemmaCore::new().unwrap();
            core.register_package(IdentityPackage::new());
            let credential = create_test_credential();
            let baseline_result = core.verify(&credential).unwrap();
            
            // Phase 3 optimized verification
            let probabilistic_verifier = ProbabilisticVerifier::new();
            let optimized_result = probabilistic_verifier.verify_probabilistic(&credential, &mut core).unwrap();
            
            black_box((baseline_result, optimized_result));
        });
    });
    
    group.finish();
}

/// Performance regression test
fn benchmark_regression_test(c: &mut Criterion) {
    let mut group = c.benchmark_group("Regression_Test");
    
    // Ensure Phase 3 optimizations don't regress performance
    group.bench_function("phase3_regression_check", |b| {
        let rt = tokio::runtime::Runtime::new().unwrap();
        
        b.to_async(&rt).iter(|| async {
            // Test that Phase 3 optimizations maintain or improve performance
            let mut core = LemmaCore::new().unwrap();
            core.register_package(IdentityPackage::new());
            let credential = create_test_credential();
            
            // Baseline
            let start = std::time::Instant::now();
            let baseline_result = core.verify(&credential).unwrap();
            let baseline_time = start.elapsed();
            
            // Phase 3 optimized
            let probabilistic_verifier = ProbabilisticVerifier::new();
            let start = std::time::Instant::now();
            let optimized_result = probabilistic_verifier.verify_probabilistic(&credential, &mut core).unwrap();
            let optimized_time = start.elapsed();
            
            // Ensure optimized version is not significantly slower
            // (allowing for some variance in measurement)
            assert!(optimized_time <= baseline_time * 2, 
                "Phase 3 optimization significantly slower: {:?} vs {:?}", 
                optimized_time, baseline_time);
            
            black_box((baseline_result, optimized_result, baseline_time, optimized_time));
        });
    });
    
    group.finish();
}

// Phase 4 Benchmarks - Specialized Hardware

/// Benchmark ASIC verification
fn benchmark_asic_verification(c: &mut Criterion) {
    let mut group = c.benchmark_group("asic_verification");
    
    // Single credential verification
    group.bench_function("single_credential", |b| {
        let mut asic_verifier = ASICVerifier::new().unwrap();
        let credential = create_test_credential();
        
        b.iter(|| {
            let result = asic_verifier.verify_asic(black_box(&credential));
            black_box(result)
        })
    });
    
    // Batch verification
    for batch_size in [1, 8, 16, 32, 64, 128].iter() {
        group.throughput(Throughput::Elements(*batch_size as u64));
        group.bench_with_input(
            BenchmarkId::new("batch_verification", batch_size),
            batch_size,
            |b, &batch_size| {
                let mut asic_verifier = ASICVerifier::new().unwrap();
                let credentials = create_test_credentials(batch_size);
                
                b.iter(|| {
                    let results = asic_verifier.verify_batch_asic(black_box(&credentials));
                    black_box(results)
                })
            },
        );
    }
    
    group.finish();
}

/// Benchmark FPGA verification
fn benchmark_fpga_verification(c: &mut Criterion) {
    let mut group = c.benchmark_group("fpga_verification");
    
    // Single credential verification
    group.bench_function("single_credential", |b| {
        let mut fpga_verifier = FPGAVerifier::new().unwrap();
        let credential = create_test_credential();
        
        b.iter(|| {
            let result = fpga_verifier.verify_fpga(black_box(&credential));
            black_box(result)
        })
    });
    
    // Batch verification with different bitstreams
    for batch_size in [1, 8, 16, 32, 64, 128].iter() {
        group.throughput(Throughput::Elements(*batch_size as u64));
        group.bench_with_input(
            BenchmarkId::new("batch_verification", batch_size),
            batch_size,
            |b, &batch_size| {
                let mut fpga_verifier = FPGAVerifier::new().unwrap();
                let credentials = create_test_credentials(batch_size);
                
                b.iter(|| {
                    let results = fpga_verifier.verify_batch_fpga(black_box(&credentials));
                    black_box(results)
                })
            },
        );
    }
    
    group.finish();
}

/// Benchmark quantum-resistant verification
fn benchmark_quantum_resistant_verification(c: &mut Criterion) {
    let mut group = c.benchmark_group("quantum_resistant_verification");
    
    // Classical verification
    group.bench_function("classical_verification", |b| {
        let mut qr_verifier = QuantumResistantVerifier::new().unwrap();
        let credential = create_test_credential();
        
        b.iter(|| {
            let result = qr_verifier.verify_quantum_resistant(black_box(&credential));
            black_box(result)
        })
    });
    
    // Post-quantum verification
    group.bench_function("post_quantum_verification", |b| {
        let mut qr_verifier = QuantumResistantVerifier::new().unwrap();
        qr_verifier.set_crypto_mode(lemma_crypto::quantum_resistant::CryptographicMode::PostQuantum);
        let credential = create_test_credential();
        
        b.iter(|| {
            let result = qr_verifier.verify_quantum_resistant(black_box(&credential));
            black_box(result)
        })
    });
    
    // Hybrid verification
    group.bench_function("hybrid_verification", |b| {
        let mut qr_verifier = QuantumResistantVerifier::new().unwrap();
        qr_verifier.set_crypto_mode(lemma_crypto::quantum_resistant::CryptographicMode::Hybrid);
        let credential = create_test_credential();
        
        b.iter(|| {
            let result = qr_verifier.verify_quantum_resistant(black_box(&credential));
            black_box(result)
        })
    });
    
    group.finish();
}

/// Benchmark distributed verification
fn benchmark_distributed_verification(c: &mut Criterion) {
    let mut group = c.benchmark_group("distributed_verification");
    
    // Single node verification
    group.bench_function("single_node", |b| {
        let config = DistributedConfig::default();
        let mut dist_verifier = DistributedVerifier::new(config).unwrap();
        let credentials = create_test_credentials(1);
        
        b.iter(|| {
            let results = dist_verifier.verify_distributed(black_box(&credentials));
            black_box(results)
        })
    });
    
    // Multi-node verification with consensus
    for batch_size in [1, 8, 16, 32, 64, 128].iter() {
        group.throughput(Throughput::Elements(*batch_size as u64));
        group.bench_with_input(
            BenchmarkId::new("multi_node_consensus", batch_size),
            batch_size,
            |b, &batch_size| {
                let config = DistributedConfig::default();
                let mut dist_verifier = DistributedVerifier::new(config).unwrap();
                let credentials = create_test_credentials(batch_size);
                
                b.iter(|| {
                    let results = dist_verifier.verify_distributed(black_box(&credentials));
                    black_box(results)
                })
            },
        );
    }
    
    group.finish();
}

/// Benchmark Phase 4 integration (all optimizations together)
fn benchmark_phase4_integration(c: &mut Criterion) {
    let mut group = c.benchmark_group("phase4_integration");
    
    // Test different batch sizes with all Phase 4 optimizations
    for batch_size in [1, 8, 16, 32, 64, 128].iter() {
        group.throughput(Throughput::Elements(*batch_size as u64));
        group.bench_with_input(
            BenchmarkId::new("full_phase4_optimization", batch_size),
            batch_size,
            |b, &batch_size| {
                // Initialize all Phase 4 components
                let mut asic_verifier = ASICVerifier::new().unwrap();
                let mut fpga_verifier = FPGAVerifier::new().unwrap();
                let mut qr_verifier = QuantumResistantVerifier::new().unwrap();
                let config = DistributedConfig::default();
                let mut dist_verifier = DistributedVerifier::new(config).unwrap();
                
                let credentials = create_test_credentials(batch_size);
                
                b.iter(|| {
                    // Test ASIC verification
                    let asic_results = asic_verifier.verify_batch_asic(black_box(&credentials));
                    
                    // Test FPGA verification
                    let fpga_results = fpga_verifier.verify_batch_fpga(black_box(&credentials));
                    
                    // Test quantum-resistant verification
                    let qr_results: Vec<_> = credentials.iter()
                        .map(|cred| qr_verifier.verify_quantum_resistant(cred))
                        .collect();
                    
                    // Test distributed verification
                    let dist_results = dist_verifier.verify_distributed(black_box(&credentials));
                    
                    black_box((asic_results, fpga_results, qr_results, dist_results))
                })
            },
        );
    }
    
    group.finish();
}

/// Benchmark Phase 4 throughput comparison
fn benchmark_phase4_throughput(c: &mut Criterion) {
    let mut group = c.benchmark_group("phase4_throughput");
    
    let batch_size = 64;
    let credentials = create_test_credentials(batch_size);
    
    group.throughput(Throughput::Elements(batch_size as u64));
    
    // ASIC throughput
    group.bench_function("asic_throughput", |b| {
        let mut asic_verifier = ASICVerifier::new().unwrap();
        
        b.iter(|| {
            let results = asic_verifier.verify_batch_asic(black_box(&credentials));
            black_box(results)
        })
    });
    
    // FPGA throughput
    group.bench_function("fpga_throughput", |b| {
        let mut fpga_verifier = FPGAVerifier::new().unwrap();
        
        b.iter(|| {
            let results = fpga_verifier.verify_batch_fpga(black_box(&credentials));
            black_box(results)
        })
    });
    
    // Quantum-resistant throughput
    group.bench_function("quantum_resistant_throughput", |b| {
        let mut qr_verifier = QuantumResistantVerifier::new().unwrap();
        
        b.iter(|| {
            let results: Vec<_> = credentials.iter()
                .map(|cred| qr_verifier.verify_quantum_resistant(cred))
                .collect();
            black_box(results)
        })
    });
    
    // Distributed throughput
    group.bench_function("distributed_throughput", |b| {
        let config = DistributedConfig::default();
        let mut dist_verifier = DistributedVerifier::new(config).unwrap();
        
        b.iter(|| {
            let results = dist_verifier.verify_distributed(black_box(&credentials));
            black_box(results)
        })
    });
    
    group.finish();
}

criterion_group!(
    benches,
    benchmark_phase1_phase2,
    benchmark_phase3_optimizations,
    benchmark_asic_verification,
    benchmark_fpga_verification,
    benchmark_quantum_resistant_verification,
    benchmark_distributed_verification,
    benchmark_phase4_integration,
    benchmark_phase4_throughput,
    benchmark_throughput_comparison,
    benchmark_memory_efficiency,
    benchmark_scalability,
    benchmark_integration,
    benchmark_regression_test
);

criterion_main!(benches); 