/**
 * Lemma Wallet Initializer
 * Include this script on any page that should display the wallet.
 */

document.addEventListener('DOMContentLoaded', function() {
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
  
  // Automatically set the cookie if page has Lemma integration
  if (hasLemmaIntegration && !document.cookie.includes('lemma_wallet_enabled=true')) {
    console.log('Lemma integration detected, enabling wallet');
    document.cookie = "lemma_wallet_enabled=true; max-age=31536000; path=/; samesite=Lax";
  }
  
  // Check if wallet should be initialized
  const shouldInitWallet = document.cookie.includes('lemma_wallet_enabled=true');
  
  if (shouldInitWallet) {
    console.log('Initializing Lemma wallet from lemma-wallet-init.js');
    
    // Ensure lemma-wallet.js is loaded
    const ensureWalletLoaded = function() {
      if (typeof LemmaWallet === 'undefined') {
        // If LemmaWallet class doesn't exist, load the script
        console.log('Loading Lemma wallet script dynamically');
        const script = document.createElement('script');
        script.src = '/static/js/lemma-wallet.js';
        script.onload = initializeWallet;
        document.head.appendChild(script);
      } else {
        // Script already loaded, initialize wallet
        initializeWallet();
      }
    };
    
    // Initialize the wallet instance
    const initializeWallet = function() {
      // Only initialize if not already done
      if (!window.lemmaWallet) {
        console.log('Creating new wallet instance');
        const wallet = new LemmaWallet();
        const walletUI = new LemmaWalletUI(wallet);
        walletUI.init();
        
        // Store the wallet instances in the window object
        window.lemmaWallet = wallet;
        window.lemmaWalletUI = walletUI;
        
        // Add credentials to wallet after initialization
        setTimeout(function() {
          addCredentialsToWallet(wallet);
        }, 500);
      } else {
        console.log('Wallet already initialized');
      }
    };
    
    // Add any available credentials to the wallet
    const addCredentialsToWallet = function(wallet) {
      console.log("Checking for credentials to add to wallet");
      
      // Check localStorage for credentials (legacy support - migrate them to wallet)
      const storageCredentials = Object.keys(localStorage).filter(key => key.startsWith('lemma_credential_'));
      
      if (storageCredentials.length > 0) {
        console.log(`Found ${storageCredentials.length} credentials in localStorage, migrating to wallet`);
        
        storageCredentials.forEach(function(key) {
          try {
            const credentialJson = localStorage.getItem(key);
            const credential = JSON.parse(credentialJson);
            
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
            
            // Debug log the wallet credential structure
            console.log('Wallet credential structure:', JSON.stringify(walletCredential));
            
            // Store in wallet
            wallet.storeCredential(walletCredential)
              .then(() => {
                console.log('Migrated credential to wallet:', credential.id);
                // Remove from localStorage after successful migration to wallet
                localStorage.removeItem(key);
                // Refresh UI if available
                if (window.lemmaWalletUI) {
                  window.lemmaWalletUI.refreshCredentialList();
                }
              })
              .catch(error => {
                console.error(`Failed to migrate credential ${credential.id}:`, error);
              });
          } catch (error) {
            console.error(`Failed to process credential from key ${key}:`, error);
          }
        });
      }
      
      // Check if there's a credential in a hidden field (from server-side)
      const sessionCredential = document.getElementById('sessionCredential');
      if (sessionCredential && sessionCredential.value) {
        try {
          console.log("Found credential in session field, adding to wallet");
          // Debug the value to see what's being received
          const credentialValue = sessionCredential.value.trim();
          console.log("Raw credential value:", credentialValue);
          
          // Handle possible HTML entity encoding or extra quotes
          let jsonToProcess = credentialValue;
          
          // Try to parse the JSON
          let credential;
          try {
            // The server should have already serialized this properly, so this should work
            credential = JSON.parse(jsonToProcess);
            console.log("Successfully parsed credential JSON directly");
          } catch (jsonError) {
            console.error("Initial JSON parse error:", jsonError);
            
            // Check if the value might have extra quotes or double encoding
            if (jsonToProcess.startsWith('"') && jsonToProcess.endsWith('"')) {
              try {
                // Try to parse the inner string (handle potential double encoding)
                const innerJson = jsonToProcess.slice(1, -1).replace(/\\"/g, '"');
                console.log("Attempting to parse inner JSON:", innerJson);
                credential = JSON.parse(innerJson);
                console.log("Successfully parsed inner JSON");
              } catch (innerError) {
                console.error("Inner JSON parse error:", innerError);
                
                // Last attempt - try with HTML entity decoding
                try {
                  const decodedJson = decodeURIComponent(jsonToProcess).replace(/&quot;/g, '"');
                  console.log("Attempting to parse decoded JSON:", decodedJson);
                  credential = JSON.parse(decodedJson);
                  console.log("Successfully parsed decoded JSON");
                } catch (decodeError) {
                  console.error("Decode JSON parse error:", decodeError);
                  throw new Error("Unable to parse credential JSON");
                }
              }
            } else {
              throw jsonError;
            }
          }
          
          if (!credential || !credential.id) {
            console.warn("Invalid credential format in session field");
            return;
          }
          
          // Get user ID from credential subject or from session field
          let userId = 'unknown';
          if (credential.credentialSubject && credential.credentialSubject.id) {
            userId = credential.credentialSubject.id.replace('did:user:', '');
          } else {
            const sessionUserId = document.getElementById('sessionUserId');
            if (sessionUserId && sessionUserId.value) {
              userId = sessionUserId.value;
            }
          }
          
          // First check if this credential already exists in the wallet
          wallet.getAllCredentials()
            .then(existingCredentials => {
              // Check if credential with same ID or holder already exists
              const exists = existingCredentials.some(cred => 
                cred.credential.id === credential.id || 
                (cred.wallet_metadata && cred.wallet_metadata.holder_id === userId)
              );
              
              if (exists) {
                console.log('Credential already exists in wallet, skipping import');
                return;
              }
              
              // Format for wallet storage
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
              
              // Store in wallet with better error handling
              return wallet.storeCredential(walletCredential)
                .then(() => {
                  console.log('Added credential to wallet from session:', credential.id);
                  // Refresh UI if available
                  if (window.lemmaWalletUI) {
                    window.lemmaWalletUI.refreshCredentialList();
                  }
                })
                .catch(error => {
                  console.error("Failed to add credential from session:", error);
                  // Try again after a delay (might be timing issue)
                  setTimeout(() => {
                    wallet.storeCredential(walletCredential)
                      .then(() => console.log('Successfully added credential on retry'))
                      .catch(retryError => console.error('Failed on retry:', retryError));
                  }, 1000);
                });
            })
            .catch(error => {
              console.error("Error checking existing credentials:", error);
            });
        } catch (error) {
          console.error("Failed to process credential from session:", error);
        }
      }
    };
    
    // Start the initialization process
    ensureWalletLoaded();
  }
}); 