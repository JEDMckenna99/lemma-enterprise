#!/usr/bin/env python3

import requests

def check_deployed_methods():
    print("🔍 Checking deployed shield widget methods...")
    
    try:
        r = requests.get('https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-widget.js')
        content = r.text
        
        print(f"✅ Script loaded: {len(content)} characters")
        
        # Check for forceShow method definitions
        force_show_lines = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            if 'forceShow' in line:
                force_show_lines.append(f"Line {i+1}: {line.strip()}")
        
        print(f"\n🔍 Found {len(force_show_lines)} lines with 'forceShow':")
        for line in force_show_lines:
            print(f"  {line}")
        
        # Check for static methods
        static_methods = []
        for i, line in enumerate(lines):
            if 'static ' in line and 'forceShow' in line:
                static_methods.append(f"Line {i+1}: {line.strip()}")
        
        print(f"\n🔍 Found {len(static_methods)} static forceShow methods:")
        for method in static_methods:
            print(f"  {method}")
        
        # Check for global assignments
        global_assignments = []
        for i, line in enumerate(lines):
            if 'window.lemmaShield' in line or 'window.LemmaShieldWidget' in line:
                global_assignments.append(f"Line {i+1}: {line.strip()}")
        
        print(f"\n🔍 Found {len(global_assignments)} global assignments:")
        for assignment in global_assignments[:10]:  # Show first 10
            print(f"  {assignment}")
        
        # Check the end of the file for initialization
        print(f"\n🔍 Last 20 lines of the file:")
        for i, line in enumerate(lines[-20:]):
            print(f"  Line {len(lines)-20+i+1}: {line.strip()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_deployed_methods() 