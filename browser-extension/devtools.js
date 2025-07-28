/**
 * Lemma DevTools Panel Setup
 * 
 * Creates a DevTools panel for debugging Lemma credential verification
 */

// Create the DevTools panel
chrome.devtools.panels.create(
  'Lemma',
  'icons/lemma-32.png',
  'panel.html',
  function(panel) {
    console.log('Lemma DevTools panel created');
    
    // Panel event handlers
    panel.onShown.addListener(function(panelWindow) {
      console.log('Lemma DevTools panel shown');
      
      // Initialize the panel
      if (panelWindow.initializeLemmaDevTools) {
        panelWindow.initializeLemmaDevTools();
      }
    });
    
    panel.onHidden.addListener(function() {
      console.log('Lemma DevTools panel hidden');
    });
  }
);

// Listen for Lemma-related network requests
chrome.devtools.network.onRequestFinished.addListener(function(request) {
  if (request.request.url.includes('lemma') || 
      request.request.url.includes('verification') ||
      request.request.url.includes('wasm')) {
    
    console.log('Lemma-related network request:', request);
    
    // Send to panel if it exists
    chrome.runtime.sendMessage({
      type: 'LEMMA_NETWORK_REQUEST',
      data: {
        url: request.request.url,
        method: request.request.method,
        statusCode: request.response.status,
        timing: request.time,
        headers: request.response.headers
      }
    });
  }
});

// Console API for debugging
chrome.devtools.inspectedWindow.eval(
  `
  // Inject Lemma debugging utilities
  window.LemmaDevTools = {
    version: '1.0.0',
    
    // Debug flag
    debug: false,
    
    // Event log
    events: [],
    
    // Performance metrics
    metrics: {
      verifications: [],
      totalTime: 0,
      averageTime: 0,
      errorCount: 0
    },
    
    // Log an event
    logEvent: function(type, data) {
      const event = {
        type: type,
        data: data,
        timestamp: Date.now(),
        timeString: new Date().toISOString()
      };
      
      this.events.push(event);
      
      if (this.debug) {
        console.log('[Lemma DevTools]', type, data);
      }
      
      // Send to DevTools panel
      window.postMessage({
        type: 'LEMMA_DEVTOOLS_EVENT',
        event: event
      }, '*');
    },
    
    // Log a verification
    logVerification: function(result, timing) {
      const verification = {
        result: result,
        timing: timing,
        timestamp: Date.now()
      };
      
      this.metrics.verifications.push(verification);
      this.metrics.totalTime += timing;
      this.metrics.averageTime = this.metrics.totalTime / this.metrics.verifications.length;
      
      if (!result.verified) {
        this.metrics.errorCount++;
      }
      
      this.logEvent('VERIFICATION', verification);
    },
    
    // Get all events
    getEvents: function() {
      return this.events;
    },
    
    // Get metrics
    getMetrics: function() {
      return this.metrics;
    },
    
    // Clear events
    clearEvents: function() {
      this.events = [];
      this.metrics = {
        verifications: [],
        totalTime: 0,
        averageTime: 0,
        errorCount: 0
      };
    },
    
    // Enable debug mode
    enableDebug: function() {
      this.debug = true;
      console.log('[Lemma DevTools] Debug mode enabled');
    },
    
    // Disable debug mode
    disableDebug: function() {
      this.debug = false;
      console.log('[Lemma DevTools] Debug mode disabled');
    }
  };
  
  // Hook into existing Lemma SDK if available
  if (window.Lemma || window.LemmaSDK) {
    const lemma = window.Lemma || window.LemmaSDK;
    
    // Hook into verification method
    const originalVerify = lemma.verify;
    if (originalVerify) {
      lemma.verify = function(credentialData) {
        const startTime = performance.now();
        
        window.LemmaDevTools.logEvent('VERIFICATION_START', {
          credentialData: credentialData.substring(0, 100) + '...'
        });
        
        return originalVerify.call(this, credentialData).then(function(result) {
          const endTime = performance.now();
          const timing = endTime - startTime;
          
          window.LemmaDevTools.logVerification(result, timing);
          
          return result;
        }).catch(function(error) {
          const endTime = performance.now();
          const timing = endTime - startTime;
          
          window.LemmaDevTools.logEvent('VERIFICATION_ERROR', {
            error: error.message,
            timing: timing
          });
          
          throw error;
        });
      };
    }
    
    // Hook into event system
    const originalEmit = lemma.emit;
    if (originalEmit) {
      lemma.emit = function(eventType, data) {
        window.LemmaDevTools.logEvent('SDK_EVENT', {
          eventType: eventType,
          data: data
        });
        
        return originalEmit.call(this, eventType, data);
      };
    }
    
    window.LemmaDevTools.logEvent('SDK_DETECTED', {
      version: lemma.version || 'unknown'
    });
  }
  
  console.log('[Lemma DevTools] Debugging utilities injected');
  `,
  function(result, isException) {
    if (isException) {
      console.error('Failed to inject Lemma DevTools:', result);
    } else {
      console.log('Lemma DevTools injected successfully');
    }
  }
); 