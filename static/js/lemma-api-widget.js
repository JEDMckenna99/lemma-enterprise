/**
 * Lemma API Widget
 * 
 * This script provides an easy way for websites to integrate 
 * Lemma human verification into their applications.
 * 
 * Usage:
 * 1. Include this script on your page:
 *    <script src="https://your-lemma-instance.com/static/js/lemma-api-widget.js"></script>
 * 
 * 2. Add a container element where you want the widget to appear:
 *    <div id="lemma-widget-container"></div>
 * 
 * 3. Initialize the widget:
 *    <script>
 *      LemmaWidget.init({
 *        containerId: 'lemma-widget-container',
 *        callbackUrl: '/your-callback-url',
 *        onSuccess: function(result) { console.log('Verification success:', result); }
 *      });
 *    </script>
 */

// Load necessary styles
const lemmaStyle = document.createElement('style');
lemmaStyle.textContent = `
  .lemma-widget {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    max-width: 500px;
    margin: 0 auto;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
    background-color: #fff;
  }
  
  .lemma-header {
    display: flex;
    align-items: center;
    margin-bottom: 15px;
  }
  
  .lemma-logo {
    width: 30px;
    height: 30px;
    background-color: #6B3FA0;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 10px;
    color: white;
    font-weight: bold;
  }
  
  .lemma-title {
    font-size: 18px;
    font-weight: 600;
    color: #333;
  }
  
  .lemma-description {
    font-size: 14px;
    color: #666;
    margin-bottom: 20px;
  }
  
  .lemma-button {
    display: inline-block;
    background-color: #6B3FA0;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .lemma-button:hover {
    background-color: #5A2E8A;
  }
  
  .lemma-status {
    margin-top: 15px;
    font-size: 14px;
    color: #555;
    min-height: 20px;
  }
  
  .lemma-spinner {
    display: none;
    width: 20px;
    height: 20px;
    border: 2px solid rgba(107, 63, 160, 0.3);
    border-radius: 50%;
    border-top-color: #6B3FA0;
    animation: lemma-spin 1s linear infinite;
    margin-right: 10px;
  }
  
  @keyframes lemma-spin {
    to { transform: rotate(360deg); }
  }
`;
document.head.appendChild(lemmaStyle);

// Get the current base URL
function getBaseUrl() {
  return window.location.protocol + '//' + window.location.host;
}

// Get a CSRF token
async function getCsrfToken() {
  try {
    const response = await fetch('/api/generate-csrf');
    const data = await response.json();
    return data.csrf_token;
  } catch (error) {
    console.error('Error getting CSRF token:', error);
    return null;
  }
}

// Main verification function
window.proveALemma = async function(options = {}) {
  const userId = options.userId || ('user_' + Math.random().toString(36).substring(2, 10));
  const callbackUrl = options.callbackUrl || '/protected';
  const elementId = options.elementId;
  const shouldRedirect = options.shouldRedirect !== false;
  const onSuccess = options.onSuccess;
  const onFailure = options.onFailure;
  
  // Update status if element provided
  const updateStatus = (message) => {
    if (elementId) {
      const element = document.getElementById(elementId);
      if (element) element.textContent = message;
    }
  };
  
  try {
    updateStatus('Starting verification...');
    
    // Get CSRF token
    const csrfToken = await getCsrfToken();
    if (!csrfToken) {
      throw new Error('Could not get CSRF token');
    }
    
    // Start verification
    const response = await fetch('/api/start-verification', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken
      },
      body: JSON.stringify({
        user_id: userId,
        return_url: getBaseUrl() + callbackUrl
      })
    });
    
    const result = await response.json();
    
    if (result.error) {
      updateStatus('Verification failed: ' + result.error);
      if (onFailure) onFailure({ message: result.error });
      return { status: 'error', message: result.error };
    }
    
    if (result.credential) {
      // Direct verification successful
      updateStatus('Verification successful!');
      
      // Store credential in wallet if available
      if (window.lemmaWallet && result.credential) {
        try {
          await window.lemmaWallet.storeCredential(result.credential);
          // Clear from session after storing in wallet
          fetch('/api/clear-session-credential', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRF-Token': csrfToken
            }
          });
        } catch (walletError) {
          console.warn('Could not store credential in wallet:', walletError);
        }
      }
      
      if (onSuccess) onSuccess(result);
      
      // Redirect if needed
      if (shouldRedirect) {
        updateStatus('Redirecting to protected content...');
        setTimeout(() => {
          window.location.href = callbackUrl;
        }, 1000);
      }
      
      return { status: 'verified', credential: result.credential };
    } else if (result.url) {
      // Need to redirect to external verification
      updateStatus('Redirecting to verification service...');
      localStorage.setItem('lemma_verification_session', result.id);
      
      // Redirect to verification URL
      if (shouldRedirect) {
        window.location.href = result.url;
      }
      
      return { status: 'initiated', verification_url: result.url, session_id: result.id };
    }
    
    // Unexpected response
    updateStatus('Unexpected verification response');
    if (onFailure) onFailure({ message: 'Unexpected verification response' });
    return { status: 'error', message: 'Unexpected verification response' };
    
  } catch (error) {
    console.error('Verification error:', error);
    updateStatus('Verification error: ' + (error.message || 'Unknown error'));
    if (onFailure) onFailure(error);
    return { status: 'error', message: error.message || 'Unknown error' };
  }
};

