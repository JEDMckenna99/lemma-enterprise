/**
 * Lemma Verification Flow - 2025 SaaS Standards
 * Enhanced verification flow with IndexedDB verification, session storage mirroring, and modern UX
 */

class LemmaVerificationFlow {
  constructor() {
    this.version = '2025.1.0';
    this.dbName = 'lemma_credentials_v2';
    this.dbVersion = 2;
    this.sessionStorageKey = 'lemma_verification_state';
    this.lastSyncKey = 'lemma_last_sync';
    this.db = null;
    this.initialized = false;
    this.syncInterval = null;
    
    // Initialize on page load
    this.init();
  }

  /**
   * Initialize the verification flow system
   */
  async init() {
    if (this.initialized) return;
    
    try {
      console.log('[LEMMA-FLOW] Initializing verification flow v' + this.version);
      
      // Initialize IndexedDB
      await this.initIndexedDB();
      
      // Start session storage mirroring
      this.initSessionStorageMirroring();
      
      // Verify credential integrity
      await this.verifyCredentialIntegrity();
      
      // Set up periodic sync
      this.startPeriodicSync();
      
      this.initialized = true;
      console.log('[LEMMA-FLOW] Verification flow initialized successfully');
      
      // Emit ready event
      this.emitEvent('lemma-flow-ready');
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Failed to initialize:', error);
      throw error;
    }
  }

