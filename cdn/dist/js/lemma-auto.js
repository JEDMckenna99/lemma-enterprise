/**
 * Lemma Auto-Integration Script v1.0.0
 * 
 * Zero-config credential verification with automatic QR scanning
 * Simply include this script and add data attributes to your HTML
 * 
 * Usage:
 * <script src="https://cdn.lemma.id/lemma-auto.js" data-api-key="your-api-key"></script>
 * <button data-lemma-verify="qr-scan">Verify Credential</button>
 * <div data-lemma-result></div>
 */

(function() {
    'use strict';
    
    // Configuration from script tag
    const scriptTag = document.currentScript;
    const config = {
        apiKey: scriptTag.getAttribute('data-api-key'),
        autoInit: scriptTag.getAttribute('data-auto-init') !== 'false',
        debug: scriptTag.getAttribute('data-debug') === 'true',
        wasmPath: scriptTag.getAttribute('data-wasm-path') || 'https://cdn.lemma.id/pkg/',
        theme: scriptTag.getAttribute('data-theme') || 'light',
        language: scriptTag.getAttribute('data-language') || 'en',
        retryAttempts: parseInt(scriptTag.getAttribute('data-retry-attempts') || '3'),
        timeout: parseInt(scriptTag.getAttribute('data-timeout') || '10000')
    };
    
    // Global Lemma instance
    window.Lemma = {
        version: '1.0.0',
        config: config,
        verifier: null,
        ready: false,
        qrScanner: null,
        
        // Event system
        events: {},
        
        // API methods
        verify: null,
        scanQR: null,
        init: null,
        
        // State management
        state: {
            isScanning: false,
            isVerifying: false,
            lastResult: null,
            networkCalls: 0,
            cacheHits: 0
        }
    };
    
    // Utility functions
    const utils = {
        log: function(message, ...args) {
            if (config.debug) {
                console.log('[LEMMA-AUTO]', message, ...args);
            }
        },
        
        error: function(message, error) {
            console.error('[LEMMA-AUTO]', message, error);
            utils.emit('error', { message, error });
        },
        
        emit: function(eventName, data) {
            if (window.Lemma.events[eventName]) {
                window.Lemma.events[eventName].forEach(callback => {
                    try {
                        callback(data);
                    } catch (e) {
                        console.error('[LEMMA-AUTO] Event callback error:', e);
                    }
                });
            }
        },
        
        addClass: function(element, className) {
            if (element && element.classList) {
                element.classList.add(className);
            }
        },
        
        removeClass: function(element, className) {
            if (element && element.classList) {
                element.classList.remove(className);
            }
        },
        
        showElement: function(element) {
            if (element) element.style.display = 'block';
        },
        
        hideElement: function(element) {
            if (element) element.style.display = 'none';
        },
        
        async retry(fn, attempts = config.retryAttempts) {
            for (let i = 0; i < attempts; i++) {
                try {
                    return await fn();
                } catch (error) {
                    if (i === attempts - 1) throw error;
                    await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
                }
            }
        }
    };
    
    // CSS injection for automatic styling
    const injectCSS = function() {
        const css = `
            /* Lemma Auto-Integration Styles */
            .lemma-loading {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 2px solid #f3f3f3;
                border-top: 2px solid #3498db;
                border-radius: 50%;
                animation: lemma-spin 1s linear infinite;
            }
            
            @keyframes lemma-spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .lemma-result-success {
                color: #27ae60;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #27ae60;
                border-radius: 5px;
                background: #d5f4e6;
            }
            
            .lemma-result-error {
                color: #e74c3c;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #e74c3c;
                border-radius: 5px;
                background: #fdeaea;
            }
            
            .lemma-qr-scanner {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.8);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
            }
            
            .lemma-qr-scanner video {
                max-width: 90%;
                max-height: 90%;
                border: 2px solid #3498db;
                border-radius: 10px;
            }
            
            .lemma-qr-close {
                position: absolute;
                top: 20px;
                right: 20px;
                background: #e74c3c;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
            }
            
            .lemma-hidden {
                display: none !important;
            }
            
            .lemma-disabled {
                opacity: 0.5;
                pointer-events: none;
            }
        `;
        
        const styleSheet = document.createElement('style');
        styleSheet.textContent = css;
        document.head.appendChild(styleSheet);
    };
    
    // WASM loader with retry and error handling
    const loadWASM = async function() {
        return utils.retry(async () => {
            utils.log('Loading WebAssembly module...');
            
            // Import the WASM module
            const { LemmaVerifier } = await import(config.wasmPath + 'lemma_crypto.js');
            
            // Initialize verifier
            const verifier = new LemmaVerifier();
            
            utils.log('WebAssembly loaded successfully');
            return verifier;
        });
    };
    
    // QR Scanner implementation
    const initQRScanner = async function() {
        try {
            // Dynamically load QR scanner library
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/qr-scanner@1.4.2/qr-scanner.min.js';
            
            await new Promise((resolve, reject) => {
                script.onload = resolve;
                script.onerror = reject;
                document.head.appendChild(script);
            });
            
            utils.log('QR Scanner library loaded');
            return true;
        } catch (error) {
            utils.error('Failed to load QR scanner', error);
            return false;
        }
    };
    
    // Main initialization function
    const init = async function() {
        try {
            utils.log('Initializing Lemma Auto-Integration...');
            
            // Inject CSS
            injectCSS();
            
            // Load WASM module
            window.Lemma.verifier = await loadWASM();
            
            // Initialize QR scanner
            await initQRScanner();
            
            // Set up API methods
            setupAPI();
            
            // Set up DOM event listeners
            setupDOMListeners();
            
            // Mark as ready
            window.Lemma.ready = true;
            
            utils.log('Lemma Auto-Integration initialized successfully');
            utils.emit('ready');
            
        } catch (error) {
            utils.error('Failed to initialize Lemma', error);
            throw error;
        }
    };
    
    // API setup
    const setupAPI = function() {
        // Verify credential
        window.Lemma.verify = async function(credentialData) {
            try {
                window.Lemma.state.isVerifying = true;
                utils.emit('verification-start');
                
                const startTime = performance.now();
                const result = window.Lemma.verifier.verify(credentialData);
                const endTime = performance.now();
                
                const verificationResult = {
                    verified: result.verified,
                    claims: result.claims,
                    timing: {
                        verification: endTime - startTime,
                        unit: 'microseconds'
                    },
                    networkCalls: 0, // Offline verification
                    cacheHit: true
                };
                
                window.Lemma.state.lastResult = verificationResult;
                window.Lemma.state.isVerifying = false;
                
                utils.emit('verification-complete', verificationResult);
                utils.log('Verification completed:', verificationResult);
                
                return verificationResult;
                
            } catch (error) {
                window.Lemma.state.isVerifying = false;
                utils.error('Verification failed', error);
                utils.emit('verification-error', error);
                throw error;
            }
        };
        
        // QR scanning
        window.Lemma.scanQR = async function(options = {}) {
            try {
                if (!window.QrScanner) {
                    throw new Error('QR Scanner not available');
                }
                
                window.Lemma.state.isScanning = true;
                utils.emit('scan-start');
                
                // Create scanner overlay
                const overlay = document.createElement('div');
                overlay.className = 'lemma-qr-scanner';
                overlay.innerHTML = `
                    <video id="lemma-qr-video"></video>
                    <button class="lemma-qr-close" onclick="window.Lemma.stopQRScan()">Close</button>
                `;
                
                document.body.appendChild(overlay);
                
                const video = document.getElementById('lemma-qr-video');
                
                // Initialize scanner
                const scanner = new QrScanner(video, async (result) => {
                    try {
                        utils.log('QR code scanned:', result.data);
                        
                        // Stop scanner
                        scanner.stop();
                        document.body.removeChild(overlay);
                        window.Lemma.state.isScanning = false;
                        
                        // Verify credential
                        const verificationResult = await window.Lemma.verify(result.data);
                        
                        utils.emit('scan-complete', {
                            qrData: result.data,
                            verificationResult: verificationResult
                        });
                        
                        return verificationResult;
                        
                    } catch (error) {
                        utils.error('QR scan verification failed', error);
                        utils.emit('scan-error', error);
                    }
                });
                
                // Start scanner
                await scanner.start();
                
                utils.log('QR scanner started');
                
            } catch (error) {
                window.Lemma.state.isScanning = false;
                utils.error('Failed to start QR scanner', error);
                utils.emit('scan-error', error);
                throw error;
            }
        };
        
        // Stop QR scanning
        window.Lemma.stopQRScan = function() {
            window.Lemma.state.isScanning = false;
            const overlay = document.querySelector('.lemma-qr-scanner');
            if (overlay) {
                document.body.removeChild(overlay);
            }
            utils.emit('scan-stop');
        };
        
        // Event system
        window.Lemma.on = function(eventName, callback) {
            if (!window.Lemma.events[eventName]) {
                window.Lemma.events[eventName] = [];
            }
            window.Lemma.events[eventName].push(callback);
        };
        
        window.Lemma.off = function(eventName, callback) {
            if (window.Lemma.events[eventName]) {
                window.Lemma.events[eventName] = window.Lemma.events[eventName].filter(cb => cb !== callback);
            }
        };
    };
    
    // DOM event listeners for automatic integration
    const setupDOMListeners = function() {
        // Handle verify buttons
        document.addEventListener('click', async function(event) {
            const target = event.target;
            
            // QR scan trigger
            if (target.hasAttribute('data-lemma-verify')) {
                event.preventDefault();
                
                const action = target.getAttribute('data-lemma-verify');
                const resultSelector = target.getAttribute('data-lemma-result');
                
                if (action === 'qr-scan') {
                    try {
                        // Show loading state
                        target.disabled = true;
                        target.innerHTML = '<span class="lemma-loading"></span> Scanning...';
                        
                        // Start QR scan
                        const result = await window.Lemma.scanQR();
                        
                        // Show result
                        if (resultSelector) {
                            const resultElement = document.querySelector(resultSelector);
                            if (resultElement) {
                                showResult(resultElement, result);
                            }
                        }
                        
                    } catch (error) {
                        utils.error('QR scan failed', error);
                        
                        // Show error
                        if (resultSelector) {
                            const resultElement = document.querySelector(resultSelector);
                            if (resultElement) {
                                showError(resultElement, error.message);
                            }
                        }
                        
                    } finally {
                        // Restore button
                        target.disabled = false;
                        target.innerHTML = 'Verify Credential';
                    }
                }
            }
            
            // Direct credential verification
            if (target.hasAttribute('data-lemma-credential')) {
                event.preventDefault();
                
                const credentialData = target.getAttribute('data-lemma-credential');
                const resultSelector = target.getAttribute('data-lemma-result');
                
                try {
                    // Show loading state
                    target.disabled = true;
                    target.innerHTML = '<span class="lemma-loading"></span> Verifying...';
                    
                    // Verify credential
                    const result = await window.Lemma.verify(credentialData);
                    
                    // Show result
                    if (resultSelector) {
                        const resultElement = document.querySelector(resultSelector);
                        if (resultElement) {
                            showResult(resultElement, result);
                        }
                    }
                    
                } catch (error) {
                    utils.error('Verification failed', error);
                    
                    // Show error
                    if (resultSelector) {
                        const resultElement = document.querySelector(resultSelector);
                        if (resultElement) {
                            showError(resultElement, error.message);
                        }
                    }
                    
                } finally {
                    // Restore button
                    target.disabled = false;
                    target.innerHTML = 'Verify Credential';
                }
            }
        });
        
        // Auto-detect QR codes in images
        const qrImages = document.querySelectorAll('[data-lemma-qr-auto]');
        qrImages.forEach(img => {
            img.addEventListener('click', async function() {
                try {
                    // Extract QR code from image (placeholder - would need QR reader library)
                    const qrData = img.getAttribute('data-lemma-qr-data');
                    if (qrData) {
                        const result = await window.Lemma.verify(qrData);
                        
                        const resultSelector = img.getAttribute('data-lemma-result');
                        if (resultSelector) {
                            const resultElement = document.querySelector(resultSelector);
                            if (resultElement) {
                                showResult(resultElement, result);
                            }
                        }
                    }
                } catch (error) {
                    utils.error('Auto QR verification failed', error);
                }
            });
        });
    };
    
    // Result display functions
    const showResult = function(element, result) {
        element.className = result.verified ? 'lemma-result-success' : 'lemma-result-error';
        element.innerHTML = `
            <div>
                <strong>${result.verified ? '✅ VERIFIED' : '❌ INVALID'}</strong>
                <p>Verification ${result.verified ? 'successful' : 'failed'}</p>
                <small>Time: ${result.timing.verification.toFixed(2)}µs | Network calls: ${result.networkCalls}</small>
            </div>
        `;
    };
    
    const showError = function(element, message) {
        element.className = 'lemma-result-error';
        element.innerHTML = `
            <div>
                <strong>❌ ERROR</strong>
                <p>${message}</p>
            </div>
        `;
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            if (config.autoInit) {
                init().catch(error => {
                    utils.error('Auto-initialization failed', error);
                });
            }
        });
    } else {
        if (config.autoInit) {
            init().catch(error => {
                utils.error('Auto-initialization failed', error);
            });
        }
    }
    
    // Expose init function for manual initialization
    window.Lemma.init = init;
    
})(); 