// Create the Lemma Widget namespace
window.LemmaWidget = {
  // Default configuration
  config: {
    containerId: 'lemma-widget-container',
    callbackUrl: null,
    onSuccess: null,
    onFailure: null,
    buttonText: 'Verify Human',
    description: 'Verify you are human with Lemma',
    shouldRedirect: true,
    showPresentButton: true // Whether to show the Present Lemma button
  },
  
  // Initialize the widget
  init: function(options = {}) {
    // Merge options with defaults
    this.config = { ...this.config, ...options };
    
    // Render the widget
    this.render();
    
    return this;
  },
  
  // Render the widget
  render: function() {
    const container = document.getElementById(this.config.containerId);
    if (!container) {
      console.error(`Container element with ID "${this.config.containerId}" not found`);
      return;
    }
    
    console.log('[WIDGET-DEBUG] Rendering widget in container:', this.config.containerId);
    
    // Create widget elements
    const widget = document.createElement('div');
    widget.className = 'lemma-widget';
    
    const header = document.createElement('div');
    header.className = 'lemma-header';
    
    const logo = document.createElement('div');
    logo.className = 'lemma-logo';
    logo.textContent = 'L';
    
    const title = document.createElement('div');
    title.className = 'lemma-title';
    title.textContent = 'Human Verification';
    
    header.appendChild(logo);
    header.appendChild(title);
    
    const description = document.createElement('div');
    description.className = 'lemma-description';
    description.textContent = this.config.description;
    
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'lemma-button-container';
    buttonContainer.style.display = 'flex';
    buttonContainer.style.gap = '10px';
    buttonContainer.style.justifyContent = 'center';
    
    const spinner = document.createElement('div');
    spinner.className = 'lemma-spinner';
    spinner.id = 'lemma-spinner';
    
    const proveButton = document.createElement('button');
    proveButton.className = 'lemma-button prove-button';
    proveButton.id = 'lemma-verify-button';
    proveButton.textContent = this.config.buttonText;
    
    // Directly add click handler to the button
    const self = this; // Store reference to 'this' for use in event handler
    proveButton.onclick = function(event) {
      console.log('[WIDGET-DEBUG] Button clicked directly via onclick');
      self.startVerification();
      event.preventDefault();
    };
    
    buttonContainer.appendChild(proveButton);
    
    // Add the Present Lemma button if configured
    if (this.config.showPresentButton) {
      const presentButton = document.createElement('button');
      presentButton.className = 'lemma-button present-button';
      presentButton.id = 'lemma-present-button';
      presentButton.textContent = 'Present Lemma';
      presentButton.style.backgroundColor = 'white';
      presentButton.style.color = '#6B3FA0';
      presentButton.style.border = '2px solid #6B3FA0';
      
      // Directly add click handler
      presentButton.onclick = function(event) {
        console.log('[WIDGET-DEBUG] Present button clicked directly via onclick');
        self.presentLemma();
        event.preventDefault();
      };
      
      buttonContainer.appendChild(presentButton);
    }
    
    const status = document.createElement('div');
    status.className = 'lemma-status';
    status.id = 'lemma-status';
    
    // Assemble the widget
    widget.appendChild(header);
    widget.appendChild(description);
    widget.appendChild(buttonContainer);
    widget.appendChild(status);
    
    // Add widget to container
    container.innerHTML = '';
    container.appendChild(widget);
    
    console.log('[WIDGET-DEBUG] Widget rendered, button event handlers attached');
  },
  
  // Start the verification process
  startVerification: function() {
    const button = document.getElementById('lemma-verify-button');
    const spinner = document.getElementById('lemma-spinner');
    const status = document.getElementById('lemma-status');
    
    if (!button || !spinner || !status) return;
    
    console.log('[WIDGET-DEBUG] Prove a Lemma button clicked');
    
    // Show spinner, disable button
    button.disabled = true;
    spinner.style.display = 'inline-block';
    status.textContent = 'Starting verification...';
    
    // Call the Lemma verification function
    window.proveALemma({
      userId: this.config.userId,
      callbackUrl: this.config.callbackUrl,
      elementId: 'lemma-status',
      shouldRedirect: this.config.shouldRedirect,
      onSuccess: (result) => {
        // Hide spinner
        spinner.style.display = 'none';
        
        // Call the success callback if provided
        if (typeof this.config.onSuccess === 'function') {
          this.config.onSuccess(result);
        }
      },
      onFailure: (error) => {
        // Hide spinner, enable button
        spinner.style.display = 'none';
        button.disabled = false;
        
        // Call the failure callback if provided
        if (typeof this.config.onFailure === 'function') {
          this.config.onFailure(error);
        }
      }
    });
  },
  
  // Present the lemma credential (Flow 5 and 6)
  presentLemma: async function() {
    const button = document.getElementById('lemma-present-button');
    const spinner = document.getElementById('lemma-spinner');
    const status = document.getElementById('lemma-status');
    
    if (!button || !spinner || !status) return;
    
    console.log('[WIDGET-DEBUG] Present Lemma button clicked');
    
    // Show spinner, disable button
    button.disabled = true;
    spinner.style.display = 'inline-block';
    status.textContent = 'Checking credential...';
    
    try {
      // FLOW 5: Check if wallet exists and has a credential
      if (!window.lemmaWallet) {
        console.error('[WIDGET-DEBUG] lemmaWallet not available');
        status.textContent = 'Wallet not available. Please try again.';
        return;
      }
      
      // Get credentials from wallet
      const credentials = await window.lemmaWallet.getAllCredentials();
      if (!credentials || credentials.length === 0) {
        status.textContent = 'No Lemma found in your wallet. Please use "Verify Human" first.';
        return;
      }
      
      // Get the credential
      const credential = credentials[0].credential;
      
      // FLOW 5: First check revocation locally
      try {
        // Check if the credential has been revoked locally
        const isRevoked = await this.checkRevocationStatus(credential);
        if (isRevoked) {
          status.textContent = 'This credential has been revoked. Please obtain a new one.';
          return;
        }
        
        // Get CSRF token
        const csrfToken = await getCsrfToken();
        
        // FLOW 6: Create a presentation
        status.textContent = 'Creating presentation...';
        
        // Get a challenge
        const challengeResponse = await fetch('/api/generate-challenge');
        const challengeData = await challengeResponse.json();
        const challenge = challengeData.challenge;
        
        // Create a presentation
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
        
        // Verify the presentation
        status.textContent = 'Verifying...';
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
        
        // Handle success
        if (verifyResult.success) {
          status.textContent = 'Verification successful! Redirecting...';
          
          // Call success callback if provided
          if (typeof this.config.onSuccess === 'function') {
            this.config.onSuccess(verifyResult);
          }
          
          // Redirect if needed
          if (this.config.shouldRedirect && verifyResult.redirect) {
            setTimeout(() => {
              window.location.href = verifyResult.redirect;
            }, 1000);
          }
        } else {
          throw new Error(verifyResult.error || 'Verification failed');
        }
      } catch (error) {
        console.error('Error verifying credential:', error);
        status.textContent = 'Failed to verify your Lemma: ' + (error.message || 'Unknown error');
        
        // Call failure callback if provided
        if (typeof this.config.onFailure === 'function') {
          this.config.onFailure(error);
        }
      }
    } catch (error) {
      console.error('Error in presentLemma:', error);
      status.textContent = 'Error: ' + (error.message || 'Unknown error');
      
      // Call failure callback if provided
      if (typeof this.config.onFailure === 'function') {
        this.config.onFailure(error);
      }
    } finally {
      // Hide spinner, enable button
      spinner.style.display = 'none';
      button.disabled = false;
    }
  },
  
  // Check if a credential is revoked (part of Flow 5)
  checkRevocationStatus: function(credential) {
    return new Promise(async (resolve, reject) => {
      try {
        console.log('Checking revocation status locally for credential:', credential.id);
        
        // Extract the credential ID
        const credentialId = credential.id;
        if (!credentialId) {
          console.error('No credential ID found');
          resolve(true); // Treat as revoked if no ID
          return;
        }
        
        // Step 1: Check locally cached revocation list first
        const cachedRevocations = localStorage.getItem('lemma_revocation_list');
        if (cachedRevocations) {
          const revocationList = JSON.parse(cachedRevocations);
          if (revocationList.includes(credentialId)) {
            console.log(`Credential ${credentialId} is revoked according to local cache`);
            resolve(true);
            return;
          }
        }
        
        // Step 2: Fetch the latest revocation list from server
        try {
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
            resolve(false); // Assume not revoked if we can't check and not in local cache
            return;
          }
          
          const result = await response.json();
          
          // Update local cache if we got a new revocation list
          if (result.revocation_list) {
            localStorage.setItem('lemma_revocation_list', JSON.stringify(result.revocation_list));
          }
          
          resolve(result.revoked || false);
        } catch (fetchError) {
          console.error('Error fetching revocation status:', fetchError);
          resolve(false);
        }
      } catch (error) {
        console.error('Error checking revocation status:', error);
        // If there's an error in the checking process, prefer to let the user proceed
        // The server-side verification will do a more thorough check
        resolve(false);
      }
    });
  },
};

// Initialize widgets with data attributes on page load
document.addEventListener('DOMContentLoaded', function() {
  // Find all elements with data-lemma-widget attribute
  const widgetElements = document.querySelectorAll('[data-lemma-widget]');
  
  widgetElements.forEach(element => {
    const config = {
      containerId: element.id,
      userId: element.dataset.lemmaUserId,
      callbackUrl: element.dataset.lemmaCallback,
      buttonText: element.dataset.lemmaButtonText,
      description: element.dataset.lemmaDescription,
      shouldRedirect: element.dataset.lemmaShouldRedirect !== 'false'
    };
    
    // Initialize the widget with the element's data attributes
    LemmaWidget.init(config);
  });
}); 