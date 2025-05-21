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

// Load the Lemma wallet script
function loadLemmaWallet() {
  if (document.querySelector('script[src*="lemma-wallet-init.js"]')) {
    return Promise.resolve();
  }
  
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://your-lemma-instance.com/static/js/lemma-wallet-init.js';
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

// Create the Lemma Widget namespace
window.LemmaWidget = {
  // Default configuration
  config: {
    containerId: 'lemma-widget-container',
    callbackUrl: null,
    onSuccess: null,
    onFailure: null,
    buttonText: 'Prove a Lemma',
    description: 'Verify you are human with Lemma'
  },
  
  // Initialize the widget
  init: function(options = {}) {
    // Merge options with defaults
    this.config = { ...this.config, ...options };
    
    // Generate a random user ID if not provided
    if (!this.config.userId) {
      this.config.userId = 'user_' + Math.random().toString(36).substring(2, 10);
    }
    
    // Load the Lemma wallet script
    loadLemmaWallet()
      .then(() => this.render())
      .catch(err => console.error('Error loading Lemma wallet:', err));
    
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
    
    // Ensure window.proveALemma is available
    if (typeof window.proveALemma !== 'function') {
      status.textContent = 'Lemma verification not available. Please try again later.';
      button.disabled = false;
      spinner.style.display = 'none';
      return;
    }
    
    // Call the Lemma verification function
    window.proveALemma({
      userId: this.config.userId,
      callbackUrl: this.config.callbackUrl,
      elementId: 'lemma-status',
      shouldRedirect: this.config.shouldRedirect !== false,
      onSuccess: (result) => {
        // Hide spinner
        spinner.style.display = 'none';
        
        // Call the success callback if provided
        if (typeof this.config.onSuccess === 'function') {
          this.config.onSuccess(result);
        }
        
        // Enable button unless redirecting
        if (this.config.shouldRedirect === false) {
          button.disabled = false;
        }
      },
      onFailure: (message) => {
        // Hide spinner, enable button
        spinner.style.display = 'none';
        button.disabled = false;
        
        // Call the failure callback if provided
        if (typeof this.config.onFailure === 'function') {
          this.config.onFailure(message);
        }
      }
    }).catch(error => {
      // Handle any errors
      status.textContent = 'Error: ' + (error.message || 'Unknown error');
      spinner.style.display = 'none';
      button.disabled = false;
      
      if (typeof this.config.onFailure === 'function') {
        this.config.onFailure(error.message || 'Unknown error');
      }
    });
  }
};

// Auto-initialize if data attributes are present
document.addEventListener('DOMContentLoaded', function() {
  const containers = document.querySelectorAll('[data-lemma-widget]');
  containers.forEach(container => {
    const options = {
      containerId: container.id,
      userId: container.getAttribute('data-lemma-user-id'),
      callbackUrl: container.getAttribute('data-lemma-callback'),
      buttonText: container.getAttribute('data-lemma-button-text'),
      description: container.getAttribute('data-lemma-description')
    };
    
    // Filter out undefined values
    Object.keys(options).forEach(key => {
      if (options[key] === null || options[key] === undefined) {
        delete options[key];
      }
    });
    
    // Initialize widget with data attributes
    LemmaWidget.init(options);
  });
}); 