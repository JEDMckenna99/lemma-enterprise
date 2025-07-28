// demo/demo.js - Lemma Offline Verification Demo

import { LemmaVerifier } from './pkg/lemma_crypto.js';

class LemmaDemo {
    constructor() {
        this.verifier = null;
        this.qrScanner = null;
        this.isScanning = false;
        this.networkCalls = 0;
        
        // Demo credentials cache
        this.demoCredentials = {};
        
        this.init();
    }
    
    async init() {
        try {
            console.log('🔄 Initializing Lemma Demo...');
            
            // Show loading
            document.getElementById('loading-wasm').style.display = 'inline-block';
            document.getElementById('wasm-status').textContent = 'Loading WebAssembly...';
            
            // Initialize Lemma verifier
            this.verifier = new LemmaVerifier();
            console.log('✅ Lemma verifier initialized');
            
            // Update UI
            document.getElementById('loading-wasm').style.display = 'none';
            document.getElementById('wasm-status').innerHTML = '✅ <strong>WebAssembly loaded successfully</strong>';
            document.getElementById('scanner-btn').disabled = false;
            document.getElementById('scanner-text').textContent = 'Start Scanner';
            
            // Monitor network status
            this.updateNetworkStatus();
            window.addEventListener('online', () => this.updateNetworkStatus());
            window.addEventListener('offline', () => this.updateNetworkStatus());
            
            // Load demo credentials
            await this.loadDemoCredentials();
            
            // Initialize QR scanner
            await this.initQRScanner();
            
        } catch (error) {
            console.error('❌ Failed to initialize demo:', error);
            document.getElementById('loading-wasm').style.display = 'none';
            document.getElementById('wasm-status').innerHTML = '❌ <strong>Failed to load WebAssembly:</strong> ' + error.message;
            this.showError('Failed to initialize demo: ' + error.message);
        }
    }
    
    async loadDemoCredentials() {
        try {
            const credentialTypes = ['identity', 'ticket', 'package_authenticity', 'qr_code'];
            
            for (const type of credentialTypes) {
                const response = await fetch(`credentials/${type}_credential.json`);
                if (response.ok) {
                    const credential = await response.json();
                    this.demoCredentials[type] = credential;
                    console.log(`📄 Loaded ${type} credential`);
                } else {
                    console.warn(`⚠️  Failed to load ${type} credential`);
                }
            }
            
            console.log('✅ Demo credentials loaded');
        } catch (error) {
            console.error('❌ Failed to load demo credentials:', error);
        }
    }
    
    async initQRScanner() {
        try {
            // Dynamically import QR scanner
            const QrScanner = (await import('https://cdn.jsdelivr.net/npm/qr-scanner@1.4.2/qr-scanner.min.js')).default;
            
            const video = document.getElementById('qr-video');
            this.qrScanner = new QrScanner(
                video,
                result => this.handleQRScan(result.data),
                {
                    highlightScanRegion: true,
                    highlightCodeOutline: true,
                    onDecodeError: (error) => {
                        // Silently ignore decode errors to avoid spam
                    }
                }
            );
            
            console.log('📱 QR scanner initialized');
        } catch (error) {
            console.error('❌ Failed to initialize QR scanner:', error);
            document.getElementById('camera-error').innerHTML = 
                '<strong>QR Scanner Error:</strong> ' + error.message + 
                '<br>Please ensure you have camera permissions and try again.';
            document.getElementById('camera-error').style.display = 'block';
        }
    }
    
    async handleQRScan(qrData) {
        console.log('📱 QR code scanned:', qrData.substring(0, 100) + '...');
        
        // Stop scanner during verification
        if (this.qrScanner && this.isScanning) {
            this.qrScanner.stop();
            this.isScanning = false;
            document.getElementById('scanner-text').textContent = 'Start Scanner';
            document.getElementById('qr-video').style.display = 'none';
        }
        
        // Verify credential
        await this.verifyCredential(qrData);
    }
    
    async verifyCredential(credentialData) {
        try {
            console.log('🔍 Starting verification...');
            
            // Record network calls before verification
            const initialNetworkCalls = this.networkCalls;
            
            // Verify credential using lemma.verify() - NO MODIFICATIONS
            const result = this.verifier.verify(credentialData);
            
            console.log('✅ Verification completed:', result);
            
            // Update network calls count (should be 0 for offline)
            const networkCallsUsed = this.networkCalls - initialNetworkCalls;
            
            this.showResult(result, networkCallsUsed);
            
        } catch (error) {
            console.error('❌ Verification failed:', error);
            this.showError('Verification failed: ' + error.message);
        }
    }
    
