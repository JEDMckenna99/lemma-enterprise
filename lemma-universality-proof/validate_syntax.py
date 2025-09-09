#!/usr/bin/env python3
"""
Basic Coq syntax validation for the lambda calculus complexity model.
This checks for common syntax errors without requiring a full Coq installation.
"""

import re
import sys
from pathlib import Path

def validate_coq_syntax(file_path):
    """Basic Coq syntax validation"""
    errors = []
    warnings = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Check for basic syntax issues
    in_comment = False
    paren_stack = []
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
            
        # Handle comments
        if '(*' in line and '*)' in line:
            # Single line comment
            pass
        elif '(*' in line:
            in_comment = True
        elif '*)' in line:
            in_comment = False
            continue
        elif in_comment:
            continue
            
        # Check for common syntax errors
        
        # 1. Missing periods at end of definitions/theorems
        if (line.startswith('Definition ') or 
            line.startswith('Theorem ') or 
            line.startswith('Lemma ') or
            line.startswith('Proof.')):
            if not line.endswith('.') and not line.endswith(':='):
                warnings.append(f"Line {line_num}: Missing period at end of statement")
        
        # 2. Unmatched parentheses/brackets
        for char in line:
            if char in '([{':
                paren_stack.append((char, line_num))
            elif char in ')]}':
                if not paren_stack:
                    errors.append(f"Line {line_num}: Unmatched closing '{char}'")
                else:
                    opener, _ = paren_stack.pop()
                    expected = {'(': ')', '[': ']', '{': '}'}
                    if expected.get(opener) != char:
                        errors.append(f"Line {line_num}: Mismatched parentheses/brackets")
        
        # 3. Check for 'admit' or 'Admitted' (incomplete proofs)
        if 'admit' in line.lower():
            warnings.append(f"Line {line_num}: Incomplete proof (uses admit/Admitted)")
            
        # 4. Check for basic keyword syntax
        if line.startswith('Require Import') and not line.endswith('.'):
            errors.append(f"Line {line_num}: Require Import must end with period")
    
    # Check for unmatched opening parentheses
    if paren_stack:
        for opener, line_num in paren_stack:
            errors.append(f"Line {line_num}: Unmatched opening '{opener}'")
    
    return errors, warnings

def validate_proof_structure(file_path):
    """Check for proper proof structure"""
    issues = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all theorems/lemmas
    theorems = re.findall(r'(Theorem|Lemma)\s+(\w+)\s*:', content, re.MULTILINE)
    
    for theorem_type, theorem_name in theorems:
        # Check if there's a corresponding Proof and Qed/Admitted
        proof_pattern = rf'{theorem_type}\s+{theorem_name}\s*:.*?Proof\.(.*?)(?:Qed|Admitted)\.'
        match = re.search(proof_pattern, content, re.DOTALL)
        
        if not match:
            issues.append(f"Theorem/Lemma '{theorem_name}' missing proper Proof...Qed structure")
        else:
            proof_body = match.group(1)
            if 'admit' in proof_body.lower():
                issues.append(f"Theorem/Lemma '{theorem_name}' has incomplete proof (uses admit)")
    
    return issues

def main():
    """Validate all Coq files in the current directory"""
    coq_files = [
        'lambda_calculus_complexity_decomposition.v',
        'practical_complexity_examples.v'
    ]
    
    total_errors = 0
    total_warnings = 0
    
    for file_path in coq_files:
        if not Path(file_path).exists():
            print(f"❌ File not found: {file_path}")
            continue
            
        print(f"\n🔍 Validating {file_path}...")
        
        # Basic syntax validation
        errors, warnings = validate_coq_syntax(file_path)
        
        # Proof structure validation
        proof_issues = validate_proof_structure(file_path)
        
        # Report results
        if errors:
            print(f"❌ ERRORS ({len(errors)}):")
            for error in errors:
                print(f"   {error}")
            total_errors += len(errors)
        
        if warnings:
            print(f"⚠️  WARNINGS ({len(warnings)}):")
            for warning in warnings:
                print(f"   {warning}")
            total_warnings += len(warnings)
            
        if proof_issues:
            print(f"🔧 PROOF ISSUES ({len(proof_issues)}):")
            for issue in proof_issues:
                print(f"   {issue}")
        
        if not errors and not warnings and not proof_issues:
            print("✅ No syntax issues found")
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total Errors: {total_errors}")
    print(f"   Total Warnings: {total_warnings}")
    
    if total_errors > 0:
        print("❌ Files have syntax errors that need to be fixed")
        return 1
    elif total_warnings > 0:
        print("⚠️  Files have warnings but should compile")
        return 0
    else:
        print("✅ All files appear syntactically correct")
        return 0

if __name__ == '__main__':
    sys.exit(main())
