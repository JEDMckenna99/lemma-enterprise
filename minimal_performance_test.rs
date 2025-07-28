use std::time::Instant;
use std::collections::HashMap;

fn main() {
    println!("🚀 Minimal Lemma Verification Performance Test");
    println!("==============================================");
    
    // Test basic instantiation timing
    println!("\n📊 Test 1: LemmaCore Instantiation");
    let start = Instant::now();
    
    let core_result = lemma_crypto::LemmaCore::new();
    let init_time = start.elapsed();
    
    println!("✅ LemmaCore initialization: {}ns ({:.3}µs)", 
             init_time.as_nanos(), init_time.as_nanos() as f64 / 1000.0);
    
    let mut core = match core_result {
        Ok(core) => core,
        Err(e) => {
            println!("❌ Failed to initialize LemmaCore: {}", e);
            return;
        }
    };
    
    // Test basic credential creation
    println!("\n📊 Test 2: Credential Creation");
    let start = Instant::now();
    
    let mut claims = HashMap::new();
    claims.insert("type".to_string(), "test".to_string());
    
    let credential = lemma_crypto::VerifiableCredential::new(
        "test_issuer".to_string(),
        "test_subject".to_string(),
        claims,
        None,
    );
    
    let creation_time = start.elapsed();
    println!("✅ Credential creation: {}ns ({:.3}µs)", 
             creation_time.as_nanos(), creation_time.as_nanos() as f64 / 1000.0);
    
    // Test single verification
    println!("\n📊 Test 3: Single Verification");
    let start = Instant::now();
    
    let verify_result = core.verify(&credential);
    let verify_time = start.elapsed();
    
    match verify_result {
        Ok(_) => {
            println!("✅ Single verification: {}ns ({:.3}µs)", 
                     verify_time.as_nanos(), verify_time.as_nanos() as f64 / 1000.0);
        }
        Err(e) => {
            println!("❌ Single verification failed: {}", e);
            return;
        }
    }
    
    // Test repeated verification for caching effects
    println!("\n📊 Test 4: Repeated Verification (Caching Test)");
    let iterations = 1000;
    let mut times = Vec::with_capacity(iterations);
    
    for i in 0..iterations {
        let start = Instant::now();
        
        if let Ok(_) = core.verify(&credential) {
            times.push(start.elapsed().as_nanos());
        } else {
            println!("❌ Verification {} failed", i + 1);
        }
        
        if (i + 1) % 100 == 0 {
            println!("   Completed {} verifications", i + 1);
        }
    }
    
    if !times.is_empty() {
        let sum: u128 = times.iter().sum();
        let mean = sum as f64 / times.len() as f64;
        
        times.sort_unstable();
        let median = times[times.len() / 2] as f64;
        let min = times[0] as f64;
        let max = times[times.len() - 1] as f64;
        
        println!("✅ Repeated verification statistics:");
        println!("   Mean: {:.2}ns ({:.3}µs)", mean, mean / 1000.0);
        println!("   Median: {:.2}ns ({:.3}µs)", median, median / 1000.0);
        println!("   Min: {:.2}ns ({:.3}µs)", min, min / 1000.0);
        println!("   Max: {:.2}ns ({:.3}µs)", max, max / 1000.0);
        println!("   Samples: {}", times.len());
        
        let throughput = 1_000_000_000.0 / mean;
        println!("   Throughput: {:.0} ops/sec", throughput);
    }
    
    // Test batch verification
    println!("\n📊 Test 5: Batch Verification");
    let batch_sizes = vec![1, 5, 10];
    
    for &batch_size in &batch_sizes {
        let credentials: Vec<_> = (0..batch_size)
            .map(|i| {
                let mut cred_claims = HashMap::new();
                cred_claims.insert("type".to_string(), "test".to_string());
                cred_claims.insert("id".to_string(), i.to_string());
                
                lemma_crypto::VerifiableCredential::new(
                    "test_issuer".to_string(),
                    format!("test_subject_{}", i),
                    cred_claims,
                    None,
                )
            })
            .collect();
        
        let start = Instant::now();
        match core.verify_batch(&credentials) {
            Ok(_) => {
                let batch_time = start.elapsed();
                let per_item_ns = batch_time.as_nanos() / batch_size as u128;
                println!("   Batch size {}: {}ns ({:.3}µs) per item", 
                        batch_size, per_item_ns, per_item_ns as f64 / 1000.0);
            }
            Err(e) => {
                println!("   ❌ Batch size {} failed: {}", batch_size, e);
            }
        }
    }
    
    // Performance summary
    println!("\n🎯 Performance Summary");
    println!("=====================");
    
    if !times.is_empty() {
        let sum: u128 = times.iter().sum();
        let mean = sum as f64 / times.len() as f64;
        let throughput = 1_000_000_000.0 / mean;
        
        println!("✅ Average verification time: {:.2}ns ({:.3}µs)", mean, mean / 1000.0);
        println!("✅ Throughput: {:.0} verifications/second", throughput);
        
        // Performance classification
        if mean < 1000.0 {
            println!("🏆 Performance Class: EXCELLENT (sub-microsecond)");
        } else if mean < 10000.0 {
            println!("🥇 Performance Class: VERY GOOD (sub-10µs)");
        } else if mean < 100000.0 {
            println!("🥈 Performance Class: GOOD (sub-100µs)");
        } else {
            println!("🥉 Performance Class: ACCEPTABLE (>100µs)");
        }
        
        // Quick validation of reasonable performance
        println!("\n🔍 Reality Check");
        println!("================");
        
        if mean < 1_000_000.0 {
            println!("✅ Sub-millisecond verification achieved");
        } else {
            println!("❌ Verification taking >1ms - may need optimization");
        }
        
        if throughput > 1000.0 {
            println!("✅ Throughput >1K ops/sec achieved");
        } else {
            println!("❌ Low throughput - may need optimization");
        }
    }
    
    println!("\n🎉 Minimal performance test complete!");
} 