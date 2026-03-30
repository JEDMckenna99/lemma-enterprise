
use lemma_crypto::LemmaCore;
use std::time::Instant;

fn main() {
    let mut core = LemmaCore::new().unwrap();
    
    // Create a simple test credential
    let credential = lemma_crypto::VerifiableCredential {
        id: "test_id".to_string(),
        issuer: "test_issuer".to_string(),
        subject: "test_subject".to_string(),
        claims: std::collections::HashMap::new(),
        signature: vec![0u8; 64],
        created: std::time::SystemTime::now(),
        expires: None,
        revocation_list_url: None,
        package_type: "identity".to_string(),
    };
    
    // Cold start (first verification)
    let start = Instant::now();
    let _ = core.verify(&credential);
    let cold_time = start.elapsed().as_nanos();
    
    // Warm up with 100 verifications
    for _ in 0..100 {
        let _ = core.verify(&credential);
    }
    
    // Hot verification (cached)
    let start = Instant::now();
    let _ = core.verify(&credential);
    let hot_time = start.elapsed().as_nanos();
    
    println!("cold_verification_ns: {}", cold_time);
    println!("hot_verification_ns: {}", hot_time);
    
    // Statistical sample for hot verification
    let mut hot_times = Vec::new();
    for _ in 0..10000 {
        let start = Instant::now();
        let _ = core.verify(&credential);
        hot_times.push(start.elapsed().as_nanos());
    }
    
    let mean = hot_times.iter().sum::<u128>() as f64 / hot_times.len() as f64;
    let variance = hot_times.iter().map(|&x| (x as f64 - mean).powi(2)).sum::<f64>() / hot_times.len() as f64;
    let std_dev = variance.sqrt();
    
    println!("hot_verification_mean_ns: {:.2}", mean);
    println!("hot_verification_std_ns: {:.2}", std_dev);
    println!("hot_verification_min_ns: {}", hot_times.iter().min().unwrap());
    println!("hot_verification_max_ns: {}", hot_times.iter().max().unwrap());
    
    // Batch verification
    let credentials: Vec<_> = (0..10).map(|i| {
        let mut cred = credential.clone();
        cred.id = format!("test_id_{}", i);
        cred
    }).collect();
    
    let start = Instant::now();
    let _ = core.verify_batch(&credentials);
    let batch_time = start.elapsed().as_nanos() / 10;
    
    println!("batch_verification_per_item_ns: {}", batch_time);
}
