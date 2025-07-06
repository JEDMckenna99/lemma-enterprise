# Browser Performance Testing Guide

## 🌐 **Manual Browser Testing for Lemma SDK**

This guide provides comprehensive instructions for testing the Lemma SDK performance in a browser environment, targeting <100ms offline verification.

---

## 🎯 **Testing Objectives**

- **Performance**: Validate <100ms offline verification target
- **Functionality**: Confirm all SDK features work in browser
- **Compatibility**: Test across different browsers
- **Bundle Size**: Validate 76KB target is maintained
- **User Experience**: Ensure smooth interaction

---

## 📋 **Step-by-Step Testing Instructions**

### **Step 1: Access the SDK Demo**

1. **Open Browser**: Use Chrome, Firefox, Safari, or Edge
2. **Navigate to**: https://lemma.id/sdk-demo
3. **Verify Page Load**: Page should load within 5 seconds
4. **Check Console**: Open Developer Tools (F12) → Console tab

### **Step 2: Basic Functionality Test**

**In the browser console, run:**

```javascript
// Test 1: Check if SDK is loaded
console.log("🔍 Testing SDK availability...");
if (typeof LemmaSDK !== 'undefined') {
    console.log("✅ LemmaSDK is available");
} else {
    console.log("❌ LemmaSDK not found");
}

// Test 2: Check SDK version and features
try {
    const sdk = new LemmaSDK({
        developmentMode: true,
        apiKey: 'test-key'
    });
    console.log("✅ SDK initialization successful");
    console.log("📊 SDK config keys:", Object.keys(sdk.config || {}).length);
} catch (e) {
    console.log("❌ SDK initialization failed:", e.message);
}
```

### **Step 3: Performance Benchmarking**

**Run this comprehensive performance test:**

```javascript
// Performance Testing Script
(async function testSDKPerformance() {
    console.log("🚀 Starting SDK Performance Test...");
    
    // Test 1: SDK Initialization Performance
    console.log("\n1. Testing SDK Initialization...");
    const initStart = performance.now();
    
    try {
        const sdk = new LemmaSDK({
            developmentMode: true,
            apiKey: 'test-key-performance'
        });
        
        const initTime = performance.now() - initStart;
        console.log(`✅ SDK initialized in: ${initTime.toFixed(2)}ms`);
        
        if (initTime < 100) {
            console.log("🎯 PERFORMANCE TARGET MET: < 100ms");
        } else {
            console.log("⚠️ Performance target missed: >= 100ms");
        }
        
        // Test 2: Check SDK Components
        console.log("\n2. Testing SDK Components...");
        console.log("Crypto Engine:", sdk.cryptoEngine ? "✅ Available" : "❌ Missing");
        console.log("Data Feed:", sdk.dataFeed ? "✅ Available" : "❌ Missing");
        console.log("Offline Verify:", typeof sdk.verifyOffline === 'function' ? "✅ Available" : "❌ Missing");
        console.log("Security:", sdk.security ? "✅ Available" : "❌ Missing");
        
        // Test 3: Bundle Size Analysis
        console.log("\n3. Analyzing Bundle Size...");
        const resources = performance.getEntriesByType('resource');
        const sdkResources = resources.filter(r => r.name.includes('lemma-sdk-unified.js'));
        
        if (sdkResources.length > 0) {
            const resource = sdkResources[0];
            const sizeKB = Math.round((resource.transferSize || resource.encodedBodySize || 0) / 1024);
            console.log(`✅ SDK bundle size: ${sizeKB}KB`);
            
            if (sizeKB <= 100) {
                console.log("🎯 BUNDLE SIZE TARGET MET: <= 100KB");
            } else {
                console.log("⚠️ Bundle size exceeds target: > 100KB");
            }
        }
        
        // Test 4: Configuration Validation
        console.log("\n4. Testing Configuration...");
        const config = sdk.config || {};
        console.log("Development Mode:", config.developmentMode ? "✅ Enabled" : "❌ Disabled");
        console.log("Production Mode:", config.productionMode ? "✅ Enabled" : "❌ Disabled");
        console.log("Security Level:", config.securityLevel || "Not set");
        
        // Test 5: Method Availability
        console.log("\n5. Testing Method Availability...");
        const methods = ['init', 'verifyOffline', 'generateProof', 'log'];
        methods.forEach(method => {
            console.log(`${method}:`, typeof sdk[method] === 'function' ? "✅ Available" : "❌ Missing");
        });
        
        console.log("\n🎉 SDK Performance Test Complete!");
        
    } catch (error) {
        console.log("❌ Performance test failed:", error.message);
    }
})();
```

### **Step 4: Offline Verification Test**

**Test offline verification capability:**

```javascript
// Offline Verification Test
(async function testOfflineVerification() {
    console.log("⚡ Testing Offline Verification...");
    
    try {
        const sdk = new LemmaSDK({
            developmentMode: true,
            apiKey: 'test-offline-verification'
        });
        
        // Initialize SDK
        await sdk.init();
        console.log("✅ SDK initialized for offline testing");
        
        // Test offline verification (simulation)
        const verifyStart = performance.now();
        
        // Simulate offline verification
        const testCredential = {
            id: 'test-credential-id',
            type: 'human',
            data: 'simulated-data'
        };
        
        // Check if verifyOffline method exists and is callable
        if (typeof sdk.verifyOffline === 'function') {
            console.log("✅ verifyOffline method available");
            
            // Note: This would normally verify against the cascade
            // For testing, we're just measuring the method call time
            const verifyResult = await sdk.verifyOffline(testCredential);
            
            const verifyTime = performance.now() - verifyStart;
            console.log(`✅ Offline verification completed in: ${verifyTime.toFixed(2)}ms`);
            
            if (verifyTime < 100) {
                console.log("🎯 OFFLINE VERIFICATION TARGET MET: < 100ms");
            } else {
                console.log("⚠️ Offline verification target missed: >= 100ms");
            }
            
        } else {
            console.log("❌ verifyOffline method not available");
        }
        
    } catch (error) {
        console.log("❌ Offline verification test failed:", error.message);
    }
})();
```

