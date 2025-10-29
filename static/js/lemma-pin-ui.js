/**
 * Lemma PIN UI Components
 * Provides user interface for PIN setup, entry, and management
 */

class LemmaPINUI {
    constructor(pinManager) {
        this.pinManager = pinManager;
        this.onUnlock = null;
        this.onLock = null;
    }
    
    /**
     * Show PIN setup modal (first time)
     */
    async showPINSetup(options = {}) {
        return new Promise((resolve, reject) => {
            const modal = this.createPINSetupModal(options);
            document.body.appendChild(modal);
            
            // Focus first input
            setTimeout(() => {
                modal.querySelector('.pin-input').focus();
            }, 100);
            
            // Handle setup
            window.handlePINSetup = async () => {
                try {
                    const pin = this.getPINFromInputs('setup');
                    const confirmPin = this.getPINFromInputs('confirm');
                    
                    if (pin !== confirmPin) {
                        this.showError('setup', 'PINs do not match');
                        return;
                    }
                    
                    await this.pinManager.setupPIN(pin);
                    document.body.removeChild(modal);
                    resolve(true);
                    
                } catch (error) {
                    this.showError('setup', error.message);
                    reject(error);
                }
            };
            
            // Handle cancel
            window.cancelPINSetup = () => {
                document.body.removeChild(modal);
                reject(new Error('PIN setup cancelled'));
            };
        });
    }
    
    /**
     * Show PIN entry modal (unlock wallet)
     */
    async showPINEntry(message = 'Enter your PIN to continue') {
        return new Promise((resolve, reject) => {
            const modal = this.createPINEntryModal(message);
            document.body.appendChild(modal);
            
            // Focus first input
            setTimeout(() => {
                modal.querySelector('.pin-input').focus();
            }, 100);
            
            // Handle unlock
            window.handlePINUnlock = async () => {
                try {
                    const pin = this.getPINFromInputs('entry');
                    const credentials = await this.pinManager.unlock(pin);
                    
                    document.body.removeChild(modal);
                    
                    if (this.onUnlock) {
                        this.onUnlock(credentials);
                    }
                    
                    resolve(credentials);
                    
                } catch (error) {
                    this.showError('entry', error.message);
                    
                    // Clear inputs
                    modal.querySelectorAll('.pin-input').forEach(input => {
                        input.value = '';
                    });
                    modal.querySelector('.pin-input').focus();
                }
            };
            
            // Handle cancel
            window.cancelPINEntry = () => {
                document.body.removeChild(modal);
                reject(new Error('PIN entry cancelled'));
            };
        });
    }
    
    /**
     * Create PIN setup modal HTML
     */
    createPINSetupModal(options) {
        const modal = document.createElement('div');
        modal.className = 'pin-modal-overlay';
        modal.innerHTML = `
            <div class="pin-modal">
                <h2 style="margin: 0 0 8px 0; color: var(--gray-900);">Secure Your Wallet</h2>
                <p style="color: var(--gray-600); margin: 0 0 24px 0;">
                    Create a 4-digit PIN to protect your credentials
                </p>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: var(--gray-700);">
                        Enter PIN
                    </label>
                    <div class="pin-input-group" id="pin-setup-inputs">
                        ${this.createPINInputs('setup')}
                    </div>
                </div>
                
                <div style="margin-bottom: 32px;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: var(--gray-700);">
                        Confirm PIN
                    </label>
                    <div class="pin-input-group" id="pin-confirm-inputs">
                        ${this.createPINInputs('confirm')}
                    </div>
                </div>
                
                <div id="pin-error-setup" class="pin-error" style="display: none;"></div>
                
                <div style="display: flex; gap: 12px;">
                    <button onclick="handlePINSetup()" class="btn-primary" style="flex: 1;">
                        Set PIN
                    </button>
                    ${options.allowSkip ? `
                        <button onclick="cancelPINSetup()" class="btn-secondary">
                            Skip for Now
                        </button>
                    ` : ''}
                </div>
                
                <p style="margin-top: 16px; font-size: 13px; color: var(--gray-500); text-align: center;">
                    Your PIN never leaves your device. It's used to encrypt your wallet locally.
                </p>
            </div>
        `;
        
        this.addPINModalStyles(modal);
        this.setupPINInputBehavior(modal);
        
        return modal;
    }
    
    /**
     * Create PIN entry modal HTML
     */
    createPINEntryModal(message) {
        const modal = document.createElement('div');
        modal.className = 'pin-modal-overlay';
        modal.innerHTML = `
            <div class="pin-modal">
                <h2 style="margin: 0 0 8px 0; color: var(--gray-900);">Unlock Wallet</h2>
                <p style="color: var(--gray-600); margin: 0 0 24px 0;">
                    ${message}
                </p>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: var(--gray-700);">
                        Enter PIN
                    </label>
                    <div class="pin-input-group" id="pin-entry-inputs">
                        ${this.createPINInputs('entry')}
                    </div>
                </div>
                
                <div id="pin-error-entry" class="pin-error" style="display: none;"></div>
                
                <div style="display: flex; gap: 12px;">
                    <button onclick="handlePINUnlock()" class="btn-primary" style="flex: 1;">
                        Unlock
                    </button>
                </div>
                
                <p style="margin-top: 16px; font-size: 13px; color: var(--gray-500); text-align: center;">
                    <a href="#" onclick="requestPINReset(); return false;" style="color: var(--primary);">
                        Forgot PIN?
                    </a>
                </p>
            </div>
        `;
        
        this.addPINModalStyles(modal);
        this.setupPINInputBehavior(modal);
        
        return modal;
    }
    