  /**
   * Initialize IndexedDB with enhanced error handling
   */
  async initIndexedDB() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) {
        reject(new Error('IndexedDB not supported in this browser'));
        return;
      }

      const request = indexedDB.open(this.dbName, this.dbVersion);

      request.onerror = () => {
        reject(new Error('Failed to open IndexedDB: ' + request.error));
      };

      request.onsuccess = (event) => {
        this.db = event.target.result;
        console.log('[LEMMA-FLOW] IndexedDB connection established');
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        console.log('[LEMMA-FLOW] Upgrading IndexedDB schema');

        // Create credentials store
        if (!db.objectStoreNames.contains('credentials')) {
          const credentialStore = db.createObjectStore('credentials', { keyPath: 'id' });
          credentialStore.createIndex('holder_id', 'wallet_metadata.holder_id', { unique: false });
          credentialStore.createIndex('fingerprint', 'wallet_metadata.fingerprint', { unique: true });
          credentialStore.createIndex('status', 'wallet_metadata.status', { unique: false });
        }

        // Create sync state store
        if (!db.objectStoreNames.contains('sync_state')) {
          const syncStore = db.createObjectStore('sync_state', { keyPath: 'key' });
        }

        // Create verification log store
        if (!db.objectStoreNames.contains('verification_log')) {
          const logStore = db.createObjectStore('verification_log', { keyPath: 'id', autoIncrement: true });
          logStore.createIndex('timestamp', 'timestamp', { unique: false });
          logStore.createIndex('type', 'type', { unique: false });
        }
      };
    });
  }

  /**
   * Initialize session storage mirroring
   */
  initSessionStorageMirroring() {
    console.log('[LEMMA-FLOW] Initializing session storage mirroring');
    
    // Load existing session state
    this.loadSessionState();
    
    // Set up storage event listeners for cross-tab sync
    window.addEventListener('storage', (event) => {
      if (event.key === this.sessionStorageKey) {
        console.log('[LEMMA-FLOW] Session state changed in another tab');
        this.handleSessionStateChange(event.newValue);
      }
    });

    // Set up page visibility change handling
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        // Page became visible, sync state
        this.syncSessionState();
      }
    });
  }

  /**
   * Load session state from sessionStorage
   */
  loadSessionState() {
    try {
      const sessionData = sessionStorage.getItem(this.sessionStorageKey);
      if (sessionData) {
        const state = JSON.parse(sessionData);
        console.log('[LEMMA-FLOW] Loaded session state:', state);
        return state;
      }
    } catch (error) {
      console.warn('[LEMMA-FLOW] Failed to load session state:', error);
    }
    return null;
  }

  /**
   * Save session state to sessionStorage
   */
  saveSessionState(state) {
    try {
      const stateData = {
        ...state,
        timestamp: Date.now(),
        version: this.version
      };
      
      sessionStorage.setItem(this.sessionStorageKey, JSON.stringify(stateData));
      console.log('[LEMMA-FLOW] Saved session state');
      
      // Also save to IndexedDB for persistence
      this.saveToIndexedDB('sync_state', {
        key: 'last_session_state',
        data: stateData,
        timestamp: Date.now()
      });
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Failed to save session state:', error);
    }
  }

  /**
   * Handle session state changes from other tabs
   */
  handleSessionStateChange(newValue) {
    if (!newValue) return;
    
    try {
      const state = JSON.parse(newValue);
      console.log('[LEMMA-FLOW] Handling session state change:', state);
      
      // Emit event for other components to handle
      this.emitEvent('lemma-session-state-changed', { state });
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Failed to handle session state change:', error);
    }
  }

  /**
   * Sync session state with IndexedDB
   */
  async syncSessionState() {
    try {
      const sessionState = this.loadSessionState();
      const indexedDBState = await this.getFromIndexedDB('sync_state', 'last_session_state');
      
      if (indexedDBState && sessionState) {
        // Compare timestamps and sync the newer state
        if (indexedDBState.timestamp > sessionState.timestamp) {
          // IndexedDB is newer, update session storage
          sessionStorage.setItem(this.sessionStorageKey, JSON.stringify(indexedDBState.data));
          console.log('[LEMMA-FLOW] Synced newer state from IndexedDB to session');
        } else if (sessionState.timestamp > indexedDBState.timestamp) {
          // Session storage is newer, update IndexedDB
          await this.saveToIndexedDB('sync_state', {
            key: 'last_session_state',
            data: sessionState,
            timestamp: sessionState.timestamp
          });
          console.log('[LEMMA-FLOW] Synced newer state from session to IndexedDB');
        }
      }
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Failed to sync session state:', error);
    }
  }

  /**
   * Verify credential integrity across storage systems
   */
  async verifyCredentialIntegrity() {
    try {
      console.log('[LEMMA-FLOW] Verifying credential integrity');
      
      // Get credentials from IndexedDB
      const indexedDBCredentials = await this.getAllCredentialsFromIndexedDB();
      
      // Get credentials from storage (wallet UI removed, using direct storage access)
      let walletCredentials = [];
      try {
        // Check localStorage for credentials
        const storedCredentials = localStorage.getItem('lemma_credentials');
        if (storedCredentials) {
          walletCredentials = JSON.parse(storedCredentials);
          if (!Array.isArray(walletCredentials)) {
            walletCredentials = [walletCredentials];
          }
        }
      } catch (error) {
        console.log('[LEMMA-FLOW] Error accessing stored credentials:', error.message);
      }
      
      // Compare and sync if needed
      if (indexedDBCredentials.length !== walletCredentials.length) {
        console.log('[LEMMA-FLOW] Credential count mismatch, syncing...');
        await this.syncCredentials(indexedDBCredentials, walletCredentials);
      }
      
      // Log verification result
      await this.logVerificationEvent('integrity_check', {
        indexeddb_count: indexedDBCredentials.length,
        wallet_count: walletCredentials.length,
        status: 'completed'
      });
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Credential integrity verification failed:', error);
      await this.logVerificationEvent('integrity_check', {
        status: 'failed',
        error: error.message
      });
    }
  }

  /**
   * Get all credentials from IndexedDB
   */
  async getAllCredentialsFromIndexedDB() {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(['credentials'], 'readonly');
      const store = transaction.objectStore('credentials');
      const request = store.getAll();

      request.onsuccess = () => {
        resolve(request.result || []);
      };

      request.onerror = () => {
        reject(new Error('Failed to get credentials from IndexedDB'));
      };
    });
  }

  /**
   * Save data to IndexedDB
   */
  async saveToIndexedDB(storeName, data) {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([storeName], 'readwrite');
      const store = transaction.objectStore(storeName);
      const request = store.put(data);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(new Error('Failed to save to IndexedDB'));
    });
  }

  /**
   * Get data from IndexedDB
   */
  async getFromIndexedDB(storeName, key) {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([storeName], 'readonly');
      const store = transaction.objectStore(storeName);
      const request = store.get(key);

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new Error('Failed to get from IndexedDB'));
    });
  }

  /**
   * Log verification events
   */
  async logVerificationEvent(type, data) {
    try {
      const logEntry = {
        type,
        data,
        timestamp: Date.now(),
        user_agent: navigator.userAgent,
        url: window.location.href
      };

      await this.saveToIndexedDB('verification_log', logEntry);
      console.log('[LEMMA-FLOW] Logged event:', type, data);
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Failed to log event:', error);
    }
  }

  /**
   * Sync credentials between storage systems
   */
  async syncCredentials(indexedDBCredentials, walletCredentials) {
    try {
      console.log('[LEMMA-FLOW] Syncing credentials between storage systems');
      
      // Create a map of existing credentials by fingerprint
      const indexedDBMap = new Map();
      indexedDBCredentials.forEach(cred => {
        if (cred.wallet_metadata?.fingerprint) {
          indexedDBMap.set(cred.wallet_metadata.fingerprint, cred);
        }
      });

      const walletMap = new Map();
      walletCredentials.forEach(cred => {
        if (cred.wallet_metadata?.fingerprint) {
          walletMap.set(cred.wallet_metadata.fingerprint, cred);
        }
      });

      // Find credentials that need to be synced
      for (const [fingerprint, credential] of walletMap) {
        if (!indexedDBMap.has(fingerprint)) {
          // Credential exists in wallet but not in IndexedDB
          await this.saveToIndexedDB('credentials', credential);
          console.log('[LEMMA-FLOW] Synced credential from wallet to IndexedDB:', fingerprint);
        }
      }

      for (const [fingerprint, credential] of indexedDBMap) {
        if (!walletMap.has(fingerprint)) {
          try {
            // Credential exists in IndexedDB but not in localStorage - sync it
            const existingCredentials = JSON.parse(localStorage.getItem('lemma_credentials') || '[]');
            if (!Array.isArray(existingCredentials)) {
              existingCredentials = [existingCredentials];
            }
            existingCredentials.push(credential);
            localStorage.setItem('lemma_credentials', JSON.stringify(existingCredentials));
            console.log('[LEMMA-FLOW] Synced credential from IndexedDB to localStorage:', fingerprint);
          } catch (error) {
            console.log('[LEMMA-FLOW] Failed to sync credential to localStorage:', error.message);
          }
        }
      }
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Failed to sync credentials:', error);
    }
  }

  /**
   * Start periodic sync process
   */
  startPeriodicSync() {
    // Sync every 30 seconds
    this.syncInterval = setInterval(() => {
      this.syncSessionState();
    }, 30000);

    console.log('[LEMMA-FLOW] Started periodic sync');
  }

  /**
   * Stop periodic sync process
   */
  stopPeriodicSync() {
    if (this.syncInterval) {
      clearInterval(this.syncInterval);
      this.syncInterval = null;
      console.log('[LEMMA-FLOW] Stopped periodic sync');
    }
  }

  /**
   * Enhanced Clear Credential function with 2025 SaaS modal
   */
  async showClearCredentialModal() {
    return new Promise((resolve) => {
      // Create modern modal
      const modal = this.createClearCredentialModal();
      document.body.appendChild(modal);
      
      // Add event listeners
      const confirmBtn = modal.querySelector('#lemma-clear-confirm');
      const cancelBtn = modal.querySelector('#lemma-clear-cancel');
      const closeBtn = modal.querySelector('#lemma-clear-close');
      
      const cleanup = () => {
        modal.remove();
        document.body.style.overflow = '';
      };
      
      confirmBtn.addEventListener('click', async () => {
        try {
          // Show loading state
          confirmBtn.disabled = true;
          confirmBtn.innerHTML = `
            <svg class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Clearing...
          `;
          
          // Perform credential clearing
          await this.clearAllCredentials();
          
          // Show success and redirect
          this.showClearSuccessToast();
          cleanup();
          
          // Redirect after brief delay
          setTimeout(() => {
            window.location.href = '/';
          }, 1500);
          
          resolve(true);
          
        } catch (error) {
          console.error('[LEMMA-FLOW] Failed to clear credentials:', error);
          this.showErrorToast('Failed to clear credentials: ' + error.message);
          cleanup();
          resolve(false);
        }
      });
      
      cancelBtn.addEventListener('click', () => {
        cleanup();
        resolve(false);
      });
      
      closeBtn.addEventListener('click', () => {
        cleanup();
        resolve(false);
      });
      
      // Close on backdrop click
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          cleanup();
          resolve(false);
        }
      });
      
      // Prevent body scroll
      document.body.style.overflow = 'hidden';
      
      // Focus on modal for accessibility
      modal.focus();
    });
  }

  /**
   * Create the modern Clear Credential modal
   */
  createClearCredentialModal() {
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-labelledby', 'lemma-clear-title');
    modal.setAttribute('aria-describedby', 'lemma-clear-description');
    modal.setAttribute('tabindex', '-1');
    
    modal.innerHTML = `
      <div class="bg-white rounded-xl shadow-2xl max-w-md w-full transform transition-all duration-200 scale-95 animate-scale-in">
        <!-- Header -->
        <div class="px-6 py-4 border-b border-gray-200">
          <div class="flex items-center justify-between">
            <div class="flex items-center">
              <div class="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center mr-3">
                <svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                </svg>
              </div>
              <h3 id="lemma-clear-title" class="text-lg font-semibold text-gray-900">Clear Verification</h3>
            </div>
            <button id="lemma-clear-close" class="text-gray-400 hover:text-gray-600 transition-colors">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </button>
          </div>
        </div>
        
        <!-- Body -->
        <div class="px-6 py-4">
          <p id="lemma-clear-description" class="text-gray-600 mb-4">
            Are you sure you want to clear your Lemma verification credential? This action cannot be undone.
          </p>
          
          <div class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
            <div class="flex items-start">
              <svg class="w-5 h-5 text-amber-600 mt-0.5 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
              </svg>
              <div>
                <h4 class="text-sm font-medium text-amber-800 mb-1">What happens when you clear:</h4>
                <ul class="text-sm text-amber-700 space-y-1">
                  <li>• Your verification credential will be deleted from all storage</li>
                  <li>• You'll need to verify again to access protected content</li>
                  <li>• This affects access across all Lemma-enabled sites</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Footer -->
        <div class="px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end space-x-3">
          <button id="lemma-clear-cancel" class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
            Cancel
          </button>
          <button id="lemma-clear-confirm" class="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500">
            Clear Credential
          </button>
        </div>
      </div>
    `;
    
    // Add animation styles
    const style = document.createElement('style');
    style.textContent = `
      @keyframes scale-in {
        from {
          opacity: 0;
          transform: scale(0.95);
        }
        to {
          opacity: 1;
          transform: scale(1);
        }
      }
      .animate-scale-in {
        animation: scale-in 0.2s ease-out;
      }
    `;
    
    if (!document.head.querySelector('style[data-lemma-modal-styles]')) {
      style.setAttribute('data-lemma-modal-styles', 'true');
      document.head.appendChild(style);
    }
    
    return modal;
  }

  /**
   * Clear all credentials from all storage systems
   */
  async clearAllCredentials() {
    console.log('[LEMMA-FLOW] Clearing all credentials');
    
    try {
      // Clear from IndexedDB
      await this.clearIndexedDBCredentials();
      
      // Clear from localStorage
      try {
        localStorage.removeItem('lemma_credentials');
        console.log('[LEMMA-FLOW] Cleared credentials from localStorage');
      } catch (error) {
        console.log('[LEMMA-FLOW] Failed to clear localStorage credentials:', error.message);
      }
      
      // Clear from localStorage
      this.clearLocalStorageCredentials();
      
      // Clear session storage
      sessionStorage.removeItem(this.sessionStorageKey);
      
      // Clear server session
      await this.clearServerSession();
      
      // Log the event
      await this.logVerificationEvent('credentials_cleared', {
        timestamp: Date.now(),
        user_initiated: true
      });
      
      console.log('[LEMMA-FLOW] All credentials cleared successfully');
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Failed to clear credentials:', error);
      throw error;
    }
  }

  /**
   * Clear credentials from IndexedDB
   */
  async clearIndexedDBCredentials() {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(['credentials'], 'readwrite');
      const store = transaction.objectStore('credentials');
      const request = store.clear();

      request.onsuccess = () => {
        console.log('[LEMMA-FLOW] Cleared IndexedDB credentials');
        resolve();
      };

      request.onerror = () => {
        reject(new Error('Failed to clear IndexedDB credentials'));
      };
    });
  }

  /**
   * Clear credentials from localStorage
   */
  clearLocalStorageCredentials() {
    const keys = Object.keys(localStorage);
    keys.forEach(key => {
      if (key.startsWith('lemma_credential_') || key.startsWith('lemma_')) {
        localStorage.removeItem(key);
      }
    });
    console.log('[LEMMA-FLOW] Cleared localStorage credentials');
  }

  /**
   * Clear server session
   */
  async clearServerSession() {
    try {
      const response = await fetch('/api/logout', {
        method: 'POST',
        credentials: 'include'
      });
      
      if (!response.ok) {
        throw new Error('Failed to clear server session');
      }
      
      console.log('[LEMMA-FLOW] Cleared server session');
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Failed to clear server session:', error);
      // Don't throw here, as local clearing is more important
    }
  }

  /**
   * Show success toast notification
   */
  showClearSuccessToast() {
    this.showToast('✅ Verification cleared successfully', 'success');
  }

  /**
   * Show error toast notification
   */
  showErrorToast(message) {
    this.showToast('❌ ' + message, 'error');
  }

  /**
   * Show toast notification
   */
  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg transform transition-all duration-300 translate-x-full ${
      type === 'success' ? 'bg-green-600 text-white' :
      type === 'error' ? 'bg-red-600 text-white' :
      'bg-blue-600 text-white'
    }`;
    
    toast.innerHTML = `
      <div class="flex items-center">
        <span class="mr-2">${message}</span>
        <button onclick="this.parentElement.parentElement.remove()" class="ml-2 text-white hover:text-gray-200">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </div>
    `;
    
    document.body.appendChild(toast);
    
    // Animate in
    setTimeout(() => {
      toast.classList.remove('translate-x-full');
    }, 100);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
      toast.classList.add('translate-x-full');
      setTimeout(() => {
        if (toast.parentElement) {
          toast.remove();
        }
      }, 300);
    }, 5000);
  }

  /**
   * Emit custom events
   */
  emitEvent(eventName, detail = {}) {
    const event = new CustomEvent(eventName, { detail });
    window.dispatchEvent(event);
    console.log('[LEMMA-FLOW] Emitted event:', eventName, detail);
  }

  /**
   * Cleanup resources
   */
  destroy() {
    this.stopPeriodicSync();
    
    if (this.db) {
      this.db.close();
      this.db = null;
    }
    
    this.initialized = false;
    console.log('[LEMMA-FLOW] Verification flow destroyed');
  }

  /**
   * Automatic end-to-end verification test after credential operations
   * This ensures the entire verification chain is working after minting/verification
   */
  async performEndToEndVerificationTest(options = {}) {
    try {
      console.log('[LEMMA-FLOW] Starting automatic end-to-end verification test');
      
      // Default test configuration
      const testConfig = {
        user_id: options.user_id || this.userId,
        credential: options.credential || null,
        force_new_credential: options.force_new_credential || false,
        test_shield_flow: options.test_shield_flow !== false, // Default true
        test_revocation: options.test_revocation !== false, // Default true
        test_background_verification: options.test_background_verification !== false, // Default true
        cleanup_test_data: options.cleanup_test_data !== false, // Default true
        timeout_ms: options.timeout_ms || 10000 // 10 second timeout
      };
      
      // Set timeout for the test
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), testConfig.timeout_ms);
      
      try {
        const response = await fetch('/api/end-to-end-verification-test', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
          },
          credentials: 'same-origin',
          signal: controller.signal,
          body: JSON.stringify(testConfig)
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
          throw new Error(`E2E test failed with status: ${response.status}`);
        }
        
        const testResults = await response.json();
        
        // Log comprehensive test results
        console.group('[LEMMA-FLOW] End-to-End Verification Test Results');
        console.log('📊 Overall Success:', testResults.overall_success);
        console.log('📈 Success Rate:', `${testResults.success_rate}%`);
        console.log('⏱️ Total Test Time:', `${testResults.performance?.total_test_time_ms}ms`);
        console.log('🔍 Tests:', testResults.tests);
        
        if (testResults.errors?.length > 0) {
          console.error('❌ Errors:', testResults.errors);
        }
        
        if (testResults.warnings?.length > 0) {
          console.warn('⚠️ Warnings:', testResults.warnings);
        }
        
        // Show step-by-step validation
        if (testResults.chain_validation?.length > 0) {
          console.log('🔗 Chain Validation:');
          testResults.chain_validation.forEach(step => console.log(`  ${step}`));
        }
        
        console.groupEnd();
        
        // Report to monitoring/analytics if available
        await this.logVerificationEvent('e2e_verification_test', {
          test_id: testResults.test_id,
          overall_success: testResults.overall_success,
          success_rate: testResults.success_rate,
          total_time_ms: testResults.performance?.total_test_time_ms,
          tests_passed: testResults.summary?.tests_passed,
          total_tests: testResults.summary?.total_tests,
          errors_count: testResults.summary?.errors_count,
          warnings_count: testResults.summary?.warnings_count
        });
        
        // Return results for caller to handle
        return {
          success: testResults.overall_success,
          results: testResults,
          recommendation: testResults.summary?.recommendation
        };
        
      } catch (error) {
        clearTimeout(timeoutId);
        
        if (error.name === 'AbortError') {
          console.error('[LEMMA-FLOW] E2E verification test timed out');
          return {
            success: false,
            error: 'Test timed out',
            recommendation: 'API may be slow or unresponsive'
          };
        }
        
        throw error;
      }
      
    } catch (error) {
      console.error('[LEMMA-FLOW] E2E verification test failed:', error);
      
      // Log the failure
      await this.logVerificationEvent('e2e_verification_test', {
        status: 'failed',
        error: error.message,
        user_id: options.user_id
      });
      
      return {
        success: false,
        error: error.message,
        recommendation: 'Manual verification recommended'
      };
    }
  }

  /**
   * Automatic post-credential verification
   * Call this immediately after issuing/storing a credential
   */
  async verifyCredentialAfterMinting(credential, user_id) {
    try {
      console.log('[LEMMA-FLOW] Performing automatic verification after credential minting');
      
      const testResult = await this.performEndToEndVerificationTest({
        user_id: user_id,
        credential: credential,
        force_new_credential: false, // Use the provided credential
        test_shield_flow: true,
        test_revocation: true
      });
      
      if (testResult.success) {
        console.log('✅ Post-minting verification successful - credential chain operational');
        return {
          verified: true,
          credential_operational: true,
          message: 'Credential minted and verified successfully'
        };
      } else {
        console.error('❌ Post-minting verification failed:', testResult.error);
        return {
          verified: false,
          credential_operational: false,
          message: testResult.error || 'Verification chain failed after minting',
          recommendation: testResult.recommendation
        };
      }
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Post-minting verification error:', error);
      return {
        verified: false,
        credential_operational: false,
        message: `Verification error: ${error.message}`
      };
    }
  }

  /**
   * Automatic post-Shield verification
   * Call this after Shield verification completes
   */
  async verifyShieldAfterCompletion(shieldResult) {
    try {
      console.log('[LEMMA-FLOW] Performing automatic verification after Shield completion');
      
      const testResult = await this.performEndToEndVerificationTest({
        user_id: shieldResult.user_id || this.userId,
        test_shield_flow: true,
        test_background_verification: true,
        test_revocation: true
      });
      
      if (testResult.success) {
        console.log('✅ Post-Shield verification successful - complete flow operational');
        return {
          verified: true,
          shield_operational: true,
          message: 'Shield verification and chain operational'
        };
      } else {
        console.error('❌ Post-Shield verification failed:', testResult.error);
        return {
          verified: false,
          shield_operational: false,
          message: testResult.error || 'Shield verification chain failed',
          recommendation: testResult.recommendation
        };
      }
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Post-Shield verification error:', error);
      return {
        verified: false,
        shield_operational: false,
        message: `Shield verification error: ${error.message}`
      };
    }
  }

  /**
   * Enhanced credential storage with automatic verification
   */
  async storeCredentialWithVerification(credential, walletMetadata = {}) {
    try {
      // Store the credential first
      const storageResult = await this.storeInIndexedDB(credential, walletMetadata);
      
      if (storageResult.success) {
        // Automatically verify the stored credential works
        const verificationResult = await this.verifyCredentialAfterMinting(
          credential, 
          walletMetadata.holder_id || this.userId
        );
        
        return {
          ...storageResult,
          post_storage_verification: verificationResult,
          fully_operational: verificationResult.credential_operational
        };
      } else {
        return storageResult;
      }
      
    } catch (error) {
      console.error('[LEMMA-FLOW] Enhanced credential storage failed:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }
}

// Initialize global instance
window.lemmaVerificationFlow = new LemmaVerificationFlow();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = LemmaVerificationFlow;
} 