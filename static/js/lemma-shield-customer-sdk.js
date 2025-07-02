/**
 * Lemma Shield SDK - Customer Integration (v2.11.0)
 * Lightweight customer integration wrapper around the main shield widget
 * 
 * This is the customer-facing SDK that provides a clean, simple interface
 * for integrating Lemma Shield into any website.
 */

// Import the main shield widget if not already loaded
if (typeof window.LemmaShield === 'undefined') {
    console.warn('[LemmaSDK] Main LemmaShield not found. Please include lemma-shield-widget.js first.');
}

/**
 * Customer-facing SDK wrapper
 */
class LemmaCustomerSDK {
    constructor(config = {}) {
        // Validate required configuration
        if (!config.apiKey) {
            throw new Error('Lemma API key is required. Get yours at https://lemma.id/onboarding/register');
        }

        // Customer-friendly configuration
        this.config = {
            // Required
            apiKey: config.apiKey,
            
            // API Configuration
            apiBase: config.apiBase || 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com',
            
            // UI Configuration
            containerId: config.containerId || 'lemma-shield',
            theme: config.theme || 'default',
            showBranding: config.showBranding !== false,
            
            // Behavior Configuration
            autoInit: config.autoInit !== false,
            offlineFirst: config.offlineFirst !== false, // Prefer offline verification
            fallbackEnabled: config.fallbackEnabled !== false, // Allow API fallback when offline fails
            
            // Event Callbacks
            onVerified: config.onVerified || (() => {}),
            onError: config.onError || (() => {}),
            onRevoked: config.onRevoked || (() => {}),
            
            // Advanced Options
            debug: config.debug || false,
            retryAttempts: config.retryAttempts || 3,
            timeout: config.timeout || 30000
        };

        // Initialize the main shield widget
        this.shield = null;
        this.initialized = false;

        // Auto-initialize if requested
        if (this.config.autoInit) {
            this.init().catch(error => {
                console.error('[LemmaSDK] Auto-initialization failed:', error);
                if (this.config.onError) {
                    this.config.onError({ error: error.message, source: 'sdk_init' });
                }
            });
        }
    }

    /**
     * Initialize the shield
     */
    async init() {
        if (this.initialized) {
            console.warn('[LemmaSDK] Already initialized');
            return this.shield;
        }

        try {
            // Ensure the main LemmaShield class is available
            if (typeof window.LemmaShield === 'undefined') {
                throw new Error('LemmaShield widget not found. Please include lemma-shield-widget.js');
            }

            // Create the shield instance
            this.shield = new window.LemmaShield({
                ...this.config,
                // Override callbacks to add SDK layer
                onVerified: (result) => this.handleVerified(result),
                onError: (error) => this.handleError(error),
                onRevoked: (result) => this.handleRevoked(result)
            });

            // Wait for shield initialization
            await this.shield.init();

            this.initialized = true;
            this.log('✅ Lemma SDK initialized successfully');

            return this.shield;

        } catch (error) {
            this.log('❌ SDK initialization failed:', error);
            throw error;
        }
    }

    /**
     * Handle verification success with customer-friendly data
     */
    handleVerified(result) {
        this.log('✅ User verified successfully:', result);

        // Provide customer-friendly result
        const customerResult = {
            verified: true,
            timestamp: result.timestamp,
            method: result.method || 'unknown',
            flowType: result.flowType || 'unknown',
            userVerified: true, // Legacy compatibility
            credentialId: result.credential?.id || null
        };

        // Call customer callback
        if (this.config.onVerified) {
            try {
                this.config.onVerified(customerResult);
            } catch (error) {
                console.error('[LemmaSDK] Customer onVerified callback error:', error);
            }
        }

        // Dispatch global event for legacy compatibility
        this.dispatchEvent('lemma:verified', customerResult);
    }

    /**
     * Handle errors with customer-friendly messages
     */
    handleError(error) {
        this.log('❌ Error occurred:', error);

        // Provide customer-friendly error
        const customerError = {
            error: error.error || error.message || 'Unknown error',
            timestamp: error.timestamp || Date.now(),
            source: error.source || 'shield',
            recoverable: error.recoverable !== false // Most errors are recoverable
        };

        // Call customer callback
        if (this.config.onError) {
            try {
                this.config.onError(customerError);
            } catch (cbError) {
                console.error('[LemmaSDK] Customer onError callback error:', cbError);
            }
        }

        // Dispatch global event
        this.dispatchEvent('lemma:error', customerError);
    }

    /**
     * Handle credential revocation
     */
    handleRevoked(result) {
        this.log('🚫 Credentials revoked:', result);

        // Provide customer-friendly result
        const customerResult = {
            revoked: true,
            timestamp: result.timestamp || Date.now(),
            action: result.action || 'credentials_revoked',
            reason: 'Credential verification failed - new verification required'
        };

        // Call customer callback
        if (this.config.onRevoked) {
            try {
                this.config.onRevoked(customerResult);
            } catch (error) {
                console.error('[LemmaSDK] Customer onRevoked callback error:', error);
            }
        }

        // Dispatch global event
        this.dispatchEvent('lemma:revoked', customerResult);
    }

