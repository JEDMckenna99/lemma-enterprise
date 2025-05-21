/**
 * Lemma Wallet Initializer
 * Include this script on any page that should display the wallet.
 */

document.addEventListener('DOMContentLoaded', function() {
  // Debug logger
  function debugLog(message, obj) {
    console.log("[WALLET-DEBUG]", message, obj || '');
  }
  
  // Check if this page is integrated with Lemma
  const hasLemmaIntegration = 
    // Check if page contains Lemma-specific elements
    document.querySelector('[data-lemma]') !== null ||
    document.querySelector('.lemma-content') !== null ||
    // Or check if the URL contains Lemma-specific paths
    window.location.pathname.includes('/verify') || 
    window.location.pathname.includes('/protected') ||
    // Or check if localStorage contains Lemma credentials (legacy check)
    Object.keys(localStorage).some(key => key.startsWith('lemma_'));
  
  debugLog('Lemma integration detected?', hasLemmaIntegration);
  
  // Automatically set the cookie if page has Lemma integration
  if (hasLemmaIntegration && !document.cookie.includes('lemma_wallet_enabled=true')) {
    debugLog('Enabling wallet via cookie');
    document.cookie = "lemma_wallet_enabled=true; max-age=31536000; path=/; samesite=Lax";
  }
  
  // Check if wallet should be initialized
  const shouldInitWallet = document.cookie.includes('lemma_wallet_enabled=true');
  
  debugLog('Should initialize wallet?', shouldInitWallet);
  
  if (shouldInitWallet) {
    debugLog('Initializing Lemma wallet from lemma-wallet-init.js');
    
    // Ensure lemma-wallet.js is loaded
    const ensureWalletLoaded = function() {
      if (typeof LemmaWallet === 'undefined') {
        // If LemmaWallet class doesn't exist, load the script
        debugLog('Loading Lemma wallet script dynamically');
        const script = document.createElement('script');
        script.src = '/static/js/lemma-wallet.js';
        script.onload = initializeWallet;
        document.head.appendChild(script);
      } else {
        // Script already loaded, initialize wallet
        debugLog('LemmaWallet class found, initializing');
        initializeWallet();
      }
    };
    
    // Initialize the wallet instance
    const initializeWallet = function() {
      // Only initialize if not already done
      if (!window.lemmaWallet) {
        debugLog('Creating new wallet instance');
        try {
          const wallet = new LemmaWallet();
          
          // Store the wallet instance in the window object
          window.lemmaWallet = wallet;
          
          // Check if LemmaWalletUI exists before initializing
          if (typeof LemmaWalletUI === 'undefined') {
            debugLog('LemmaWalletUI not defined, creating mock implementation');
            // Create a mock if not defined to prevent errors
            window.LemmaWalletUI = class LemmaWalletUI {
              constructor(wallet) {
                this.wallet = wallet;
                debugLog('Created mock WalletUI');
              }
              
              init() {
                debugLog('Mock WalletUI initialized');
              }
              
              refreshCredentialList() {
                debugLog('Mock refreshCredentialList called');
              }
            };
          }
          
          const walletUI = new LemmaWalletUI(wallet);
          walletUI.init();
          window.lemmaWalletUI = walletUI;
          
          debugLog('Wallet initialized successfully');
          
          // Add credentials to wallet after initialization
          setTimeout(function() {
            addCredentialsToWallet(wallet);
          }, 500);
        } catch (error) {
          console.error('[WALLET-ERROR] Failed to initialize wallet:', error);
        }
      } else {
        debugLog('Wallet already initialized');
      }
    };
    
    // Add credentials to wallet after initialization
    const addCredentialsToWallet = function(wallet) {
      console.log("Checking for credentials to add to wallet");
      
      // First check for wallet credential directly from template (highest priority)
      const walletCredentialElem = document.getElementById('walletCredential');
      const sessionUserIdElement = document.getElementById('sessionUserId');
      
      let credentialAdded = false;
      
      if (walletCredentialElem && walletCredentialElem.value && sessionUserIdElement && sessionUserIdElement.value) {
        try {
          console.log("Found wallet credential in template field");
          const walletCredentialValue = walletCredentialElem.value.trim();
          
          // Parse the credential
          const walletCredential = JSON.parse(walletCredentialValue);
          
          if (!walletCredential || !walletCredential.credential || !walletCredential.credential.id) {
            console.warn("Invalid wallet credential format in template field");
          } else {
            console.log("Storing wallet credential from template:", walletCredential.credential.id);
            
            // Store in wallet
            wallet.storeCredential(walletCredential)
              .then(() => {
                console.log('Successfully stored wallet credential in wallet:', walletCredential.credential.id);
                credentialAdded = true;
                // Refresh UI if available
                if (window.lemmaWalletUI) {
                  window.lemmaWalletUI.refreshCredentialList();
                }
                
                // Clear from session after successful storage
                // This is done through a hidden form submission to protect against XSS
                const clearForm = document.createElement('form');
                clearForm.method = 'POST';
                clearForm.action = '/api/clear-session-credential';
                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrf_token';
                csrfInput.value = document.querySelector('meta[name="csrf-token"]')?.content || '';
                clearForm.appendChild(csrfInput);
                document.body.appendChild(clearForm);
                clearForm.submit();
              })
              .catch(error => {
                console.error('Failed to store wallet credential:', error);
              });
          }
        } catch (error) {
          console.error('Error processing wallet credential from template:', error);
        }
      }
      
      // Check session credential if wallet credential not found
      if (!credentialAdded) {
        const sessionCredential = document.getElementById('sessionCredential');
        
        if (sessionCredential && sessionCredential.value && sessionUserIdElement && sessionUserIdElement.value) {
          try {
            console.log("Found credential in session field");
            const credentialValue = sessionCredential.value.trim();
            const userId = sessionUserIdElement.value;
            
            // Parse the credential
            let credential = JSON.parse(credentialValue);
            
            if (!credential || !credential.id) {
              console.warn("Invalid credential format in session field");
            } else {
              // Create wallet credential
              const walletCredential = {
                credential: credential,
                wallet_metadata: {
                  added_at: credential.issuanceDate || new Date().toISOString(),
                  holder_id: userId,
                  status: "active",
                  display_name: "Lemma Human Verification",
                  fingerprint: credential.id,
                  key_type: credential.proof?.type || "Ed25519Signature2020",
                  key_format: "raw"
                }
              };
              
              // Store in wallet
              wallet.storeCredential(walletCredential)
                .then(() => {
                  console.log('Successfully stored session credential in wallet:', credential.id);
                  credentialAdded = true;
                  // Refresh UI if available
                  if (window.lemmaWalletUI) {
                    window.lemmaWalletUI.refreshCredentialList();
                  }
                })
                .catch(error => {
                  console.error('Failed to store session credential:', error);
                });
            }
          } catch (error) {
            console.error('Error processing session credential:', error);
          }
        }
      }
      
      // Only check other sources if no credential added yet
      if (!credentialAdded) {
        // Check cookies next
        const cookies = document.cookie.split(';');
        const credentialCookies = cookies.filter(cookie => cookie.trim().startsWith('lemma_credential_'));
        
        if (credentialCookies.length > 0) {
          console.log(`Found ${credentialCookies.length} credentials in cookies`);
          
          credentialCookies.forEach(function(cookie) {
            try {
              const [key, value] = cookie.trim().split('=');
              let walletCredential;
              
              try {
                walletCredential = JSON.parse(decodeURIComponent(value));
              } catch (e) {
                console.error(`Failed to parse cookie value: ${e}`);
                return;
              }
              
              if (!walletCredential) {
                console.warn(`Invalid credential format in cookie ${key} - null or undefined`);
                return;
              }
              
              // Handle lookup type cookie
              if (walletCredential.lookup === true) {
                console.log("Found lookup cookie, will fetch credential from API");
                const userId = walletCredential.user_id;
                if (!userId) {
                  console.warn("Lookup cookie missing user_id");
                  return;
                }
                
                // Fetch credential from API
                fetch(`/api/credential-lookup/${userId}`)
                  .then(response => response.json())
                  .then(credential => {
                    if (!credential || !credential.id) {
                      console.warn("API returned invalid credential");
                      return;
                    }
                    
                    // Create wallet credential
                    const fullWalletCredential = {
                      credential: credential,
                      wallet_metadata: {
                        added_at: credential.issuanceDate || new Date().toISOString(),
                        holder_id: userId,
                        status: "active",
                        display_name: "Lemma Human Verification",
                        fingerprint: credential.id
                      }
                    };
                    
                    // Store in wallet
                    return wallet.storeCredential(fullWalletCredential);
                  })
                  .then(() => {
                    console.log('Stored credential from API lookup');
                    credentialAdded = true;
                    // Refresh UI if available
                    if (window.lemmaWalletUI) {
                      window.lemmaWalletUI.refreshCredentialList();
                    }
                  })
                  .catch(error => {
                    console.error(`Failed to fetch and store credential:`, error);
                  });
                return;
              }
              
              // Handle normal credential cookie
              if (!walletCredential.credential || !walletCredential.credential.id) {
                console.warn(`Invalid credential format in cookie ${key} - missing expected properties`);
                return;
              }
              
              // Store in wallet
              wallet.storeCredential(walletCredential)
                .then(() => {
                  console.log('Stored credential from cookie:', walletCredential.credential.id);
                  // Remove cookie after successful storage
                  document.cookie = `${key}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
                  credentialAdded = true;
                  // Refresh UI if available
                  if (window.lemmaWalletUI) {
                    window.lemmaWalletUI.refreshCredentialList();
                  }
                })
                .catch(error => {
                  console.error(`Failed to store credential from cookie:`, error);
                });
            } catch (error) {
              console.error(`Failed to process credential cookie:`, error);
            }
          });
        }
      }
      
      // Finally check localStorage if still no credential added
      if (!credentialAdded) {
        const storageCredentials = Object.keys(localStorage).filter(key => key.startsWith('lemma_credential_'));
        
        if (storageCredentials.length > 0) {
          console.log(`Found ${storageCredentials.length} credentials in localStorage`);
          
          storageCredentials.forEach(function(key) {
            try {
              const credentialJson = localStorage.getItem(key);
              let credential;
              
              try {
                credential = JSON.parse(credentialJson);
              } catch (e) {
                console.error(`Failed to parse localStorage credential: ${e}`);
                return;
              }
              
              // Check if this is already a wallet credential format
              if (credential && credential.credential && credential.wallet_metadata) {
                console.log('Found wallet-formatted credential in localStorage');
                
                // Store directly
                wallet.storeCredential(credential)
                  .then(() => {
                    console.log('Stored wallet credential from localStorage:', credential.credential.id);
                    // Don't remove from localStorage, might need it again
                    credentialAdded = true;
                    // Refresh UI if available
                    if (window.lemmaWalletUI) {
                      window.lemmaWalletUI.refreshCredentialList();
                    }
                  })
                  .catch(error => {
                    console.error(`Failed to store wallet credential from localStorage:`, error);
                  });
                return;
              }
              
              // Handle raw credential format
              if (!credential || !credential.id) {
                console.warn(`Invalid credential format in localStorage for key ${key}`);
                return;
              }
              
              // Create wallet metadata
              const userId = key.replace('lemma_credential_', '');
              const walletCredential = {
                credential: credential,
                wallet_metadata: {
                  added_at: new Date().toISOString(),
                  holder_id: userId,
                  status: "active",
                  display_name: "Lemma Human Verification",
                  fingerprint: credential.id
                }
              };
              
              // Store in wallet
              wallet.storeCredential(walletCredential)
                .then(() => {
                  console.log('Migrated credential to wallet:', credential.id);
                  // Remove from localStorage after successful migration to avoid duplication
                  localStorage.removeItem(key);
                  credentialAdded = true;
                  // Refresh UI if available
                  if (window.lemmaWalletUI) {
                    window.lemmaWalletUI.refreshCredentialList();
                  }
                })
                .catch(error => {
                  console.error(`Failed to migrate credential ${credential.id}:`, error);
                });
            } catch (error) {
              console.error(`Failed to process credential from localStorage:`, error);
            }
          });
        }
      }
    };
    
    // Start the initialization process
    ensureWalletLoaded();
  }
}); 

/**
 * Lemma Wallet Initialization
 * This script initializes the Lemma wallet and provides functions for verification.
 */

// Initialize the Lemma wallet when the document is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing Lemma wallet...');
    
    // Check if lemmaWallet already exists
    if (window.lemmaWallet) {
        console.log('Lemma wallet already initialized');
        return;
    }
    
    // Create the lemmaWallet object
    window.lemmaWallet = createLemmaWallet();
    console.log('Lemma wallet initialized');
});

/**
 * Create the Lemma wallet instance
 * @returns {Object} The wallet object with methods for managing credentials
 */
function createLemmaWallet() {
    const wallet = {
        // Storage for credentials
        credentialStore: new Map(),
        
        // Initialize the wallet
        init: async function() {
            // Load credentials from localStorage
            await this.loadFromStorage();
            return this;
        },
        
        // Load credentials from localStorage
        loadFromStorage: async function() {
            try {
                // Get all credentials from localStorage
                const credentialKeys = Object.keys(localStorage).filter(key => 
                    key.startsWith('lemma_credential_')
                );
                
                for (const key of credentialKeys) {
                    try {
                        const data = JSON.parse(localStorage.getItem(key));
                        const userId = key.replace('lemma_credential_', '');
                        this.credentialStore.set(userId, data);
                    } catch (e) {
                        console.error('Error parsing credential:', e);
                    }
                }
                
                console.log(`Loaded ${this.credentialStore.size} credentials from storage`);
            } catch (e) {
                console.error('Error loading credentials from storage:', e);
            }
        },
        
        // Get all credentials
        getAllCredentials: async function() {
            const credentials = [];
            for (const [userId, data] of this.credentialStore.entries()) {
                credentials.push(data);
            }
            return credentials;
        },
        
        // Get a credential by ID
        getCredential: async function(id) {
            for (const [userId, data] of this.credentialStore.entries()) {
                if (data.credential && data.credential.id === id) {
                    return data;
                }
            }
            return null;
        },
        
        // Store a credential
        storeCredential: async function(credentialData) {
            if (!credentialData || !credentialData.credential || !credentialData.wallet_metadata) {
                throw new Error('Invalid credential format');
            }
            
            const userId = credentialData.wallet_metadata.holder_id;
            if (!userId) {
                throw new Error('Missing holder ID in credential');
            }
            
            this.credentialStore.set(userId, credentialData);
            
            // Store in localStorage
            localStorage.setItem(`lemma_credential_${userId}`, JSON.stringify(credentialData));
            console.log(`Stored credential for user ${userId}`);
            
            return userId;
        },
        
        // Delete a credential
        deleteCredential: async function(id) {
            let found = false;
            
            // Check all credentials for a match
            for (const [userId, data] of this.credentialStore.entries()) {
                if ((data.credential && data.credential.id === id) || 
                    (data.wallet_metadata && data.wallet_metadata.fingerprint === id)) {
                    this.credentialStore.delete(userId);
                    localStorage.removeItem(`lemma_credential_${userId}`);
                    found = true;
                    console.log(`Deleted credential for user ${userId}`);
                    break;
                }
            }
            
            if (!found) {
                throw new Error('Credential not found');
            }
            
            return true;
        },
        
        // Verify if a user has a valid credential
        checkVerification: async function(userId) {
            try {
                // Get CSRF token
                const csrfResponse = await fetch('/api/generate-csrf-token', {
                    credentials: 'include'
                });
                const csrfData = await csrfResponse.json();
                const csrfToken = csrfData.csrf_token;
                
                // Check if we have a credential for this user
                const credential = this.credentialStore.get(userId);
                
                // Call the verification API
                const response = await fetch('/api/complete-verification-flow', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        user_id: userId,
                        check_only: true,
                        wallet_credential: credential ? credential.credential : null
                    })
                });
                
                const result = await response.json();
                return result;
            } catch (error) {
                console.error('Error checking verification:', error);
                throw error;
            }
        },
        
        // Start the verification flow
        startVerification: async function(userId, options = {}) {
            try {
                // Get CSRF token
                const csrfResponse = await fetch('/api/generate-csrf-token', {
                    credentials: 'include'
                });
                const csrfData = await csrfResponse.json();
                const csrfToken = csrfData.csrf_token;
                
                // Get credential from wallet if available
                const credential = this.credentialStore.get(userId);
                
                // Call the verification API
                const response = await fetch('/api/complete-verification-flow', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        user_id: userId,
                        wallet_credential: credential ? credential.credential : null,
                        callback_url: options.callback_url || null,
                        stripe_session_id: options.session_id || null
                    })
                });
                
                const result = await response.json();
                
                // Handle the response
                if (result.status === 'verified') {
                    console.log('User is verified');
                    
                    // If we need to store a credential
                    if (result.next_step === 'store_credential' && result.store_credential) {
                        await this.storeCredential(result.store_credential);
                    }
                    
                    // Redirect if needed
                    if (result.redirect_url) {
                        window.location.href = result.redirect_url;
                    }
                } 
                else if (result.status === 'initiated') {
                    console.log('Verification initiated');
                    
                    // Redirect to verification URL
                    if (result.verification_url) {
                        window.location.href = result.verification_url;
                    }
                    
                    // Store session ID for later checking
                    if (result.session_id) {
                        localStorage.setItem('lemma_verification_session', result.session_id);
                    }
                }
                
                return result;
            } catch (error) {
                console.error('Error in verification flow:', error);
                throw error;
            }
        },
        
        // Check the status of an ongoing verification
        checkVerificationStatus: async function(userId, sessionId) {
            try {
                // Get CSRF token
                const csrfResponse = await fetch('/api/generate-csrf-token', {
                    credentials: 'include'
                });
                const csrfData = await csrfResponse.json();
                const csrfToken = csrfData.csrf_token;
                
                // Call the verification API
                const response = await fetch('/api/complete-verification-flow', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        user_id: userId,
                        stripe_session_id: sessionId
                    })
                });
                
                const result = await response.json();
                
                // Handle the response
                if (result.status === 'verified') {
                    console.log('Verification completed successfully');
                    
                    // If we need to store a credential
                    if (result.next_step === 'store_credential' && result.store_credential) {
                        await this.storeCredential(result.store_credential);
                    }
                    
                    // Clear session ID
                    localStorage.removeItem('lemma_verification_session');
                    
                    // Redirect if needed
                    if (result.redirect_url) {
                        window.location.href = result.redirect_url;
                    }
                }
                
                return result;
            } catch (error) {
                console.error('Error checking verification status:', error);
                throw error;
            }
        }
    };
    
    // Initialize and return
    return wallet.init();
}

/**
 * Helper function to handle the complete Lemma verification flow
 * Call this from your application to verify a user
 * @param {string} userId - The user ID to verify
 * @param {Object} options - Additional options
 * @returns {Promise<Object>} Verification result
 */
async function verifyWithLemma(userId, options = {}) {
    if (!window.lemmaWallet) {
        console.error('Lemma wallet not initialized');
        throw new Error('Lemma wallet not initialized');
    }
    
    try {
        // First, try to directly access the protected page
        try {
            // Make a GET request to check if the user can access the protected page
            const response = await fetch('/protected', {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Accept': 'text/html'
                }
            });
            
            // If the response is not a redirect, we can go directly to protected
            if (response.ok && !response.redirected) {
                console.log('User is already verified, can go directly to protected page');
                return { 
                    status: 'verified', 
                    message: 'Already verified',
                    redirect_url: '/protected'
                };
            }
        } catch (error) {
            console.warn('Error checking protected access:', error);
            // Continue with normal verification flow
        }
        
        // Check if already verified in wallet
        const checkResult = await window.lemmaWallet.checkVerification(userId);
        
        // If already verified, return the result
        if (checkResult.status === 'verified') {
            console.log('User already verified in wallet');
            return checkResult;
        }
        
        // Start verification process
        return await window.lemmaWallet.startVerification(userId, options);
    } catch (error) {
        console.error('Error in verifyWithLemma:', error);
        throw error;
    }
} 

/**
 * API Widget Integration Functions
 * Use these to integrate with the Lemma API widget
 */

/**
 * Function to be called by the "Prove a Lemma" button in API widgets
 * This is the main entry point for external sites to verify users
 * 
 * @param {Object} options - Configuration options
 * @param {string} options.userId - The user ID to verify (required)
 * @param {string} options.callbackUrl - URL to redirect after verification
 * @param {string} options.elementId - ID of the element to update with status messages
 * @param {Function} options.onSuccess - Callback function when verification succeeds
 * @param {Function} options.onFailure - Callback function when verification fails
 * @returns {Promise<Object>} Verification result
 */
window.proveALemma = async function(options = {}) {
    console.log('Prove a Lemma called with options:', options);
    
    // Validate required parameters
    if (!options.userId) {
        console.error('User ID is required for verification');
        if (options.onFailure) {
            options.onFailure('User ID is required for verification');
        }
        return { status: 'error', message: 'User ID is required' };
    }
    
    // Wait for wallet initialization
    await waitForWalletInitialization();
    
    try {
        // Show status if element ID provided
        if (options.elementId) {
            const element = document.getElementById(options.elementId);
            if (element) {
                element.textContent = 'Verifying...';
            }
        }
        
        // First, try to directly access the protected page
        try {
            // Make a GET request to check if the user can access the protected page
            const response = await fetch('/protected', {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Accept': 'text/html'
                }
            });
            
            // If the response is not a redirect, we can go directly to protected
            if (response.ok && !response.redirected) {
                console.log('User is already verified, going directly to protected page');
                
                // Update status element if provided
                if (options.elementId) {
                    const element = document.getElementById(options.elementId);
                    if (element) {
                        element.textContent = 'Already verified! Redirecting...';
                    }
                }
                
                // Call success callback if provided
                if (options.onSuccess) {
                    options.onSuccess({ status: 'verified', message: 'Already verified' });
                }
                
                // Redirect to protected page
                if (options.shouldRedirect !== false) {
                    window.location.href = '/protected';
                }
                
                return { status: 'verified', message: 'Already verified' };
            }
        } catch (error) {
            console.warn('Error checking protected access:', error);
            // Continue with normal verification flow
        }
        
        // Use the unified verification flow
        const result = await verifyWithLemma(options.userId, {
            callback_url: options.callbackUrl
        });
        
        console.log('Verification result:', result);
        
        // Update status element if provided
        if (options.elementId) {
            const element = document.getElementById(options.elementId);
            if (element) {
                element.textContent = result.message || 'Verification complete';
            }
        }
        
        // Handle result based on status
        if (result.status === 'verified') {
            // Call success callback if provided
            if (options.onSuccess) {
                options.onSuccess(result);
            }
            
            // Redirect if requested and redirect URL provided
            if (result.redirect_url && options.shouldRedirect !== false) {
                window.location.href = result.redirect_url;
            }
        } else if (result.status === 'initiated') {
            // Redirect to verification URL if provided
            if (result.verification_url) {
                window.location.href = result.verification_url;
            }
        } else {
            // Call failure callback if provided
            if (options.onFailure) {
                options.onFailure(result.message || 'Verification failed');
            }
        }
        
        return result;
    } catch (error) {
        console.error('Error in proveALemma:', error);
        
        // Update status element if provided
        if (options.elementId) {
            const element = document.getElementById(options.elementId);
            if (element) {
                element.textContent = 'Verification error: ' + (error.message || 'Unknown error');
            }
        }
        
        // Call failure callback if provided
        if (options.onFailure) {
            options.onFailure(error.message || 'Verification error');
        }
        
        return { status: 'error', message: error.message || 'Verification error' };
    }
};

/**
 * Helper function to wait for the wallet to initialize
 * @param {number} timeout - Maximum time to wait in milliseconds
 * @returns {Promise<Object>} The wallet object
 */
function waitForWalletInitialization(timeout = 5000) {
    return new Promise((resolve) => {
        if (window.lemmaWallet) {
            resolve(window.lemmaWallet);
            return;
        }
        
        const startTime = Date.now();
        const checkInterval = setInterval(() => {
            if (window.lemmaWallet) {
                clearInterval(checkInterval);
                resolve(window.lemmaWallet);
            } else if (Date.now() - startTime > timeout) {
                clearInterval(checkInterval);
                console.warn('Wallet initialization timed out');
                resolve(null);
            }
        }, 100);
    });
} 