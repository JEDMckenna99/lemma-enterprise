/**
 * Lemma Bot Shield - Simple Implementation
 * =======================================
 * 
 * Simple bot shield that:
 * 1. Checks for existing lemma in background (silent)
 * 2. Shows "Verify a Lemma" widget if no lemma exists
 * 3. Uses working Stripe redirect flow
 * 4. Engine creates + verifies lemma after Stripe success
 * 5. Protects content until verified
 * 
 * Usage: new LemmaBotShield().protect('#protected-content');
 */

class LemmaBotShield {
    constructor(options = {}) {
        this.config = {
            apiKey: options.apiKey || 'demo-integration-key-12345',
            apiBase: options.apiBase || window.location.origin,
            debug: options.debug || false
        };
        
        this.state = {
            checking: false,
            hasLemma: false,
            verifying: false
        };
        
        if (this.config.debug) {
            console.log('🛡️ Lemma Bot Shield initialized');
        }
    }
    
    /**
     * Protect an element with the bot shield
     */
    async protect(elementSelector) {
        const element = document.querySelector(elementSelector);
        if (!element) {
            console.error('❌ Element not found:', elementSelector);
            return;
        }
        
        // Hide protected content immediately
        element.style.display = 'none';
        
        if (this.config.debug) {
            console.log('🛡️ Protecting element:', elementSelector);
        }
        
        // Check for existing lemma in background
        const hasLemma = await this.checkForExistingLemma();
        
        if (hasLemma) {
            // User has lemma - show content immediately
            this.showProtectedContent(element);
        } else {
            // User needs lemma - show verification widget
            this.showVerificationWidget(element);
        }
    }
    
    /**
     * Check for existing lemma in user's wallet (background, silent)
     */
    async checkForExistingLemma() {
        if (this.state.checking) return false;
        
        this.state.checking = true;
        
        try {
            if (this.config.debug) {
                console.log('🔍 Checking for existing lemma in background...');
            }
            
            const response = await fetch(`${this.config.apiBase}/api/sdk/check-credentials`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    backgroundCheck: true,
                    enableRustEngine: true
                })
            });
            
            const result = await response.json();
            
            if (result.success && result.has_credentials) {
                this.state.hasLemma = true;
                
                if (this.config.debug) {
                    console.log('✅ Existing lemma found and verified');
                }
                
                return true;
            }
            
            if (this.config.debug) {
                console.log('ℹ️ No existing lemma found');
            }
            
            return false;
            
        } catch (error) {
            console.error('❌ Error checking for lemma:', error);
            return false;
        } finally {
            this.state.checking = false;
        }
    }
    
    /**
     * Show protected content (user has verified lemma)
     */
    showProtectedContent(element) {
        // Hide the protected element (which should be the main content)
        element.style.display = 'none';
        
        // Show success content if it exists
        const successContent = document.querySelector('#success-content');
        if (successContent) {
            successContent.style.display = 'block';
        } else {
            // Fallback: show the original protected content
            element.style.display = 'block';
        }
        
        if (this.config.debug) {
            console.log('✅ Showing verified user content');
        }
    }
    
    /**
     * Show verification widget (user needs lemma)
     */
    showVerificationWidget(element) {
        // Create verification widget
        const widget = document.createElement('div');
        widget.innerHTML = `
            <div style="
                max-width: 400px;
                margin: 2rem auto;
                padding: 2rem;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                text-align: center;
                border: 2px solid #e5e7eb;
            ">
                <div style="
                    width: 60px;
                    height: 60px;
                    margin: 0 auto 1rem;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                ">🛡️</div>
                
                <h3 style="
                    margin-bottom: 0.5rem;
                    color: #1f2937;
                    font-size: 1.25rem;
                    font-weight: 600;
                ">Protected by Lemma Shield</h3>
                
                <p style="
                    margin-bottom: 1.5rem;
                    color: #6b7280;
                    font-size: 0.875rem;
                ">Verify your identity to access this content</p>
                
                <button id="verify-lemma-btn" style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    padding: 0.75rem 1.5rem;
                    border-radius: 8px;
                    font-size: 1rem;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s;
                    width: 100%;
                " onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(102, 126, 234, 0.4)'" 
                   onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                    Verify a Lemma
                </button>
                
                <p style="
                    margin-top: 1rem;
                    color: #9ca3af;
                    font-size: 0.75rem;
                ">One-time verification • Never see CAPTCHAs again</p>
            </div>
        `;
        
        // Insert widget before the protected element
        element.parentNode.insertBefore(widget, element);
        
        // Add click handler to verification button
        const verifyBtn = widget.querySelector('#verify-lemma-btn');
        verifyBtn.addEventListener('click', () => this.startVerification(element, widget));
        
        if (this.config.debug) {
            console.log('🔧 Showing verification widget');
        }
    }
    
    /**
     * Start the verification process (Stripe redirect)
     */
    async startVerification(protectedElement, widget) {
        if (this.state.verifying) return;
        
        this.state.verifying = true;
        
        // Update button to show loading state
        const verifyBtn = widget.querySelector('#verify-lemma-btn');
        const originalText = verifyBtn.textContent;
        verifyBtn.textContent = 'Starting verification...';
        verifyBtn.disabled = true;
        
        try {
            if (this.config.debug) {
                console.log('🚀 Starting Stripe Identity verification...');
            }
            
            // Start identity verification (this creates Stripe session)
            const response = await fetch(`${this.config.apiBase}/api/sdk/start-identity-verification`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    provider: 'stripe_identity',
                    inline_mode: false, // Use redirect mode (which works!)
                    return_url: window.location.href
                })
            });
            
            const result = await response.json();
            
            if (result.success && result.url) {
                if (this.config.debug) {
                    console.log('✅ Stripe session created, redirecting...');
                }
                
                // Redirect to Stripe Identity (the working flow!)
                window.location.href = result.url;
            } else {
                throw new Error(result.message || 'Failed to start verification');
            }
            
        } catch (error) {
            console.error('❌ Verification failed:', error);
            
            // Reset button
            verifyBtn.textContent = originalText;
            verifyBtn.disabled = false;
            
            // Show error message
            verifyBtn.textContent = 'Verification failed - Try again';
            setTimeout(() => {
                verifyBtn.textContent = originalText;
            }, 3000);
            
        } finally {
            this.state.verifying = false;
        }
    }
}

// Global initialization for easy customer integration
window.LemmaBotShield = LemmaBotShield;

// Auto-initialize if data attributes are present
document.addEventListener('DOMContentLoaded', () => {
    const autoProtect = document.querySelector('[data-lemma-protect]');
    if (autoProtect) {
        const selector = autoProtect.getAttribute('data-lemma-protect');
        new LemmaBotShield({ debug: true }).protect(selector);
    }
});