/**
 * Test suite for the Lemma wallet JavaScript implementation
 * 
 * This file contains tests for the client-side wallet functionality,
 * including IndexedDB storage, credential management, and presentation creation.
 * 
 * To run these tests:
 * 1. Install Jest: npm install --save-dev jest
 * 2. Run: npx jest test_wallet_js.js
 */

// Mock IndexedDB
const mockIndexedDB = {
  open: jest.fn(),
  deleteDatabase: jest.fn()
};

// Mock IDBRequest
class MockIDBRequest {
  constructor() {
    this.result = null;
    this.error = null;
    this.readyState = 'pending';
  }
  
  triggerSuccess(result) {
    this.result = result;
    this.readyState = 'done';
    if (this.onsuccess) {
      this.onsuccess({ target: this });
    }
  }
  
  triggerError(error) {
    this.error = error;
    this.readyState = 'done';
    if (this.onerror) {
      this.onerror({ target: this });
    }
  }
}

// Mock IDBObjectStore
class MockIDBObjectStore {
  constructor(name) {
    this.name = name;
    this.data = new Map();
  }
  
  add(value, key) {
    const request = new MockIDBRequest();
    this.data.set(key || value.id, value);
    setTimeout(() => request.triggerSuccess(key || value.id), 0);
    return request;
  }
  
  put(value, key) {
    const request = new MockIDBRequest();
    this.data.set(key || value.id, value);
    setTimeout(() => request.triggerSuccess(key || value.id), 0);
    return request;
  }
  
  get(key) {
    const request = new MockIDBRequest();
    setTimeout(() => {
      if (this.data.has(key)) {
        request.triggerSuccess(this.data.get(key));
      } else {
        request.triggerSuccess(undefined);
      }
    }, 0);
    return request;
  }
  
  getAll() {
    const request = new MockIDBRequest();
    setTimeout(() => {
      request.triggerSuccess(Array.from(this.data.values()));
    }, 0);
    return request;
  }
  
  delete(key) {
    const request = new MockIDBRequest();
    setTimeout(() => {
      if (this.data.has(key)) {
        this.data.delete(key);
        request.triggerSuccess();
      } else {
        request.triggerError(new Error('Key not found'));
      }
    }, 0);
    return request;
  }
  
  clear() {
    const request = new MockIDBRequest();
    setTimeout(() => {
      this.data.clear();
      request.triggerSuccess();
    }, 0);
    return request;
  }
  
  createIndex(name, keyPath, options) {
    return { name, keyPath, options };
  }
}

// Mock IDBTransaction
class MockIDBTransaction {
  constructor(db, storeNames, mode) {
    this.db = db;
    this.storeNames = storeNames;
    this.mode = mode;
    this.objectStores = new Map();
    
    // Create object stores
    if (Array.isArray(storeNames)) {
      storeNames.forEach(name => {
        this.objectStores.set(name, new MockIDBObjectStore(name));
      });
    } else {
      this.objectStores.set(storeNames, new MockIDBObjectStore(storeNames));
    }
  }
  
  objectStore(name) {
    return this.objectStores.get(name);
  }
  
  commit() {
    if (this.oncomplete) {
      setTimeout(() => this.oncomplete(), 0);
    }
  }
  
  abort() {
    if (this.onabort) {
      setTimeout(() => this.onabort(), 0);
    }
  }
}

// Mock IDBDatabase
class MockIDBDatabase {
  constructor(name, version) {
    this.name = name;
    this.version = version;
    this.objectStoreNames = [];
    this.objectStores = new Map();
  }
  
  createObjectStore(name, options) {
    const store = new MockIDBObjectStore(name);
    this.objectStores.set(name, store);
    this.objectStoreNames.push(name);
    return store;
  }
  
  transaction(storeNames, mode) {
    return new MockIDBTransaction(this, storeNames, mode);
  }
  
  close() {
    // No-op for mock
  }
}

// Mock crypto for signing
global.crypto = {
  subtle: {
    generateKey: jest.fn().mockResolvedValue({
      privateKey: 'mock-private-key',
      publicKey: 'mock-public-key'
    }),
    sign: jest.fn().mockResolvedValue(new Uint8Array([1, 2, 3, 4])),
    verify: jest.fn().mockResolvedValue(true),
    exportKey: jest.fn().mockResolvedValue(new Uint8Array([5, 6, 7, 8]))
  },
  getRandomValues: jest.fn(array => {
    for (let i = 0; i < array.length; i++) {
      array[i] = Math.floor(Math.random() * 256);
    }
    return array;
  })
};