    /**
     * Create PIN input fields
     */
    createPINInputs(id) {
        let inputs = '';
        for (let i = 0; i < this.pinManager.pinLength; i++) {
            inputs += `
                <input 
                    type="tel" 
                    class="pin-input" 
                    data-group="${id}"
                    data-index="${i}" 
                    maxlength="1" 
                    pattern="[0-9]"
                    inputmode="numeric"
                    autocomplete="off"
                    style="
                        width: 60px;
                        height: 60px;
                        font-size: 24px;
                        text-align: center;
                        border: 2px solid var(--gray-300);
                        border-radius: 8px;
                        margin: 0 4px;
                        font-weight: 600;
                    "
                />
            `;
        }
        return inputs;
    }
    
    /**
     * Get PIN from input fields
     */
    getPINFromInputs(group) {
        const inputs = document.querySelectorAll(`.pin-input[data-group="${group}"]`);
        let pin = '';
        inputs.forEach(input => {
            pin += input.value;
        });
        return pin;
    }
    
    /**
     * Show error message
     */
    showError(group, message) {
        const errorDiv = document.getElementById(`pin-error-${group}`);
        if (errorDiv) {
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
            
            // Hide after 3 seconds
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 3000);
        }
    }
    
    /**
     * Setup PIN input behavior (auto-advance)
     */
    setupPINInputBehavior(modal) {
        const inputs = modal.querySelectorAll('.pin-input');
        
        inputs.forEach((input, index) => {
            // Auto-advance to next input
            input.addEventListener('input', (e) => {
                if (e.target.value.length === 1 && index < inputs.length - 1) {
                    inputs[index + 1].focus();
                }
                
                // Auto-submit on last digit
                if (index === inputs.length - 1 && e.target.value.length === 1) {
                    const group = e.target.dataset.group;
                    if (group === 'entry') {
                        window.handlePINUnlock();
                    } else if (group === 'confirm') {
                        window.handlePINSetup();
                    }
                }
            });
            
            // Backspace to previous input
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Backspace' && e.target.value === '' && index > 0) {
                    inputs[index - 1].focus();
                }
            });
            
            // Only allow digits
            input.addEventListener('beforeinput', (e) => {
                if (e.data && !/^\d$/.test(e.data)) {
                    e.preventDefault();
                }
            });
        });
    }
    
    /**
     * Add modal styles
     */
    addPINModalStyles(modal) {
        const style = document.createElement('style');
        style.textContent = `
            .pin-modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
                backdrop-filter: blur(4px);
            }
            
            .pin-modal {
                background: var(--white);
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                max-width: 400px;
                width: 90%;
                animation: slideIn 0.3s ease;
            }
            
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateY(-20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .pin-input-group {
                display: flex;
                justify-content: center;
                gap: 8px;
            }
            
            .pin-input:focus {
                outline: none;
                border-color: var(--primary);
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            
            .pin-error {
                background: #fee;
                border-left: 4px solid var(--error);
                padding: 12px;
                border-radius: 4px;
                color: var(--error);
                margin-bottom: 16px;
                font-size: 14px;
            }
        `;
        modal.appendChild(style);
    }
}

/**
 * Request PIN Reset (called from "Forgot PIN?" link)
 * SECURITY: Only works if wallet has a credential with the provided email
 */
async function requestPINReset() {
    // Get all credentials to find email
    let userEmail = null;
    let credentialId = null;
    
    try {
        // Try to get email from wallet (if available)
        if (window.lemmaWallet) {
            const allCredentials = await window.lemmaWallet.getAllCredentials();
            
            // Look for credential with email claim
            for (const cred of allCredentials) {
                const claims = cred.claims || cred.credentialSubject || {};
                if (claims.email) {
                    userEmail = claims.email;
                    credentialId = cred.id;
                    break;
                }
            }
        }
    } catch (error) {
        console.warn('Could not auto-detect email from wallet:', error);
    }
    
    // If no email found in wallet, ask user to enter it
    if (!userEmail) {
        userEmail = prompt('Enter the email address associated with your Lemma credential:');
        
        if (!userEmail) return;
        
        if (!userEmail.includes('@') || !userEmail.includes('.')) {
            alert('Please enter a valid email address');
            return;
        }
    } else {
        // Confirm the detected email
        const confirmed = confirm(`Send PIN reset link to ${userEmail}?`);
        if (!confirmed) return;
    }
    
    try {
        const requestBody = { 
            email: userEmail.trim().toLowerCase()
        };
        
        // Include credential ID if available for additional verification
        if (credentialId) {
            requestBody.credential_id = credentialId;
        }
        
        const response = await fetch('/api/wallet/pin-reset/request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`PIN reset email sent to ${userEmail}!\n\nCheck your inbox for a reset link (valid for 1 hour).`);
        } else {
            if (data.error === 'no_credentials') {
                alert(`No Lemma credentials found for ${userEmail}.\n\nYou can only reset the PIN for an email that has active credentials.`);
            } else {
                alert(`Failed to send reset email: ${data.message || 'Unknown error'}`);
            }
        }
    } catch (error) {
        console.error('PIN reset request failed:', error);
        alert('Failed to request PIN reset. Please try again.');
    }
}

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.LemmaPINUI = LemmaPINUI;
    window.requestPINReset = requestPINReset;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaPINUI;
}

