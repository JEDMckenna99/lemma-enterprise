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
    buttonText: 'Prove a Lemma',
    description: 'Verify you are human with Lemma',
    shouldRedirect: true
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
    
    const spinner = document.createElement('div');
    spinner.className = 'lemma-spinner';
    spinner.id = 'lemma-spinner';
    
    const button = document.createElement('button');
    button.className = 'lemma-button';
    button.id = 'lemma-verify-button';
    button.textContent = this.config.buttonText;
    
    buttonContainer.appendChild(button);
    
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
    
    // Add event listener to button
    button.addEventListener('click', () => this.startVerification());
  },
  
  // Start the verification process
  startVerification: function() {
    const button = document.getElementById('lemma-verify-button');
    const spinner = document.getElementById('lemma-spinner');
    const status = document.getElementById('lemma-status');
    
    if (!button || !spinner || !status) return;
    
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
  }
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