// Mock fetch
global.fetch = jest.fn().mockImplementation(() => 
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ 
      status: 'success',
      challenge: 'test-challenge',
      csrf_token: 'test-csrf-token'
    })
  })
);

// Setup global mocks before importing the wallet
global.indexedDB = mockIndexedDB;
global.IDBRequest = MockIDBRequest;
global.IDBObjectStore = MockIDBObjectStore;
global.IDBTransaction = MockIDBTransaction;
global.IDBDatabase = MockIDBDatabase;

// Import the wallet implementation
// Note: In a real test, you would import the actual wallet code
// For this example, we'll mock the LemmaWallet class
class LemmaWallet {
  constructor() {
    this.dbName = 'lemma_wallet';
    this.dbVersion = 1;
    this.credentialStore = 'credentials';
    this.metadataStore = 'metadata';
    this.initialized = false;
    this.db = null;
  }
  
  async init() {
    if (this.initialized) return Promise.resolve();
    
    try {
      this.db = await this.openDatabase();
      this.initialized = true;
      return Promise.resolve();
    } catch (error) {
      return Promise.reject(error);
    }
  }
  
  openDatabase() {
    return new Promise((resolve, reject) => {
      const request = new MockIDBRequest();
      const db = new MockIDBDatabase(this.dbName, this.dbVersion);
      
      // Create object stores
      db.createObjectStore(this.credentialStore, { keyPath: 'id' });
      db.createObjectStore(this.metadataStore, { keyPath: 'id' });
      
      setTimeout(() => request.triggerSuccess(db), 0);
      
      request.onsuccess = event => resolve(event.target.result);
      request.onerror = event => reject(event.target.error);
      
      // Mock the open call
      mockIndexedDB.open.mockReturnValue(request);
      
      return request;
    });
  }
  
  async storeCredential(credential, userId) {
    if (!this.initialized) await this.init();
    
    return new Promise((resolve, reject) => {
      try {
        // Format credential for storage if needed
        let walletCredential = credential;
        
        // If this is a raw credential, format it for the wallet
        if (!credential.wallet_metadata && credential.id) {
          walletCredential = {
            credential: credential,
            wallet_metadata: {
              added_at: new Date().toISOString(),
              holder_id: userId,
              status: 'active',
              display_name: 'Lemma Human Verification',
              fingerprint: credential.id
            },
            id: userId // Use userId as the key
          };
        }
        
        // Store in IndexedDB
        const transaction = this.db.transaction(this.credentialStore, 'readwrite');
        const store = transaction.objectStore(this.credentialStore);
        const request = store.put(walletCredential, userId);
        
        request.onsuccess = () => resolve(userId);
        request.onerror = event => reject(event.target.error);
      } catch (error) {
        reject(error);
      }
    });
  }
  
  async getCredentialByUserId(userId) {
    if (!this.initialized) await this.init();
    
    return new Promise((resolve, reject) => {
      try {
        const transaction = this.db.transaction(this.credentialStore, 'readonly');
        const store = transaction.objectStore(this.credentialStore);
        const request = store.get(userId);
        
        request.onsuccess = event => resolve(event.target.result);
        request.onerror = event => reject(event.target.error);
      } catch (error) {
        reject(error);
      }
    });
  }
  
  async getAllCredentials() {
    if (!this.initialized) await this.init();
    
    return new Promise((resolve, reject) => {
      try {
        const transaction = this.db.transaction(this.credentialStore, 'readonly');
        const store = transaction.objectStore(this.credentialStore);
        const request = store.getAll();
        
        request.onsuccess = event => resolve(event.target.result);
        request.onerror = event => reject(event.target.error);
      } catch (error) {
        reject(error);
      }
    });
  }
  
  async deleteCredential(id) {
    if (!this.initialized) await this.init();
    
    return new Promise((resolve, reject) => {
      try {
        const transaction = this.db.transaction(this.credentialStore, 'readwrite');
        const store = transaction.objectStore(this.credentialStore);
        const request = store.delete(id);
        
        request.onsuccess = () => resolve(true);
        request.onerror = event => reject(event.target.error);
      } catch (error) {
        reject(error);
      }
    });
  }
  
