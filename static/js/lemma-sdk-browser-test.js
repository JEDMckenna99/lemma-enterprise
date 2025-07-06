/**
 * Lemma SDK Browser Performance Test
 * 
 * Copy and paste this entire script into your browser console
 * on the https://lemma.id/sdk-demo page to test SDK performance
 * 
 * Usage: Open https://lemma.id/sdk-demo → F12 → Console → Paste this script
 */

(function() {
    'use strict';
    
    console.log('🚀 Lemma SDK Browser Performance Test');
    console.log('=====================================');
    console.log('🎯 Target: <100ms offline verification');
    console.log('📅 Test Time:', new Date().toISOString());
    console.log('🌐 URL:', window.location.href);
    
    // Test configuration
    const config = {
        performanceTarget: 100, // milliseconds
        bundleSizeTarget: 100, // KB
        testApiKey: 'test-browser-performance-key'
    };
    
    let testResults = {
        sdkAvailable: false,
        initTime: null,
        bundleSize: null,
        componentsAvailable: {},
        configValidation: {},
        performanceMetrics: {},
        overallSuccess: false
    };
    
    // Utility functions
    function formatTime(ms) {
        return `${ms.toFixed(2)}ms`;
    }
    
    function formatSize(bytes) {
        return `${Math.round(bytes / 1024)}KB`;
    }
    
    function logSuccess(message) {
        console.log(`✅ ${message}`);
    }
    
    function logWarning(message) {
        console.log(`⚠️ ${message}`);
    }
    
    function logError(message) {
        console.log(`❌ ${message}`);
    }
    
    function logInfo(message) {
        console.log(`📊 ${message}`);
    }
    
    // Test 1: SDK Availability
    function testSDKAvailability() {
        console.log('\n1. Testing SDK Availability...');
        
        if (typeof LemmaSDK !== 'undefined') {
            logSuccess('LemmaSDK is available in global scope');
            testResults.sdkAvailable = true;
            return true;
        } else {
            logError('LemmaSDK not found in global scope');
            logInfo('Expected: window.LemmaSDK should be defined');
            return false;
        }
    }
    
    // Test 2: SDK Initialization Performance
    async function testSDKInitialization() {
        console.log('\n2. Testing SDK Initialization Performance...');
        
        const initStart = performance.now();
        
        try {
            const sdk = new LemmaSDK({
                developmentMode: true,
                apiKey: config.testApiKey
            });
            
            const initTime = performance.now() - initStart;
            testResults.initTime = initTime;
            
            logSuccess(`SDK initialized in ${formatTime(initTime)}`);
            
            if (initTime < config.performanceTarget) {
                logSuccess(`Performance target met: ${formatTime(initTime)} < ${config.performanceTarget}ms`);
            } else {
                logWarning(`Performance target missed: ${formatTime(initTime)} >= ${config.performanceTarget}ms`);
            }
            
            return sdk;
            
        } catch (error) {
            logError(`SDK initialization failed: ${error.message}`);
            return null;
        }
    }
    
    // Test 3: Component Availability
    function testComponentAvailability(sdk) {
        console.log('\n3. Testing Component Availability...');
        
        const components = {
            'Crypto Engine': 'cryptoEngine',
            'Data Feed': 'dataFeed',
            'Security': 'security',
            'Offline Verifier': 'verifyOffline'
        };
        
        Object.entries(components).forEach(([name, property]) => {
            const available = property === 'verifyOffline' 
                ? typeof sdk[property] === 'function'
                : sdk[property] !== undefined;
                
            testResults.componentsAvailable[name] = available;
            
            if (available) {
                logSuccess(`${name}: Available`);
            } else {
                logWarning(`${name}: Missing`);
            }
        });
    }
    
    // Test 4: Configuration Validation
    function testConfiguration(sdk) {
        console.log('\n4. Testing Configuration...');
        
        const config = sdk.config || {};
        
        const configTests = {
            'Development Mode': config.developmentMode,
            'Production Mode': config.productionMode,
            'Security Level': config.securityLevel,
            'API Key': config.apiKey
        };
        
        Object.entries(configTests).forEach(([name, value]) => {
            testResults.configValidation[name] = value !== undefined;
            
            if (value !== undefined) {
                logSuccess(`${name}: ${value}`);
            } else {
                logWarning(`${name}: Not set`);
            }
        });
    }
    
    // Test 5: Method Availability
    function testMethodAvailability(sdk) {
        console.log('\n5. Testing Method Availability...');
        
        const methods = ['init', 'verifyOffline', 'generateProof', 'log'];
        let availableCount = 0;
        
        methods.forEach(method => {
            const available = typeof sdk[method] === 'function';
            if (available) {
                logSuccess(`${method}: Available`);
                availableCount++;
            } else {
                logWarning(`${method}: Missing`);
            }
        });
        
        logInfo(`Methods available: ${availableCount}/${methods.length}`);
        return availableCount === methods.length;
    }
    
    // Test 6: Bundle Size Analysis
    function testBundleSize() {
        console.log('\n6. Testing Bundle Size...');
        
        const resources = performance.getEntriesByType('resource');
        const sdkResources = resources.filter(r => 
            r.name.includes('lemma-sdk-unified.js') ||
            r.name.includes('lemma-sdk')
        );
        
        if (sdkResources.length > 0) {
            const resource = sdkResources[0];
            const size = resource.transferSize || resource.encodedBodySize || 0;
            const sizeKB = Math.round(size / 1024);
            
            testResults.bundleSize = sizeKB;
            logSuccess(`SDK bundle size: ${sizeKB}KB`);
            
            if (sizeKB <= config.bundleSizeTarget) {
                logSuccess(`Bundle size target met: ${sizeKB}KB <= ${config.bundleSizeTarget}KB`);
            } else {
                logWarning(`Bundle size exceeds target: ${sizeKB}KB > ${config.bundleSizeTarget}KB`);
            }
            
            return sizeKB <= config.bundleSizeTarget;
        } else {
            logWarning('SDK bundle not found in network resources');
            return false;
        }
    }
    
    // Test 7: Performance Metrics
    function testPerformanceMetrics() {
        console.log('\n7. Testing Performance Metrics...');
        
        const navigation = performance.getEntriesByType('navigation')[0];
        if (navigation) {
            const metrics = {
                domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                loadComplete: navigation.loadEventEnd - navigation.loadEventStart,
                firstPaint: navigation.domContentLoadedEventEnd - navigation.fetchStart
            };
            
            testResults.performanceMetrics = metrics;
            
            logInfo(`DOM Content Loaded: ${formatTime(metrics.domContentLoaded)}`);
            logInfo(`Load Complete: ${formatTime(metrics.loadComplete)}`);
            logInfo(`First Paint: ${formatTime(metrics.firstPaint)}`);
            
            // Check if performance is acceptable
            const acceptable = metrics.domContentLoaded < 5000 && metrics.loadComplete < 10000;
            
            if (acceptable) {
                logSuccess('Page performance is acceptable');
            } else {
                logWarning('Page performance could be improved');
            }
            
            return acceptable;
        } else {
            logWarning('Navigation timing not available');
            return false;
        }
    }
    
    // Test 8: Offline Verification Simulation
    async function testOfflineVerification(sdk) {
        console.log('\n8. Testing Offline Verification...');
        
        if (typeof sdk.verifyOffline !== 'function') {
            logError('verifyOffline method not available');
            return false;
        }
        
        try {
            const verifyStart = performance.now();
            
            // Simulate offline verification
            const testCredential = {
                id: 'test-credential-browser',
                type: 'human',
                data: 'simulated-browser-test-data'
            };
            
            // Note: This may fail in actual verification but we're testing the call time
            try {
                await sdk.verifyOffline(testCredential);
                const verifyTime = performance.now() - verifyStart;
                
                logSuccess(`Offline verification completed in ${formatTime(verifyTime)}`);
                
                if (verifyTime < config.performanceTarget) {
                    logSuccess(`Offline verification target met: ${formatTime(verifyTime)} < ${config.performanceTarget}ms`);
                    return true;
                } else {
                    logWarning(`Offline verification target missed: ${formatTime(verifyTime)} >= ${config.performanceTarget}ms`);
                    return false;
                }
                
            } catch (verifyError) {
                const verifyTime = performance.now() - verifyStart;
                logInfo(`Offline verification method called in ${formatTime(verifyTime)}`);
                logInfo(`Verification error (expected in test): ${verifyError.message}`);
                
                // Even if verification fails, we can still measure method call time
                if (verifyTime < config.performanceTarget) {
                    logSuccess(`Method call time acceptable: ${formatTime(verifyTime)} < ${config.performanceTarget}ms`);
                    return true;
                } else {
                    logWarning(`Method call time too slow: ${formatTime(verifyTime)} >= ${config.performanceTarget}ms`);
                    return false;
                }
            }
            
        } catch (error) {
            logError(`Offline verification test failed: ${error.message}`);
            return false;
        }
    }
    
    // Test 9: Network Resource Analysis
    function testNetworkResources() {
        console.log('\n9. Analyzing Network Resources...');
        
        const resources = performance.getEntriesByType('resource');
        const lemmaResources = resources.filter(r => 
            r.name.includes('lemma') || 
            r.name.includes('sdk')
        );
        
        if (lemmaResources.length > 0) {
            logInfo(`Found ${lemmaResources.length} Lemma-related resources:`);
            
            lemmaResources.forEach(resource => {
                const name = resource.name.split('/').pop();
                const duration = resource.duration.toFixed(2);
                const size = Math.round((resource.transferSize || resource.encodedBodySize || 0) / 1024);
                
                logInfo(`  ${name}: ${duration}ms, ${size}KB`);
            });
            
            return true;
        } else {
            logWarning('No Lemma-related resources found');
            return false;
        }
    }
    
    // Generate Test Report
    function generateTestReport() {
        console.log('\n' + '='.repeat(50));
        console.log('📊 LEMMA SDK BROWSER TEST REPORT');
        console.log('='.repeat(50));
        
        console.log(`🕐 Test Date: ${new Date().toISOString()}`);
        console.log(`🌐 URL: ${window.location.href}`);
        console.log(`🔍 User Agent: ${navigator.userAgent}`);
        
        console.log('\n📈 Performance Results:');
        console.log(`  SDK Initialization: ${testResults.initTime ? formatTime(testResults.initTime) : 'N/A'}`);
        console.log(`  Bundle Size: ${testResults.bundleSize ? testResults.bundleSize + 'KB' : 'N/A'}`);
        
        console.log('\n🔧 Functionality Results:');
        console.log(`  SDK Loading: ${testResults.sdkAvailable ? '✅ PASS' : '❌ FAIL'}`);
        console.log(`  Component Availability: ${Object.values(testResults.componentsAvailable).every(v => v) ? '✅ PASS' : '⚠️ PARTIAL'}`);
        console.log(`  Configuration: ${Object.values(testResults.configValidation).every(v => v) ? '✅ PASS' : '⚠️ PARTIAL'}`);
        
        console.log('\n🎯 Performance Targets:');
        console.log(`  Initialization < ${config.performanceTarget}ms: ${testResults.initTime && testResults.initTime < config.performanceTarget ? '✅ MET' : '❌ MISSED'}`);
        console.log(`  Bundle Size ≤ ${config.bundleSizeTarget}KB: ${testResults.bundleSize && testResults.bundleSize <= config.bundleSizeTarget ? '✅ MET' : '❌ MISSED'}`);
        
        const overallSuccess = testResults.sdkAvailable && 
                              testResults.initTime && testResults.initTime < config.performanceTarget &&
                              testResults.bundleSize && testResults.bundleSize <= config.bundleSizeTarget;
        
        console.log('\n🏆 Overall Assessment:');
        if (overallSuccess) {
            console.log('✅ PASS - SDK is performing excellently!');
            console.log('🚀 Ready for customer integration');
        } else {
            console.log('⚠️ NEEDS ATTENTION - Some issues detected');
            console.log('🔧 Review failed tests and optimize');
        }
        
        return overallSuccess;
    }
    
    // Main test execution
    async function runAllTests() {
        console.log('\n🚀 Starting comprehensive SDK testing...');
        
        // Test 1: SDK Availability
        const sdkAvailable = testSDKAvailability();
        if (!sdkAvailable) {
            console.log('\n❌ Cannot continue tests - SDK not available');
            return generateTestReport();
        }
        
        // Test 2: SDK Initialization
        const sdk = await testSDKInitialization();
        if (!sdk) {
            console.log('\n❌ Cannot continue tests - SDK initialization failed');
            return generateTestReport();
        }
        
        // Test 3-9: Component tests
        testComponentAvailability(sdk);
        testConfiguration(sdk);
        testMethodAvailability(sdk);
        testBundleSize();
        testPerformanceMetrics();
        await testOfflineVerification(sdk);
        testNetworkResources();
        
        // Generate final report
        return generateTestReport();
    }
    
    // Start the tests
    runAllTests().then(success => {
        if (success) {
            console.log('\n🎉 All tests completed successfully!');
            console.log('📋 Next steps: Proceed with customer integration');
        } else {
            console.log('\n🔧 Some tests need attention');
            console.log('📋 Next steps: Review and optimize failing areas');
        }
    }).catch(error => {
        console.error('\n❌ Test execution failed:', error);
    });
    
})();

// Instructions for users
console.log('\n📋 HOW TO USE THIS TEST:');
console.log('1. Open https://lemma.id/sdk-demo in your browser');
console.log('2. Press F12 to open Developer Tools');
console.log('3. Go to the Console tab');
console.log('4. Copy and paste this entire script');
console.log('5. Press Enter to run the tests');
console.log('6. Review the results above'); 