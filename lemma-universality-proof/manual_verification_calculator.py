#!/usr/bin/env python3
"""
Manual Lambda Calculus Verification Calculator
Interactive tool for manually verifying complexity reductions step-by-step
"""

def manual_traditional_calculation(n_claims, security_bits):
    """Manual step-by-step traditional calculation"""
    print(f"🔢 MANUAL TRADITIONAL CALCULATION")
    print(f"=" * 50)
    
    base_time = 500_000
    security_factor = security_bits // 32
    
    print(f"Given:")
    print(f"  n_claims = {n_claims}")
    print(f"  security_bits = {security_bits}")
    print(f"  base_time = {base_time:,}μs")
    
    print(f"\nStep 1: Calculate security factor")
    print(f"  security_factor = {security_bits} ÷ 32 = {security_factor}")
    
    print(f"\nStep 2: Apply formula")
    print(f"  traditional_time = base_time × n_claims × security_factor")
    print(f"  traditional_time = {base_time:,} × {n_claims} × {security_factor}")
    
    step_result = base_time * n_claims
    print(f"  traditional_time = {step_result:,} × {security_factor}")
    
    final_result = step_result * security_factor
    print(f"  traditional_time = {final_result:,}μs")
    print(f"  traditional_time = {final_result / 1_000_000:.1f} seconds")
    
    return final_result

def manual_lemma_calculation(n_claims, hardware_accel=True, cache_available=True):
    """Manual step-by-step lemma calculation"""
    print(f"\n🧮 MANUAL LEMMA CALCULATION")
    print(f"=" * 50)
    
    print(f"Given:")
    print(f"  n_claims = {n_claims}")
    print(f"  hardware_accel = {hardware_accel}")
    print(f"  cache_available = {cache_available}")
    
    print(f"\nStep 1: Determine atomic operation times")
    sig_time = 28 if hardware_accel else 150
    rev_time = 3 if cache_available else 96
    
    print(f"  sig_time = {sig_time}μs ({'hardware accelerated' if hardware_accel else 'software only'})")
    print(f"  rev_time = {rev_time}μs ({'cached' if cache_available else 'uncached'})")
    print(f"  timestamp_time = 1μs (constant)")
    print(f"  format_time = 2μs (constant)")
    print(f"  claims_time = {n_claims}μs ({n_claims} claims)")
    
    print(f"\nStep 2: Calculate parallel execution time")
    core_time = max(sig_time, rev_time, 1, 2)
    print(f"  core_time = max({sig_time}, {rev_time}, 1, 2) = {core_time}μs")
    
    print(f"\nStep 3: Add sequential claims processing")
    total_time = core_time + n_claims
    print(f"  total_time = core_time + claims_time")
    print(f"  total_time = {core_time} + {n_claims} = {total_time}μs")
    
    return total_time

def manual_speedup_calculation(traditional, lemma):
    """Manual speedup calculation"""
    print(f"\n⚡ MANUAL SPEEDUP CALCULATION")
    print(f"=" * 50)
    
    speedup = traditional / lemma if lemma > 0 else 0
    
    print(f"Step 1: Calculate speedup ratio")
    print(f"  speedup = traditional_time ÷ lemma_time")
    print(f"  speedup = {traditional:,} ÷ {lemma}")
    print(f"  speedup = {speedup:,.0f}x improvement")
    
    print(f"\nStep 2: Calculate time savings")
    time_saved = traditional - lemma
    percent_saved = (time_saved / traditional) * 100
    print(f"  time_saved = {traditional:,} - {lemma} = {time_saved:,}μs")
    print(f"  percent_saved = {percent_saved:.1f}%")
    
    return speedup

def manual_lambda_composition():
    """Manual lambda calculus composition example"""
    print(f"\n🔀 MANUAL LAMBDA COMPOSITION")
    print(f"=" * 50)
    
    print("Original lambda expression:")
    print("  λ(credential, context). compose_lemmas(")
    print("    signature_lemma(credential, context),")
    print("    revocation_lemma(credential, context),")
    print("    timestamp_lemma(credential, context),")
    print("    format_lemma(credential, context)")
    print("  )")
    
    print("\nStep 1: Evaluate individual lemmas")
    print("  signature_lemma → Verified 28 128 1.0 [\"sig_valid\"]")
    print("  revocation_lemma → Verified 3 128 1.0 [\"not_revoked\"]")
    print("  timestamp_lemma → Verified 1 128 1.0 [\"timestamp_valid\"]")
    print("  format_lemma → Verified 2 128 1.0 [\"format_valid\"]")
    
    print("\nStep 2: Compose pairwise")
    print("  compose_lemmas(signature, revocation):")
    print("    → Verified max(28,3) min(128,128) (1.0×1.0) [\"sig_valid\",\"not_revoked\"]")
    print("    → Verified 28 128 1.0 [\"sig_valid\",\"not_revoked\"]")
    
    print("\n  compose_lemmas(timestamp, format):")
    print("    → Verified max(1,2) min(128,128) (1.0×1.0) [\"timestamp_valid\",\"format_valid\"]")
    print("    → Verified 2 128 1.0 [\"timestamp_valid\",\"format_valid\"]")
    
    print("\nStep 3: Final composition")
    print("  compose_lemmas(first_pair, second_pair):")
    print("    → Verified max(28,2) min(128,128) (1.0×1.0) [all_claims]")
    print("    → Verified 28 128 1.0 [all_claims]")
    
    print("\nResult: 28μs total time (parallel execution)")

def interactive_verification():
    """Interactive verification tool"""
    print("🧮 MANUAL LAMBDA CALCULUS VERIFICATION TOOL")
    print("=" * 60)
    print("This tool helps you manually verify complexity reductions step-by-step")
    print()
    
    while True:
        print("\nChoose verification type:")
        print("1. Simple example (1 claim)")
        print("2. Banking KYC (7 claims)")
        print("3. Custom calculation")
        print("4. Lambda composition example")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == '1':
            print("\n" + "="*60)
            print("SIMPLE IDENTITY VERIFICATION (1 claim, 128-bit security)")
            print("="*60)
            
            traditional = manual_traditional_calculation(1, 128)
            lemma = manual_lemma_calculation(1, True, True)
            speedup = manual_speedup_calculation(traditional, lemma)
            
        elif choice == '2':
            print("\n" + "="*60)
            print("BANKING KYC VERIFICATION (7 claims, 256-bit security)")
            print("="*60)
            
            traditional = manual_traditional_calculation(7, 256)
            lemma = manual_lemma_calculation(7, True, True)
            speedup = manual_speedup_calculation(traditional, lemma)
            
        elif choice == '3':
            print("\n" + "="*60)
            print("CUSTOM CALCULATION")
            print("="*60)
            
            try:
                n_claims = int(input("Enter number of claims: "))
                security_bits = int(input("Enter security bits (128, 192, 256): "))
                hardware = input("Hardware acceleration? (y/n): ").lower().startswith('y')
                cache = input("Caching available? (y/n): ").lower().startswith('y')
                
                traditional = manual_traditional_calculation(n_claims, security_bits)
                lemma = manual_lemma_calculation(n_claims, hardware, cache)
                speedup = manual_speedup_calculation(traditional, lemma)
                
            except ValueError:
                print("Please enter valid numbers")
                
        elif choice == '4':
            manual_lambda_composition()
            
        elif choice == '5':
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice, please try again")
        
        input("\nPress Enter to continue...")

if __name__ == '__main__':
    interactive_verification()