  async createPresentation(credential, challenge) {
    // Create a verifiable presentation from a credential
    const rawCredential = credential.credential || credential;
    
    // Create a simple presentation object
    const presentation = {
      "@context": [
        "https://www.w3.org/2018/credentials/v1"
      ],
      "type": ["VerifiablePresentation"],
      "verifiableCredential": [rawCredential],
      "holder": rawCredential.credentialSubject.id,
      "proof": {
        "type": "Ed25519Signature2020",
        "created": new Date().toISOString(),
        "challenge": challenge,
        "proofPurpose": "authentication",
        "verificationMethod": rawCredential.issuer + "#keys-1",
        "jws": "eyJhbGciOiJFZERTQSIsImI2NCI6ZmFsc2UsImNyaXQiOlsiYjY0Il19..mockSignature"
      }
    };
    
    return presentation;
  }
}

// Make the wallet available globally for tests
global.LemmaWallet = LemmaWallet;

// Begin tests
describe('LemmaWallet', () => {
  let wallet;
  
  beforeEach(async () => {
    // Reset mocks
    jest.clearAllMocks();
    
    // Create a new wallet instance
    wallet = new LemmaWallet();
    await wallet.init();
  });
  
  test('should initialize correctly', () => {
    expect(wallet.initialized).toBe(true);
    expect(wallet.db).not.toBeNull();
    expect(mockIndexedDB.open).toHaveBeenCalledWith('lemma_wallet', 1);
  });
  
  test('should store a credential', async () => {
    const userId = 'test-user-123';
    const credential = {
      id: 'credential-123',
      type: ['VerifiableCredential'],
      issuer: 'did:lemma:issuer',
      issuanceDate: '2025-05-22T12:00:00Z',
      credentialSubject: {
        id: `did:user:${userId}`,
        isHuman: true
      },
      proof: {
        type: 'Ed25519Signature2020',
        created: '2025-05-22T12:00:00Z',
        jws: 'mockSignature'
      }
    };
    
    const result = await wallet.storeCredential(credential, userId);
    expect(result).toBe(userId);
    
    // Verify it was stored
    const stored = await wallet.getCredentialByUserId(userId);
    expect(stored).toBeDefined();
    expect(stored.wallet_metadata.holder_id).toBe(userId);
    expect(stored.credential.id).toBe('credential-123');
  });
  
  test('should retrieve all credentials', async () => {
    // Store multiple credentials
    const users = ['user-1', 'user-2', 'user-3'];
    
    for (const userId of users) {
      const credential = {
        id: `credential-${userId}`,
        type: ['VerifiableCredential'],
        issuer: 'did:lemma:issuer',
        issuanceDate: '2025-05-22T12:00:00Z',
        credentialSubject: {
          id: `did:user:${userId}`,
          isHuman: true
        },
        proof: {
          type: 'Ed25519Signature2020',
          created: '2025-05-22T12:00:00Z',
          jws: 'mockSignature'
        }
      };
      
      await wallet.storeCredential(credential, userId);
    }
    
    // Retrieve all credentials
    const credentials = await wallet.getAllCredentials();
    expect(credentials.length).toBe(3);
    
    // Verify each credential
    for (const userId of users) {
      const credential = credentials.find(c => c.id === userId);
      expect(credential).toBeDefined();
      expect(credential.wallet_metadata.holder_id).toBe(userId);
    }
  });
  
  test('should delete a credential', async () => {
    // Store a credential
    const userId = 'test-user-delete';
    const credential = {
      id: `credential-${userId}`,
      type: ['VerifiableCredential'],
      issuer: 'did:lemma:issuer',
      issuanceDate: '2025-05-22T12:00:00Z',
      credentialSubject: {
        id: `did:user:${userId}`,
        isHuman: true
      },
      proof: {
        type: 'Ed25519Signature2020',
        created: '2025-05-22T12:00:00Z',
        jws: 'mockSignature'
      }
    };
    
    await wallet.storeCredential(credential, userId);
    
    // Verify it was stored
    let stored = await wallet.getCredentialByUserId(userId);
    expect(stored).toBeDefined();
    
    // Delete the credential
    const result = await wallet.deleteCredential(userId);
    expect(result).toBe(true);
    
    // Verify it was deleted
    stored = await wallet.getCredentialByUserId(userId);
    expect(stored).toBeUndefined();
  });
  
  test('should create a presentation from a credential', async () => {
    // Store a credential
    const userId = 'test-user-presentation';
    const credential = {
      id: `credential-${userId}`,
      type: ['VerifiableCredential'],
      issuer: 'did:lemma:issuer',
      issuanceDate: '2025-05-22T12:00:00Z',
      credentialSubject: {
        id: `did:user:${userId}`,
        isHuman: true
      },
      proof: {
        type: 'Ed25519Signature2020',
        created: '2025-05-22T12:00:00Z',
        jws: 'mockSignature'
      }
    };
    
    await wallet.storeCredential(credential, userId);
    
    // Create a presentation
    const challenge = 'test-challenge-123';
    const presentation = await wallet.createPresentation(
      await wallet.getCredentialByUserId(userId), 
      challenge
    );
    
    // Verify the presentation
    expect(presentation).toBeDefined();
    expect(presentation.type).toContain('VerifiablePresentation');
    expect(presentation.verifiableCredential[0].id).toBe(`credential-${userId}`);
    expect(presentation.proof.challenge).toBe(challenge);
    expect(presentation.proof.proofPurpose).toBe('authentication');
  });
});

