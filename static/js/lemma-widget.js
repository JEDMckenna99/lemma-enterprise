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

    async getCsrfToken() {
        const response = await fetch('/api/generate-csrf');
        const data = await response.json();
        return data.csrf_token;
    }

    attachEventListeners() {
        const proveButton = this.container.querySelector('.prove-button');
        const showButton = this.container.querySelector('.show-button');

        proveButton.addEventListener('click', async () => {
            try {
                // Check if user already has a lemma
                const credentials = await this.wallet.getAllCredentials();
                if (credentials && credentials.length > 0) {
                    alert('You already have a Lemma credential. You can use "Show Lemma" to verify it.');
                    return;
                }

                // Get CSRF token
                const csrfToken = await this.getCsrfToken();

                // Start verification process
                const response = await fetch('/api/start-verification', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken
                    },
                    body: JSON.stringify({
                        csrf_token: csrfToken
                    })
                });

                const result = await response.json();
                if (result.success) {
                    // Redirect to Stripe verification URL
                    window.location.href = result.url;
                } else {
                    throw new Error(result.error || 'Failed to start verification');
                }
            } catch (error) {
                console.error('Error starting verification:', error);
                alert('An error occurred while starting verification. Please try again.');
            }
        });

        showButton.addEventListener('click', async () => {
            try {
                // Check for lemma in wallet
                const credentials = await this.wallet.getAllCredentials();
                if (!credentials || credentials.length === 0) {
                    alert('No Lemma found in your wallet. Please use "Prove Lemma" to get started.');
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
                        challenge: challenge,
                        csrf_token: csrfToken
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
                        csrf_token: csrfToken,
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
                alert('An error occurred while verifying your Lemma. Please try again.');
            }
        });
    }
} 