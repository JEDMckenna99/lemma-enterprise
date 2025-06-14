/**
 * Lemma Wallet SRE Monitoring
 * Client-side error tracking and performance monitoring for wallet operations
 */

class LemmaWalletSRE {
    constructor() {
        this.errorBuffer = [];
        this.performanceBuffer = [];
        this.maxBufferSize = 100;
        this.flushInterval = 30000; // 30 seconds
        this.baseUrl = window.location.origin;
        
        this.init();
    }
    
    init() {
        // Set up error listeners
        this.setupErrorHandlers();
        
        // Set up performance monitoring
        this.setupPerformanceMonitoring();
        
        // Start buffer flushing
        this.startBufferFlush();
        
        console.log('[Lemma SRE] Wallet monitoring initialized');
    }
    
    setupErrorHandlers() {
        // Global error handler
        window.addEventListener('error', (event) => {
            this.recordError({
                type: 'javascript_error',
                message: event.message,
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
                stack: event.error ? event.error.stack : null,
                url: window.location.href
            });
        });
        
        // Unhandled promise rejection handler
        window.addEventListener('unhandledrejection', (event) => {
            this.recordError({
                type: 'promise_rejection',
                message: event.reason ? event.reason.toString() : 'Unhandled promise rejection',
                url: window.location.href
            });
        });
        
        // Wallet-specific error wrapper
        this.wrapWalletMethods();
    }
    
    wrapWalletMethods() {
        // Wait for lemmaWallet to be available
        const checkWallet = () => {
            if (window.lemmaWallet) {
                this.instrumentWalletMethods();
            } else {
                setTimeout(checkWallet, 100);
            }
        };
        checkWallet();
    }
    
    instrumentWalletMethods() {
        const wallet = window.lemmaWallet;
        const sre = this;
        
        // Wrap critical wallet methods
        const methodsToWrap = [
            'getFirstCredential',
            'storeCredential', 
            'createPresentation',
            'verifyCredential',
            'exportCredentials',
            'importCredentials'
        ];
        
        methodsToWrap.forEach(methodName => {
            if (wallet[methodName]) {
                const originalMethod = wallet[methodName];
                wallet[methodName] = function(...args) {
                    const startTime = performance.now();
                    
                    try {
                        const result = originalMethod.apply(this, args);
                        
                        // Handle both sync and async methods
                        if (result && typeof result.then === 'function') {
                            return result.then(
                                (value) => {
                                    sre.recordPerformance(methodName, performance.now() - startTime, true);
                                    return value;
                                },
                                (error) => {
                                    sre.recordError({
                                        type: 'wallet_method_error',
                                        method: methodName,
                                        message: error.message || error.toString(),
                                        stack: error.stack,
                                        url: window.location.href
                                    });
                                    sre.recordPerformance(methodName, performance.now() - startTime, false);
                                    throw error;
                                }
                            );
                        } else {
                            sre.recordPerformance(methodName, performance.now() - startTime, true);
                            return result;
                        }
                    } catch (error) {
                        sre.recordError({
                            type: 'wallet_method_error',
                            method: methodName,
                            message: error.message || error.toString(),
                            stack: error.stack,
                            url: window.location.href
                        });
                        sre.recordPerformance(methodName, performance.now() - startTime, false);
                        throw error;
                    }
                };
            }
        });
        
        console.log('[Lemma SRE] Wallet methods instrumented');
    }
    
    setupPerformanceMonitoring() {
        // Monitor page load performance
        window.addEventListener('load', () => {
            if (performance.getEntriesByType) {
                const navigation = performance.getEntriesByType('navigation')[0];
                if (navigation) {
                    this.recordPerformance('page_load', navigation.loadEventEnd - navigation.startTime, true);
                }
            }
        });
        
        // Monitor wallet script loading
        const walletScripts = document.querySelectorAll('script[src*="lemma-wallet"]');
        walletScripts.forEach(script => {
            script.addEventListener('load', () => {
                this.recordPerformance('wallet_script_load', performance.now(), true);
            });
            script.addEventListener('error', () => {
                this.recordError({
                    type: 'script_load_error',
                    message: 'Failed to load wallet script',
                    url: script.src
                });
            });
        });
    }
    
    recordError(errorData) {
        const error = {
            ...errorData,
            timestamp: Date.now(),
            userAgent: navigator.userAgent,
            url: window.location.href
        };
        
        this.errorBuffer.push(error);
        
        // Keep buffer size manageable
        if (this.errorBuffer.length > this.maxBufferSize) {
            this.errorBuffer.shift();
        }
        
        console.warn('[Lemma SRE] Error recorded:', error);
    }
    
    recordPerformance(operation, duration, success) {
        const performance = {
            operation,
            duration,
            success,
            timestamp: Date.now(),
            url: window.location.href
        };
        
        this.performanceBuffer.push(performance);
        
        // Keep buffer size manageable
        if (this.performanceBuffer.length > this.maxBufferSize) {
            this.performanceBuffer.shift();
        }
    }
    
    startBufferFlush() {
        setInterval(() => {
            this.flushBuffers();
        }, this.flushInterval);
    }
    
    async flushBuffers() {
        if (this.errorBuffer.length === 0 && this.performanceBuffer.length === 0) {
            return;
        }
        
        try {
            // Flush errors
            if (this.errorBuffer.length > 0) {
                const errors = [...this.errorBuffer];
                this.errorBuffer = [];
                
                for (const error of errors) {
                    await this.sendError(error);
                }
            }
            
            // Flush performance data (could be sent to different endpoint)
            if (this.performanceBuffer.length > 0) {
                this.performanceBuffer = [];
                // Performance data could be sent to analytics endpoint
                // For now, just log it
                console.log('[Lemma SRE] Performance data flushed');
            }
            
        } catch (error) {
            console.error('[Lemma SRE] Failed to flush buffers:', error);
        }
    }
    
    async sendError(errorData) {
        try {
            const response = await fetch(`${this.baseUrl}/api/sre/collect/wallet-error`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(errorData)
            });
            
            if (!response.ok) {
                console.warn('[Lemma SRE] Failed to send error data:', response.status);
            }
        } catch (error) {
            console.warn('[Lemma SRE] Network error sending error data:', error);
        }
    }
    
    // Manual error reporting for specific wallet issues
    reportWalletIssue(issueType, details = {}) {
        this.recordError({
            type: 'wallet_issue',
            issueType,
            ...details,
            url: window.location.href
        });
    }
    
    // Get current error stats (for debugging)
    getErrorStats() {
        return {
            errorBufferSize: this.errorBuffer.length,
            performanceBufferSize: this.performanceBuffer.length,
            recentErrors: this.errorBuffer.slice(-5)
        };
    }
}

// Auto-initialize SRE monitoring
if (typeof window !== 'undefined') {
    window.addEventListener('DOMContentLoaded', () => {
        window.lemmaSRE = new LemmaWalletSRE();
    });
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaWalletSRE;
} 