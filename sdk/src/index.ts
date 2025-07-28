/**
 * Lemma Verification SDK - Main Implementation
 * 
 * Production-ready SDK for offline credential verification
 */

import {
  LemmaSDK,
  LemmaConfig,
  LemmaState,
  VerificationResult,
  QRScanResult,
  QRScanOptions,
  LemmaEventType,
  LemmaEventCallback,
  CredentialClaims,
  LemmaError,
  LemmaInitializationError,
  LemmaVerificationError,
  LemmaQRScanError,
  DEFAULT_CONFIG,
  PerformanceMetrics
} from './types';
import { 
  ErrorHandler, 
  createErrorHandler, 
  withErrorHandling 
} from './error-handling';

/**
 * Main Lemma SDK class
 */
export class Lemma implements LemmaSDK {
  public version = '1.0.0';
  public config: LemmaConfig;
  public state: LemmaState;
  
  private verifier: any = null;
  private qrScanner: any = null;
  private events: Record<string, LemmaEventCallback[]> = {};
  private performanceData: PerformanceMetrics['verification'] = {
    count: 0,
    totalTime: 0,
    averageTime: 0,
    minTime: Infinity,
    maxTime: 0
  };
  private cache: Map<string, VerificationResult> = new Map();
  private cacheEnabled = true;
  private maxCacheSize = 1000;
  private errorHandler: ErrorHandler;
  
  constructor(config: LemmaConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.state = {
      isScanning: false,
      isVerifying: false,
      lastResult: null,
      networkCalls: 0,
      cacheHits: 0,
      initialized: false
    };
    
    // Initialize error handler
    this.errorHandler = createErrorHandler(
      { ...DEFAULT_CONFIG.retry, ...this.config.retry } as any,
      { ...DEFAULT_CONFIG.circuitBreaker, ...this.config.circuitBreaker } as any,
      this.config.errorRecovery || DEFAULT_CONFIG.errorRecovery,
      { ...DEFAULT_CONFIG.errorReporting, ...this.config.errorReporting } as any
    );
    
    if (this.config.autoInit) {
      this.init();
    }
  }
  
  /**
   * Initialize the Lemma SDK
   */
  async init(config?: LemmaConfig): Promise<void> {
    if (config) {
      this.config = { ...this.config, ...config };
    }
    
    return this.errorHandler.executeWithErrorHandling(async () => {
      this.log('Initializing Lemma SDK...');
      
      // Load WebAssembly module
      await this.loadWASM();
      
      // Initialize QR scanner if available
      await this.initQRScanner();
      
      // Mark as initialized
      this.state.initialized = true;
      
      this.log('Lemma SDK initialized successfully');
      this.emit('ready');
    }, 'init');
  }
  
  /**
   * Verify a credential
   */
  async verify(credentialData: string): Promise<VerificationResult> {
    if (!this.state.initialized) {
      throw new LemmaInitializationError('SDK not initialized');
    }
    
    // Check cache first
    if (this.cacheEnabled && this.cache.has(credentialData)) {
      const cachedResult = this.cache.get(credentialData)!;
      this.state.cacheHits++;
      this.log('Cache hit for credential verification');
      return cachedResult;
    }
    
    return this.errorHandler.executeWithErrorHandling(async () => {
      this.state.isVerifying = true;
      this.emit('verification-start');
      
      const startTime = performance.now();
      
      // Verify using WebAssembly module
      const wasmResult = this.verifier.verify(credentialData);
      
      const endTime = performance.now();
      const verificationTime = endTime - startTime;
      
      // Update performance metrics
      this.updatePerformanceMetrics(verificationTime);
      
      const result: VerificationResult = {
        verified: wasmResult.verified,
        claims: wasmResult.claims || {},
        timing: {
          verification: verificationTime,
          unit: 'microseconds'
        },
        networkCalls: 0, // Always offline
        cacheHit: false
      };
      
      // Cache the result
      if (this.cacheEnabled) {
        this.addToCache(credentialData, result);
      }
      
      this.state.lastResult = result;
      this.state.isVerifying = false;
      
      this.log('Verification completed:', result);
      this.emit('verification-complete', result);
      
      return result;
    }, 'verify').finally(() => {
      this.state.isVerifying = false;
    });
  }
  
  /**
   * Scan QR code
   */
  async scanQR(options: QRScanOptions = {}): Promise<QRScanResult> {
    if (!this.state.initialized) {
      throw new LemmaInitializationError('SDK not initialized');
    }
    
    if (!this.qrScanner) {
      throw new LemmaQRScanError('QR Scanner not available');
    }
    
    try {
      this.state.isScanning = true;
      this.emit('scan-start');
      
      this.log('Starting QR scan...');
      
      // Start scanning
      const scanResult = await this.performQRScan(options);
      
      // Verify the scanned credential
      const verificationResult = await this.verify(scanResult.data);
      
      const result: QRScanResult = {
        data: scanResult.data,
        verificationResult,
        timestamp: Date.now()
      };
      
      this.state.isScanning = false;
      this.log('QR scan completed:', result);
      this.emit('scan-complete', result);
      
      return result;
      
    } catch (error) {
      this.state.isScanning = false;
      const scanError = new LemmaQRScanError(
        'QR scan failed',
        error
      );
      this.emit('scan-error', scanError);
      throw scanError;
    }
  }
  
