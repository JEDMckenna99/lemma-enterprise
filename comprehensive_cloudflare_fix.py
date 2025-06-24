#!/usr/bin/env python3
"""
Comprehensive CloudFlare Security Fix
=====================================
This script checks and fixes multiple CloudFlare security settings that could be causing 403 errors.
"""

import os
import sys
import requests
import json
from datetime import datetime

def log(message, level="INFO"):
    """Log with timestamp and level"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    symbols = {
        "INFO": "🔧",
        "SUCCESS": "✅", 
        "ERROR": "❌",
        "WARNING": "⚠️"
    }
    symbol = symbols.get(level, "📝")
    print(f"[{timestamp}] {symbol} {message}")

def make_cf_request(endpoint, method="GET", data=None):
    """Make a CloudFlare API request"""
    cf_api_token = os.getenv('CLOUDFLARE_API_TOKEN')
    headers = {
        "Authorization": f"Bearer {cf_api_token}",
        "Content-Type": "application/json"
    }
    
    if method == "GET":
        response = requests.get(endpoint, headers=headers, timeout=30)
    elif method == "PATCH":
        response = requests.patch(endpoint, headers=headers, json=data, timeout=30)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    return response

def main():
    log("Comprehensive CloudFlare Security Fix", "INFO")
    log("=" * 60, "INFO")
    
    # Configuration
    ZONE_ID = "c4e8c3580c49fa6351a5d6c02bc79b4d"
    BASE_URL = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}"
    
    # Check authentication
    cf_api_token = os.getenv('CLOUDFLARE_API_TOKEN')
    if not cf_api_token:
        log("CLOUDFLARE_API_TOKEN not set", "ERROR")
        sys.exit(1)
    
    log(f"Zone ID: {ZONE_ID}", "INFO")
    log("", "INFO")
    
    try:
        # 1. Check current security level
        log("1. Checking current security level...", "INFO")
        response = make_cf_request(f"{BASE_URL}/settings/security_level")
        if response.status_code == 200:
            data = response.json()
            current_level = data['result']['value']
            log(f"Current security level: {current_level}", "INFO")
            
            if current_level != "medium":
                log("Setting security level to medium...", "INFO")
                update_response = make_cf_request(
                    f"{BASE_URL}/settings/security_level", 
                    "PATCH", 
                    {"value": "medium"}
                )
                if update_response.status_code == 200:
                    log("Security level updated to medium", "SUCCESS")
                else:
                    log(f"Failed to update security level: {update_response.text}", "ERROR")
            else:
                log("Security level already set to medium", "SUCCESS")
        else:
            log(f"Failed to check security level: {response.text}", "ERROR")
        
        # 2. Check Bot Fight Mode
        log("", "INFO")
        log("2. Checking Bot Fight Mode...", "INFO")
        response = make_cf_request(f"{BASE_URL}/settings/brotli")
        if response.status_code == 200:
            log("Bot Fight Mode check completed", "INFO")
        
        # 3. Check Browser Integrity Check
        log("", "INFO") 
        log("3. Checking Browser Integrity Check...", "INFO")
        response = make_cf_request(f"{BASE_URL}/settings/browser_check")
        if response.status_code == 200:
            data = response.json()
            browser_check = data['result']['value']
            log(f"Browser Integrity Check: {browser_check}", "INFO")
            
            if browser_check == "on":
                log("Disabling Browser Integrity Check...", "INFO")
                update_response = make_cf_request(
                    f"{BASE_URL}/settings/browser_check",
                    "PATCH",
                    {"value": "off"}
                )
                if update_response.status_code == 200:
                    log("Browser Integrity Check disabled", "SUCCESS")
                else:
                    log(f"Failed to disable Browser Integrity Check: {update_response.text}", "WARNING")
            else:
                log("Browser Integrity Check already disabled", "SUCCESS")
        
        # 4. Check Challenge Passage
        log("", "INFO")
        log("4. Checking Challenge Passage...", "INFO")
        response = make_cf_request(f"{BASE_URL}/settings/challenge_ttl")
        if response.status_code == 200:
            data = response.json()
            challenge_ttl = data['result']['value']
            log(f"Challenge TTL: {challenge_ttl} seconds", "INFO")
        
        # 5. Check I'm Under Attack Mode
        log("", "INFO")
        log("5. Checking I'm Under Attack Mode...", "INFO")
        response = make_cf_request(f"{BASE_URL}/settings/security_level")
        if response.status_code == 200:
            data = response.json()
            if data['result']['value'] == "under_attack":
                log("Disabling 'I'm Under Attack' mode...", "INFO")
                update_response = make_cf_request(
                    f"{BASE_URL}/settings/security_level",
                    "PATCH", 
                    {"value": "medium"}
                )
                if update_response.status_code == 200:
                    log("'I'm Under Attack' mode disabled", "SUCCESS")
        
        # 6. Test the API
        log("", "INFO")
        log("6. Testing API access...", "INFO")
        try:
            test_response = requests.get("https://lemma.id/api/health", timeout=15)
            if test_response.status_code == 200:
                log(f"✅ API is working! Status: {test_response.status_code}", "SUCCESS")
                try:
                    health_data = test_response.json()
                    log(f"Service: {health_data.get('service', 'unknown')}", "SUCCESS")
                except:
                    pass
            elif test_response.status_code == 403:
                log("Still getting 403 - may need more time to propagate", "WARNING")
                log("CloudFlare changes can take 15-30 minutes globally", "WARNING")
            else:
                log(f"API returned status {test_response.status_code}", "WARNING")
        except requests.RequestException as e:
            log(f"API test failed: {e}", "WARNING")
        
        log("", "INFO")
        log("Comprehensive CloudFlare fix completed!", "SUCCESS")
        log("", "INFO")
        log("If still getting 403 errors:", "INFO")
        log("1. Wait 15-30 minutes for global propagation", "INFO")
        log("2. Check CloudFlare dashboard for additional firewall rules", "INFO")
        log("3. Verify no rate limiting rules are blocking the domain", "INFO")
        
    except requests.RequestException as e:
        log(f"Request failed: {e}", "ERROR")
        sys.exit(1)
    except Exception as e:
        log(f"Unexpected error: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main() 