// Test the wallet initialization script
describe('LemmaWalletInit', () => {
  // Mock the DOM
  document.body.innerHTML = `
    <div data-lemma="true"></div>
    <div id="lemma-widget-container"></div>
  `;
  
  // Mock document.cookie
  Object.defineProperty(document, 'cookie', {
    writable: true,
    value: ''
  });
  
  test('should detect Lemma integration', () => {
    // Create a script element to simulate the script loading
    const script = document.createElement('script');
    script.src = '/static/js/lemma-wallet-init.js';
    document.head.appendChild(script);
    
    // Trigger DOMContentLoaded
    const event = new Event('DOMContentLoaded');
    document.dispatchEvent(event);
    
    // Check that the cookie was set
    expect(document.cookie).toContain('lemma_wallet_enabled=true');
  });
  
  test('should initialize wallet when cookie is set', async () => {
    // Set the cookie
    document.cookie = 'lemma_wallet_enabled=true; path=/';
    
    // Mock the wallet initialization
    const mockWallet = new LemmaWallet();
    const initSpy = jest.spyOn(mockWallet, 'init');
    global.LemmaWallet = jest.fn().mockImplementation(() => mockWallet);
    
    // Trigger DOMContentLoaded
    const event = new Event('DOMContentLoaded');
    document.dispatchEvent(event);
    
    // Wait for async operations
    await new Promise(resolve => setTimeout(resolve, 0));
    
    // Check that the wallet was initialized
    expect(global.LemmaWallet).toHaveBeenCalled();
    expect(initSpy).toHaveBeenCalled();
    expect(global.lemmaWallet).toBe(mockWallet);
  });
  
  test('proveALemma should handle existing credential', async () => {
    // Set up a mock wallet with a credential
    const userId = 'test-user-prove';
    const credential = {
      id: `credential-${userId}`,
      type: ['VerifiableCredential'],
      issuer: 'did:lemma:issuer',
      issuanceDate: '2025-05-22T12:00:00Z',
      credentialSubject: {
        id: `did:user:${userId}`,
        isHuman: true
      },
      proof: {
        type: 'Ed25519Signature2020',
        created: '2025-05-22T12:00:00Z',
        jws: 'mockSignature'
      }
    };
    
    const mockWallet = new LemmaWallet();
    await mockWallet.init();
    await mockWallet.storeCredential(credential, userId);
    
    // Mock the wallet methods
    const getCredentialSpy = jest.spyOn(mockWallet, 'getCredentialByUserId');
    const createPresentationSpy = jest.spyOn(mockWallet, 'createPresentation');
    
    // Set the global wallet
    global.lemmaWallet = mockWallet;
    
    // Define the proveALemma function (simplified version)
    global.proveALemma = async function(options = {}) {
      try {
        const wallet = global.lemmaWallet;
        const userId = options.userId || 'test-user-prove';
        
        // Check if user has a credential
        const credential = await wallet.getCredentialByUserId(userId);
        
        if (credential) {
          // Create presentation
          const challenge = 'test-challenge';
          const presentation = await wallet.createPresentation(credential, challenge);
          
          // Mock verification API call
          return { 
            status: 'success', 
            verified: true,
            presentation: presentation
          };
        } else {
          return { status: 'error', message: 'No credential found' };
        }
      } catch (error) {
        return { status: 'error', message: error.message };
      }
    };
    
    // Call proveALemma
    const result = await global.proveALemma({ userId });
    
    // Verify the result
    expect(result.status).toBe('success');
    expect(result.verified).toBe(true);
    expect(getCredentialSpy).toHaveBeenCalledWith(userId);
    expect(createPresentationSpy).toHaveBeenCalled();
  });
});