  /**
   * Stop QR scanning
   */
  stopQRScan(): void {
    if (this.qrScanner && this.state.isScanning) {
      this.qrScanner.stop();
      this.state.isScanning = false;
      this.emit('scan-stop');
      this.log('QR scan stopped');
    }
  }
  
  /**
   * Event system
   */
  on<T = any>(event: LemmaEventType, callback: LemmaEventCallback<T>): void {
    if (!this.events[event]) {
      this.events[event] = [];
    }
    this.events[event].push(callback);
  }
  
  off<T = any>(event: LemmaEventType, callback: LemmaEventCallback<T>): void {
    if (this.events[event]) {
      this.events[event] = this.events[event].filter(cb => cb !== callback);
    }
  }
  
  emit<T = any>(event: LemmaEventType, data?: T): void {
    if (this.events[event]) {
      this.events[event].forEach(callback => {
        try {
          callback({
            type: event,
            data,
            timestamp: Date.now()
          });
        } catch (error) {
          console.error('[LEMMA-SDK] Event callback error:', error);
        }
      });
    }
  }
  
  /**
   * Utility methods
   */
  validateCredential(credentialData: string): boolean {
    try {
      // Basic validation - check if it's valid JSON
      const parsed = JSON.parse(credentialData);
      return typeof parsed === 'object' && parsed !== null;
    } catch {
      return false;
    }
  }
  
  parseClaims(credentialData: string): CredentialClaims {
    try {
      const parsed = JSON.parse(credentialData);
      return parsed.claims || parsed;
    } catch {
      return {};
    }
  }
  
  getPerformanceMetrics(): {
    averageVerificationTime: number;
    totalVerifications: number;
    cacheHitRate: number;
    errorRate: number;
  } {
    return {
      averageVerificationTime: this.performanceData.averageTime,
      totalVerifications: this.performanceData.count,
      cacheHitRate: this.performanceData.count > 0 ? this.state.cacheHits / this.performanceData.count : 0,
      errorRate: 0 // TODO: Implement error tracking
    };
  }
  
  /**
   * Cache management
   */
  clearCache(): void {
    this.cache.clear();
    this.state.cacheHits = 0;
    this.log('Cache cleared');
  }
  
  getCacheSize(): number {
    return this.cache.size;
  }
  
  setCacheEnabled(enabled: boolean): void {
    this.cacheEnabled = enabled;
    if (!enabled) {
      this.clearCache();
    }
    this.log(`Cache ${enabled ? 'enabled' : 'disabled'}`);
  }
  
  /**
   * Private methods
   */
  private async loadWASM(): Promise<void> {
    try {
      this.log('Loading WebAssembly module...');
      
      // Import the WASM module
      const wasmModule = await import(this.config.wasmPath + 'lemma_crypto.js');
      
      // Initialize verifier
      this.verifier = new wasmModule.LemmaVerifier();
      
      this.log('WebAssembly loaded successfully');
      
    } catch (error) {
      throw new LemmaInitializationError('Failed to load WebAssembly module', error);
    }
  }
  
  private async initQRScanner(): Promise<void> {
    try {
      // Dynamically load QR scanner library
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/qr-scanner@1.4.2/qr-scanner.min.js';
      
      await new Promise<void>((resolve, reject) => {
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Failed to load QR scanner'));
        document.head.appendChild(script);
      });
      
      this.log('QR Scanner library loaded');
      
    } catch (error) {
      this.log('QR Scanner not available:', error);
      // QR scanner is optional, don't throw error
    }
  }
  
  private async performQRScan(options: QRScanOptions): Promise<{ data: string }> {
    return new Promise((resolve, reject) => {
      // Create video element
      const video = document.createElement('video');
      video.style.display = 'none';
      document.body.appendChild(video);
      
      // Initialize scanner
      const scanner = new (window as any).QrScanner(
        video,
        (result: { data: string }) => {
          scanner.stop();
          document.body.removeChild(video);
          resolve(result);
        },
        {
          returnDetailedScanResult: true,
          highlightScanRegion: options.highlightScanRegion !== false,
          highlightCodeOutline: options.highlightCodeOutline !== false,
          ...options
        }
      );
      
      // Start scanning
      scanner.start().catch(reject);
      
      // Cleanup on timeout
      setTimeout(() => {
        scanner.stop();
        document.body.removeChild(video);
        reject(new LemmaQRScanError('QR scan timeout'));
      }, this.config.timeout);
    });
  }
  
  private updatePerformanceMetrics(time: number): void {
    this.performanceData.count++;
    this.performanceData.totalTime += time;
    this.performanceData.averageTime = this.performanceData.totalTime / this.performanceData.count;
    this.performanceData.minTime = Math.min(this.performanceData.minTime, time);
    this.performanceData.maxTime = Math.max(this.performanceData.maxTime, time);
  }
  
  private addToCache(key: string, result: VerificationResult): void {
    // Remove oldest entries if cache is full
    if (this.cache.size >= this.maxCacheSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    
    this.cache.set(key, { ...result, cacheHit: true });
  }
  
  private log(message: string, ...args: any[]): void {
    if (this.config.debug) {
      console.log('[LEMMA-SDK]', message, ...args);
    }
  }
}

// Export default instance
export const lemma = new Lemma();

// Export all types
export * from './types';

// Export components (will be created next)
// export * from './components/react';

// Default export
export default Lemma; 