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
      
      // First check for credentials in cookies (new method)
      const cookies = document.cookie.split(';');
      const credentialCookies = cookies.filter(cookie => cookie.trim().startsWith('lemma_credential_'));
      
      if (credentialCookies.length > 0) {
        console.log(`Found ${credentialCookies.length} credentials in cookies`);
        
        credentialCookies.forEach(function(cookie) {
          try {
            const [key, value] = cookie.trim().split('=');
            const walletCredential = JSON.parse(decodeURIComponent(value));
            
            if (!walletCredential || !walletCredential.credential || !walletCredential.credential.id) {
              console.warn(`Invalid credential format in cookie ${key}`);
              return;
            }
            
            // Store in wallet
            wallet.storeCredential(walletCredential)
              .then(() => {
                console.log('Stored credential from cookie:', walletCredential.credential.id);
                // Remove cookie after successful storage
                document.cookie = `${key}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
              })
              .catch(error => {
                console.error(`Failed to store credential from cookie:`, error);
              });
          } catch (error) {
            console.error(`Failed to process credential cookie:`, error);
          }
        });
      }
      
      // Check localStorage for credentials (legacy support)
      const storageCredentials = Object.keys(localStorage).filter(key => key.startsWith('lemma_credential_'));
      
      if (storageCredentials.length > 0) {
        console.log(`Found ${storageCredentials.length} credentials in localStorage`);
        
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
            
            // Store in wallet
            wallet.storeCredential(walletCredential)
              .then(() => {
                console.log('Migrated credential to wallet:', credential.id);
                // Remove from localStorage after successful migration
                localStorage.removeItem(key);
              })
              .catch(error => {
                console.error(`Failed to migrate credential ${credential.id}:`, error);
              });
          } catch (error) {
            console.error(`Failed to process credential from localStorage:`, error);
          }
        });
      }
      
      // Check if there's a credential in a hidden field
      const sessionCredential = document.getElementById('sessionCredential');
      const sessionUserId = document.getElementById('sessionUserId');
      
      if (sessionCredential && sessionCredential.value && sessionUserId && sessionUserId.value) {
        try {
          console.log("Found credential in session field");
          const credentialValue = sessionCredential.value.trim();
          const userId = sessionUserId.value;
          
          // Parse the credential
          let credential = JSON.parse(credentialValue);
          
          if (!credential || !credential.id) {
            console.warn("Invalid credential format in session field");
            return;
          }
          
          // Create wallet credential
          const walletCredential = {
            credential: credential,
            wallet_metadata: {
              added_at: credential.issuanceDate || new Date().toISOString(),
              holder_id: userId,
              status: "active",
              display_name: "Lemma Human Verification",
              fingerprint: credential.id,
              // Add key format information
              key_type: credential.proof?.type || "Ed25519Signature2020",
              key_format: "raw"
            }
          };
          
          // Ensure the proof is properly formatted for Ed25519
          if (credential.proof && credential.proof.jws) {
            // Ensure the JWS is properly padded for base64
            const jws = credential.proof.jws;
            credential.proof.jws = jws.padEnd(Math.ceil(jws.length / 4) * 4, '=');
          }
          
          // Check if credential already exists
          wallet.getAllCredentials()
            .then(existingCredentials => {
              const exists = existingCredentials.some(cred => 
                cred.credential.id === credential.id || 
                (cred.wallet_metadata && cred.wallet_metadata.holder_id === userId)
              );
              
              if (!exists) {
                // Store in wallet
                return wallet.storeCredential(walletCredential);
              } else {
                console.log('Credential already exists in wallet');
              }
            })
            .then(() => {
              if (window.lemmaWalletUI) {
                window.lemmaWalletUI.refreshCredentialList();
              }
            })
            .catch(error => {
              console.error('Failed to process session credential:', error);
            });
        } catch (error) {
          console.error('Failed to process session credential:', error);
        }
      }
    };
    
    // Start the initialization process
    ensureWalletLoaded();
  }
}); 