    /**
     * Public API Methods
     */

    /**
     * Force a recheck of credentials
     */
    async recheck() {
        if (!this.shield) {
            throw new Error('SDK not initialized. Call init() first.');
        }
        return await this.shield.forceRecheck();
    }

    /**
     * Clear all stored credentials
     */
    async clearCredentials() {
        if (!this.shield) {
            throw new Error('SDK not initialized. Call init() first.');
        }
        return await this.shield.clearCredentials();
    }

    /**
     * Show the verification shield
     */
    show() {
        if (!this.shield) {
            throw new Error('SDK not initialized. Call init() first.');
        }
        return this.shield.show();
    }

    /**
     * Hide the verification shield
     */
    hide() {
        if (!this.shield) {
            throw new Error('SDK not initialized. Call init() first.');
        }
        return this.shield.hide();
    }

    /**
     * Get verification status
     */
    getStatus() {
        if (!this.shield) {
            return { initialized: false, verified: false };
        }

        return {
            initialized: this.initialized,
            verified: this.shield.state.verified,
            verifying: this.shield.state.verifying,
            lastVerification: this.shield.state.lastVerification
        };
    }

    /**
     * Get performance metrics
     */
    getMetrics() {
        if (!this.shield) {
            return null;
        }
        return this.shield.getMetrics();
    }

    /**
     * Update configuration
     */
    updateConfig(newConfig) {
        Object.assign(this.config, newConfig);
        
        if (this.shield) {
            Object.assign(this.shield.config, newConfig);
        }
    }

    /**
     * Utility Methods
     */

    log(...args) {
        if (this.config.debug) {
            console.log('[LemmaSDK]', new Date().toISOString(), ...args);
        }
    }

    dispatchEvent(eventName, data) {
        try {
            const event = new CustomEvent(eventName, { detail: data });
            document.dispatchEvent(event);
        } catch (error) {
            console.warn('[LemmaSDK] Failed to dispatch event:', eventName, error);
        }
    }

    /**
     * Static factory method for easy initialization
     */
    static init(config) {
        return new LemmaCustomerSDK(config);
    }

    /**
     * Static method to check if Lemma is available
     */
    static isAvailable() {
        return typeof window.LemmaShield !== 'undefined';
    }
}

// Export as global
window.LemmaSDK = LemmaCustomerSDK;

// Legacy compatibility
window.LemmaShield = window.LemmaShield || LemmaCustomerSDK;

// jQuery plugin for legacy compatibility
if (typeof window.$ !== 'undefined') {
    window.$.lemma = function(options) {
        return new LemmaCustomerSDK(options);
    };
}

/**
 * Simple integration helper for basic use cases
 */
window.Lemma = window.Lemma || {
    /**
     * Quick setup method
     */
    protect: function(apiKey, options = {}) {
        const config = {
            apiKey,
            ...options
        };
        
        return new LemmaCustomerSDK(config);
    },

    /**
     * Check if user is verified
     */
    isVerified: function() {
        if (window.lemmaShield) {
            return window.lemmaShield.state.verified;
        }
        return false;
    },

    /**
     * Reset verification
     */
    reset: function() {
        if (window.lemmaShield) {
            return window.lemmaShield.clearCredentials();
        }
    }
};

// Auto-handle verification returns
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('session_id') && urlParams.has('user_id')) {
        console.log('[LemmaSDK] Verification return detected');
    }
});

// Usage examples and documentation
if (typeof window.LemmaSDK !== 'undefined') {
    /**
     * USAGE EXAMPLES:
     * 
     * // Basic setup
     * const lemma = new LemmaSDK({
     *     apiKey: 'your-api-key-here',
     *     onVerified: (result) => {
     *         console.log('User verified!', result);
     *         // Enable protected features
     *     },
     *     onError: (error) => {
     *         console.error('Verification error:', error);
     *     }
     * });
     * 
     * // Quick setup
     * const lemma = Lemma.protect('your-api-key-here', {
     *     onVerified: () => console.log('Verified!')
     * });
     * 
     * // Manual control
     * const lemma = new LemmaSDK({
     *     apiKey: 'your-api-key-here',
     *     autoInit: false
     * });
     * 
     * // Initialize when needed
     * await lemma.init();
     * 
     * // Check status
     * if (lemma.getStatus().verified) {
     *     console.log('User is verified');
     * }
     * 
     * // Force recheck
     * await lemma.recheck();
     * 
     * // Clear and start fresh
     * await lemma.clearCredentials();
     */
} 