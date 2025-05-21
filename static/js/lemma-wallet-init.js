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