### **Step 5: Network Performance Analysis**

**Analyze network performance:**

```javascript
// Network Performance Analysis
(function analyzeNetworkPerformance() {
    console.log("🌐 Analyzing Network Performance...");
    
    const resources = performance.getEntriesByType('resource');
    const sdkResources = resources.filter(r => 
        r.name.includes('lemma') || 
        r.name.includes('sdk') || 
        r.name.includes('static/js')
    );
    
    console.log(`📊 Found ${sdkResources.length} SDK-related resources:`);
    
    sdkResources.forEach(resource => {
        const name = resource.name.split('/').pop();
        const duration = resource.duration.toFixed(2);
        const size = Math.round((resource.transferSize || resource.encodedBodySize || 0) / 1024);
        
        console.log(`   ${name}: ${duration}ms, ${size}KB`);
    });
    
    // Page load performance
    const navigation = performance.getEntriesByType('navigation')[0];
    if (navigation) {
        console.log("\n📈 Page Load Performance:");
        console.log(`   DOM Content Loaded: ${navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart}ms`);
        console.log(`   Load Complete: ${navigation.loadEventEnd - navigation.loadEventStart}ms`);
        console.log(`   First Paint: ${navigation.domContentLoadedEventEnd - navigation.fetchStart}ms`);
    }
})();
```

---

## 🧪 **Interactive Testing**

### **Test Interactive Elements**

1. **Look for test buttons** on the SDK demo page
2. **Click performance test buttons** if available
3. **Observe console output** for timing information
4. **Check for error messages** in the console

### **Visual Inspection**

1. **Page Layout**: Should be clean and professional
2. **Loading States**: Should show proper loading indicators
3. **Error Handling**: Should gracefully handle errors
4. **Mobile Responsiveness**: Test on mobile devices

---

## 🎯 **Performance Targets**

### **Primary Targets**
- **SDK Initialization**: < 100ms
- **Bundle Size**: ≤ 100KB (currently 76KB)
- **Page Load**: < 5 seconds
- **Offline Verification**: < 100ms

### **Secondary Targets**
- **First Paint**: < 2 seconds
- **Interactive**: < 3 seconds
- **Network Requests**: Minimal during offline operation
- **Memory Usage**: < 50MB

---

## 🌍 **Cross-Browser Testing**

### **Test on Multiple Browsers**

1. **Chrome** (Recommended)
   - Version 90+ for best performance
   - Developer tools for detailed analysis

2. **Firefox**
   - Test WebAssembly compatibility
   - Check for any browser-specific issues

3. **Safari**
   - Test on macOS/iOS
   - Verify mobile performance

4. **Edge**
   - Test on Windows environments
   - Check enterprise compatibility

### **Mobile Testing**

1. **Open on mobile device**: https://lemma.id/sdk-demo
2. **Run performance tests** using mobile browser console
3. **Check touch interactions** and responsiveness
4. **Validate bundle size** on limited bandwidth

---

## 📊 **Expected Results**

### **✅ Success Criteria**

- **SDK loads and initializes** within 100ms
- **All methods are available** and functional
- **Bundle size is ≤ 100KB** (currently 76KB)
- **Offline verification** completes within 100ms
- **No console errors** during normal operation
- **Performance metrics** meet or exceed targets

### **🔍 Troubleshooting Common Issues**

**Issue**: SDK not found in global scope
**Solution**: Check if script loaded properly, verify network tab

**Issue**: Initialization takes too long
**Solution**: Check network connection, verify CDN performance

**Issue**: Bundle size too large
**Solution**: Verify gzip compression is enabled

**Issue**: Console errors
**Solution**: Check for browser compatibility issues

---

## 📋 **Test Report Template**

```
🧪 Lemma SDK Browser Test Report
=====================================

Test Date: [DATE]
Browser: [BROWSER VERSION]
Platform: [OPERATING SYSTEM]

Performance Results:
- SDK Initialization: [TIME]ms
- Bundle Size: [SIZE]KB
- Page Load: [TIME]ms
- Offline Verification: [TIME]ms

Functionality Results:
- SDK Loading: [✅/❌]
- Method Availability: [✅/❌]
- Configuration: [✅/❌]
- Console Errors: [NONE/LIST]

Overall Assessment: [PASS/FAIL]
Notes: [ANY OBSERVATIONS]
```

---

## 🚀 **Next Steps After Testing**

1. **Document Results**: Record all performance metrics
2. **Share Screenshots**: Take screenshots of successful tests
3. **Report Issues**: Create tickets for any problems found
4. **Optimize Further**: If targets not met, identify optimization areas
5. **Customer Integration**: Proceed with customer demos if all tests pass

---

## 📞 **Support Information**

**If you encounter issues:**
- **Live Demo**: https://lemma.id/sdk-demo
- **Documentation**: https://lemma.id/docs
- **Support**: Contact development team with test results

**For Performance Issues:**
- Check browser developer tools
- Verify network conditions
- Test on different devices/browsers
- Report specific error messages

---

*This guide ensures comprehensive testing of the Lemma SDK in real browser environments, validating all performance targets and functionality requirements.* 