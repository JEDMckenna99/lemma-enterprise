class LemmaWidget {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.wallet = new LemmaWallet();
        this.init();
    }

    async init() {
        await this.wallet.init();
        this.render();
        this.attachEventListeners();
    }

    render() {
        this.container.innerHTML = `
            <div class="lemma-widget">
                <div class="lemma-widget-buttons">
                    <button class="lemma-button prove-button">Prove Lemma</button>
                    <button class="lemma-button show-button">Show Lemma</button>
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
                
                .show-button {
                    background-color: white;
                    color: #6B3FA0;
                    border: 2px solid #6B3FA0;
                }
                
                .show-button:hover {
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

    async getCsrfToken() {
        try {
            // First try to get the token from the cookie
            const cookieToken = document.cookie.split('; ').find(row => row.startsWith('_csrf_token='));
            if (cookieToken) {
                return cookieToken.split('=')[1];
            }

            // If no cookie, fetch a new token
            const response = await fetch('/api/generate-csrf', {
                method: 'GET',
                credentials: 'include'
            });
            
            if (!response.ok) {
                throw new Error('Failed to get CSRF token');
            }
            
            const data = await response.json();
            
            // Wait a bit for the cookie to be set
            await new Promise(resolve => setTimeout(resolve, 100));
            
            // Try to get the token from the cookie again
            const newCookieToken = document.cookie.split('; ').find(row => row.startsWith('_csrf_token='));
            if (newCookieToken) {
                return newCookieToken.split('=')[1];
            }
            
            // If still no cookie, use the token from the response
            return data.csrf_token;
        } catch (error) {
            console.error('Error getting CSRF token:', error);
            throw error;
        }
    }

    generateUserId() {
        // Generate a random user ID
        const randomBytes = new Uint8Array(16);
        window.crypto.getRandomValues(randomBytes);
        return 'user_' + Array.from(randomBytes).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    attachEventListeners() {
        const proveButton = this.container.querySelector('.prove-button');
        const showButton = this.container.querySelector('.show-button');

        proveButton.addEventListener('click', async () => {
            try {
                proveButton.disabled = true;
                proveButton.textContent = 'Checking...';

                // Check if user already has a lemma
                const credentials = await this.wallet.getAllCredentials();
                if (credentials && credentials.length > 0) {
                    this.showError('You already have a Lemma credential. You can use "Show Lemma" to verify it.');
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
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Failed to start verification');
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
                this.showError('Failed to start verification. Please try again.');
            } finally {
                proveButton.disabled = false;
                proveButton.textContent = 'Prove Lemma';
            }
        });

        showButton.addEventListener('click', async () => {
            try {
                showButton.disabled = true;
                showButton.textContent = 'Checking...';

                // Check for lemma in wallet
                const credentials = await this.wallet.getAllCredentials();
                if (!credentials || credentials.length === 0) {
                    this.showError('No Lemma found in your wallet. Please use "Prove Lemma" to get started.');
                    return;
                }

                // Get CSRF token
                const csrfToken = await this.getCsrfToken();

                // Get a challenge for the presentation
                const challengeResponse = await fetch('/api/generate-challenge');
                const challengeData = await challengeResponse.json();
                const challenge = challengeData.challenge;

                // Create a presentation with the credential
                const presentationResponse = await fetch('/api/presentation', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        credential: credentials[0].credential,
                        challenge: challenge
                    })
                });

                if (!presentationResponse.ok) {
                    const errorData = await presentationResponse.json();
                    throw new Error(errorData.error || 'Failed to create presentation');
                }

                const presentation = await presentationResponse.json();

                // Verify the presentation
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
            } finally {
                showButton.disabled = false;
                showButton.textContent = 'Show Lemma';
            }
        });
    }
} 