    showResult(result, networkCallsUsed = 0) {
        const container = document.getElementById('result-container');
        const resultDiv = document.getElementById('verification-result');
        
        // Update result display
        resultDiv.className = result.verified ? 'result-success' : 'result-error';
        resultDiv.innerHTML = `
            <h2>${result.verified ? '✅ VERIFIED' : '❌ INVALID'}</h2>
            <p>Credential verification ${result.verified ? 'successful' : 'failed'}</p>
            ${result.error ? `<p><strong>Error:</strong> ${result.error}</p>` : ''}
            <p><strong>Confidence:</strong> ${(result.confidence * 100).toFixed(1)}%</p>
            ${result.offline ? '<p><strong>✈️ Verified completely offline</strong></p>' : ''}
        `;
        
        // Update performance stats
        document.getElementById('verification-time').textContent = result.verification_time_us.toFixed(1);
        document.getElementById('network-calls').textContent = networkCallsUsed;
        document.getElementById('credential-type').textContent = result.credential_type;
        document.getElementById('cached-status').textContent = result.cached ? 'Yes' : 'No';
        
        // Show result container
        container.style.display = 'block';
        
        // Scroll to result
        container.scrollIntoView({ behavior: 'smooth' });
    }
    
    showError(message) {
        const container = document.getElementById('result-container');
        const resultDiv = document.getElementById('verification-result');
        
        resultDiv.className = 'result-error';
        resultDiv.innerHTML = `
            <h2>❌ ERROR</h2>
            <p>${message}</p>
        `;
        
        // Reset performance stats
        document.getElementById('verification-time').textContent = '--';
        document.getElementById('network-calls').textContent = '0';
        document.getElementById('credential-type').textContent = '--';
        document.getElementById('cached-status').textContent = '--';
        
        container.style.display = 'block';
        container.scrollIntoView({ behavior: 'smooth' });
    }
    
    updateNetworkStatus() {
        const statusElement = document.getElementById('network-status');
        const statusText = document.getElementById('status-text');
        
        const isOnline = navigator.onLine;
        statusText.textContent = isOnline ? 'ONLINE' : 'OFFLINE (Airplane Mode)';
        statusElement.className = `network-status ${isOnline ? 'online' : 'offline'}`;
    }
    
    toggleScanner() {
        if (!this.qrScanner) {
            this.showError('QR scanner not initialized. Please check camera permissions.');
            return;
        }
        
        if (this.isScanning) {
            this.qrScanner.stop();
            this.isScanning = false;
            document.getElementById('scanner-text').textContent = 'Start Scanner';
            document.getElementById('qr-video').style.display = 'none';
            console.log('📱 Scanner stopped');
        } else {
            this.qrScanner.start();
            this.isScanning = true;
            document.getElementById('scanner-text').textContent = 'Stop Scanner';
            document.getElementById('qr-video').style.display = 'block';
            console.log('📱 Scanner started');
        }
    }
    
    async testCredential(credentialType) {
        if (!this.demoCredentials[credentialType]) {
            this.showError(`Demo credential for ${credentialType} not found`);
            return;
        }
        
        console.log(`🧪 Testing ${credentialType} credential...`);
        
        // Convert credential to JSON string
        const credentialJson = JSON.stringify(this.demoCredentials[credentialType]);
        
        // Verify credential
        await this.verifyCredential(credentialJson);
    }
    
    async testWithDemoCredential() {
        // Test with the first available credential
        const availableTypes = Object.keys(this.demoCredentials);
        if (availableTypes.length === 0) {
            this.showError('No demo credentials available');
            return;
        }
        
        const credentialType = availableTypes[0];
        await this.testCredential(credentialType);
    }
}

// Global functions for HTML buttons
window.toggleScanner = function() {
    if (window.lemmaDemo) {
        window.lemmaDemo.toggleScanner();
    }
};

window.testCredential = function(credentialType) {
    if (window.lemmaDemo) {
        window.lemmaDemo.testCredential(credentialType);
    }
};

window.testWithDemoCredential = function() {
    if (window.lemmaDemo) {
        window.lemmaDemo.testWithDemoCredential();
    }
};

// Initialize demo when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.lemmaDemo = new LemmaDemo();
});

// Override fetch to monitor network calls
const originalFetch = window.fetch;
window.fetch = function(...args) {
    if (window.lemmaDemo) {
        window.lemmaDemo.networkCalls++;
        console.log(`🌐 Network call detected: ${args[0]}`);
    }
    return originalFetch.apply(this, args);
}; 