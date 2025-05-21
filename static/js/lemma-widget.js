class LemmaWidget {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.wallet = new LemmaWallet();
        this.csrfToken = null;
        this.init();
    }

    async init() {
        await this.wallet.init();
        // Get initial CSRF token
        try {
            await this.refreshCsrfToken();
        } catch (error) {
            console.error('Error getting initial CSRF token:', error);
        }
        this.render();
        this.attachEventListeners();
    }

    render() {
        this.container.innerHTML = `
            <div class="lemma-widget">
                <div class="lemma-widget-buttons">
                    <button class="lemma-button prove-button">Prove a Lemma</button>
                    <button class="lemma-button present-button">Present Lemma</button>
                </div>
                <div class="lemma-widget-error" style="display: none; color: red; margin-top: 10px; text-align: center;"></div>
            </div>
            <style>
                .lemma-widget {
                    background: white;
                    border-radius: 8px;
                    padding: 15px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    width: 300px;
                    margin: 0 auto;
                }
                
                .lemma-widget-buttons {
                    display: flex;
                    gap: 10px;
                    justify-content: center;
                }
                
                .lemma-button {
                    padding: 8px 16px;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: 600;
                    transition: all 0.2s ease;
                }
                
                .prove-button {
                    background-color: #6B3FA0;
                    color: white;
                }
                
                .prove-button:hover {
                    background-color: #4A2C71;
                }
                
                .present-button {
                    background-color: white;
                    color: #6B3FA0;
                    border: 2px solid #6B3FA0;
                }
                
                .present-button:hover {
                    background-color: #F8F9FA;
                }
            </style>
        `;
    }

    showError(message) {
        const errorDiv = this.container.querySelector('.lemma-widget-error');
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    }

    async refreshCsrfToken() {
        try {
            // Always fetch a fresh token
            const response = await fetch('/api/generate-csrf', {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to get CSRF token');
            }
            
            const data = await response.json();
            this.csrfToken = data.csrf_token;
            return this.csrfToken;
        } catch (error) {
            console.error('Error getting CSRF token:', error);
            throw error;
        }
    }

    async getCsrfToken() {
        // If we don't have a token, get one
        if (!this.csrfToken) {
            return this.refreshCsrfToken();
        }
        return this.csrfToken;
    }

    generateUserId() {
        // Generate a random user ID
        const randomBytes = new Uint8Array(16);
        window.crypto.getRandomValues(randomBytes);
        return 'user_' + Array.from(randomBytes).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    attachEventListeners() {
        const proveButton = this.container.querySelector('.prove-button');
        const presentButton = this.container.querySelector('.present-button');

        proveButton.addEventListener('click', async () => {
            try {
                proveButton.disabled = true;
                proveButton.textContent = 'Checking...';

                // Check if user already has a lemma
                const credentials = await this.wallet.getAllCredentials();
                if (credentials && credentials.length > 0) {
                    this.showError('You already have a Lemma credential. You can use "Present Lemma" to verify it.');
                    return;
                }

                // Get CSRF token
                const csrfToken = await this.getCsrfToken();

                // Generate a user ID
                const userId = this.generateUserId();

                // Start verification process
                const response = await fetch('/api/start-verification', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken
                    },
                    credentials: 'include',
                    body: JSON.stringify({ user_id: userId })
                });

                if (!response.ok) {
                    let errorMessage = 'Failed to start verification';
                    try {
                        const errorData = await response.json();
                        errorMessage = errorData.error || errorData.message || errorMessage;
                        
                        // If we get a CSRF error, refresh the token and try again
                        if (errorMessage.includes('CSRF') || response.status === 400) {
                            await this.refreshCsrfToken();
                            const retryResponse = await fetch('/api/start-verification', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRF-Token': this.csrfToken
                                },
                                credentials: 'include',
                                body: JSON.stringify({ user_id: userId })
                            });
                            
                            if (retryResponse.ok) {
                                const result = await retryResponse.json();
                                if (result.url) {
                                    window.location.href = result.url;
                                    return;
                                }
                            }
                        }
                    } catch (e) {
                        // If response is not JSON, try to get text
                        const text = await response.text();
                        if (text.includes('CSRF')) {
                            errorMessage = 'Security token expired. Please refresh the page and try again.';
                        }
                    }
                    throw new Error(errorMessage);
                }

                const result = await response.json();
                if (result.url) {
                    // Redirect to Stripe verification URL
                    window.location.href = result.url;
                } else {
                    throw new Error('No verification URL provided');
                }
            } catch (error) {
                console.error('Error starting verification:', error);
                this.showError(error.message || 'Failed to start verification. Please try again.');
            } finally {
                proveButton.disabled = false;
                proveButton.textContent = 'Prove a Lemma';
            }
        });

        presentButton.addEventListener('click', async () => {
            try {
                presentButton.disabled = true;
                presentButton.textContent = 'Checking...';

                // Check for lemma in wallet
                const credentials = await this.wallet.getAllCredentials();
                if (!credentials || credentials.length === 0) {
                    this.showError('No Lemma found in your wallet. Please use "Prove a Lemma" to get started.');
                    return;
                }

                // FLOW 5: Create VP and check offline if not revoked
                const credential = credentials[0].credential;
                
                // 1. Check if the credential is revoked locally
                try {
                    // Check revocation locally first (Flow 5)
                    const isRevoked = await this.checkRevocationStatus(credential);
                    if (isRevoked) {
                        this.showError('This credential has been revoked. Please obtain a new one.');
                        return;
                    }
                    
                    // Get CSRF token for the next step
                    const csrfToken = await this.getCsrfToken();
                    
                    // 2. Get a challenge for the presentation
                    const challengeResponse = await fetch('/api/generate-challenge');
                    const challengeData = await challengeResponse.json();
                    const challenge = challengeData.challenge;
                    
                    // 3. Create a presentation with the credential (part of Flow 6)
                    const presentationResponse = await fetch('/api/presentation', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-Token': csrfToken
                        },
                        credentials: 'include',
                        body: JSON.stringify({
                            credential: credential,
                            challenge: challenge
                        })
                    });
                    
                    if (!presentationResponse.ok) {
                        const errorData = await presentationResponse.json();
                        throw new Error(errorData.error || 'Failed to create presentation');
                    }
                    
                    const presentation = await presentationResponse.json();
                    
                    // 4. Verify the presentation
                    const verifyResponse = await fetch('/api/verify-human', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-Token': csrfToken
                        },
                        credentials: 'include',
                        body: JSON.stringify({
                            presentation: presentation,
                            challenge: challenge,
                            user_id: credentials[0].wallet_metadata.holder_id
                        })
                    });
                    
                    if (!verifyResponse.ok) {
                        const errorData = await verifyResponse.json();
                        throw new Error(errorData.error || 'Verification failed');
                    }
                    
                    const verifyResult = await verifyResponse.json();
                    if (verifyResult.success) {
                        // Redirect to protected page
                        window.location.href = verifyResult.redirect || '/protected';
                    } else {
                        throw new Error(verifyResult.error || 'Invalid credential');
                    }
                } catch (error) {
                    console.error('Error verifying credential:', error);
                    this.showError('Failed to verify your Lemma. Please try again.');
                }
            } catch (error) {
                console.error('Error during presentation:', error);
                this.showError('Failed to present your Lemma. Please try again.');
            } finally {
                presentButton.disabled = false;
                presentButton.textContent = 'Present Lemma';
            }
        });
    }

    async checkRevocationStatus(credential) {
        try {
            console.log('Checking revocation status locally for credential:', credential.id);
            
            // Extract the credential ID
            const credentialId = credential.id;
            if (!credentialId) {
                console.error('No credential ID found');
                return true; // Treat as revoked if no ID
            }
            
            // Step 1: Check locally cached revocation list first
            const cachedRevocations = localStorage.getItem('lemma_revocation_list');
            if (cachedRevocations) {
                const revocationList = JSON.parse(cachedRevocations);
                if (revocationList.includes(credentialId)) {
                    console.log(`Credential ${credentialId} is revoked according to local cache`);
                    return true;
                }
            }
            
            // Step 2: Fetch the latest revocation list from server
            const response = await fetch('/api/check-revocation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    credential_id: credentialId
                })
            });
            
            if (!response.ok) {
                // If can't reach server, use the local check result
                console.warn('Could not reach revocation server, using local status only');
                return false; // Assume not revoked if we can't check and not in local cache
            }
            
            const result = await response.json();
            
            // Update local cache if we got a new revocation list
            if (result.revocation_list) {
                localStorage.setItem('lemma_revocation_list', JSON.stringify(result.revocation_list));
            }
            
            return result.revoked || false;
        } catch (error) {
            console.error('Error checking revocation status:', error);
            // If there's an error in the checking process, prefer to let the user proceed
            // The server-side verification will do a more thorough check
            return false;
        }
    }
} 