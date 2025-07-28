import { 
  LemmaError, 
  RetryConfig, 
  CircuitBreakerConfig, 
  ErrorRecoveryStrategy, 
  ErrorReportingConfig,
  LemmaTimeoutError,
  LemmaNetworkError,
  LemmaInitializationError,
  LemmaVerificationError,
  LemmaQRScanError,
  LemmaCacheError,
  LemmaValidationError
} from './types';

/**
 * Enhanced retry mechanism with exponential backoff and jitter
 */
export class RetryManager {
  private config: RetryConfig;
  
  constructor(config: RetryConfig) {
    this.config = config;
  }
  
  /**
   * Execute a function with retry logic
   */
  async execute<T>(
    fn: () => Promise<T>,
    context: string = 'operation'
  ): Promise<T> {
    let lastError: Error;
    
    for (let attempt = 1; attempt <= this.config.maxAttempts; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error as Error;
        
        // Check if error is retryable
        if (!this.shouldRetry(error as Error, attempt)) {
          throw this.enhanceError(error as Error, attempt, context);
        }
        
        // Wait before retry (except for last attempt)
        if (attempt < this.config.maxAttempts) {
          await this.sleep(this.calculateDelay(attempt));
        }
      }
    }
    
    throw this.enhanceError(lastError!, this.config.maxAttempts, context);
  }
  
  private shouldRetry(error: Error, attempt: number): boolean {
    // Don't retry on last attempt
    if (attempt >= this.config.maxAttempts) {
      return false;
    }
    
    // Use custom retry condition if provided
    if (this.config.retryCondition) {
      return this.config.retryCondition(error);
    }
    
    // Default retry logic
    if (error instanceof LemmaError) {
      return error.isRetryable;
    }
    
    // Retry on network errors and timeouts
    return error.name === 'NetworkError' || 
           error.name === 'TimeoutError' ||
           error.message.includes('timeout') ||
           error.message.includes('network');
  }
  
  private calculateDelay(attempt: number): number {
    let delay = this.config.baseDelay * Math.pow(this.config.exponentialBase, attempt - 1);
    
    // Apply maximum delay limit
    delay = Math.min(delay, this.config.maxDelay);
    
    // Add jitter if enabled
    if (this.config.jitter) {
      delay = delay * (0.5 + Math.random() * 0.5);
    }
    
    return delay;
  }
  
  private enhanceError(error: Error, retryCount: number, context: string): Error {
    if (error instanceof LemmaError) {
      error.retryCount = retryCount;
      error.details = {
        ...error.details,
        context,
        finalAttempt: retryCount
      };
    }
    return error;
  }
  
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

/**
 * Circuit breaker pattern for resilience
 */
export class CircuitBreaker {
  private config: CircuitBreakerConfig;
  private state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' = 'CLOSED';
  private failures: number = 0;
  private successes: number = 0;
  private lastFailureTime: number = 0;
  private nextAttempt: number = 0;
  
  constructor(config: CircuitBreakerConfig) {
    this.config = config;
  }
  
  async execute<T>(fn: () => Promise<T>, context: string = 'operation'): Promise<T> {
    if (!this.config.enabled) {
      return await fn();
    }
    
    if (this.state === 'OPEN') {
      if (Date.now() < this.nextAttempt) {
        throw new LemmaError(
          `Circuit breaker is OPEN for ${context}. Next attempt in ${this.nextAttempt - Date.now()}ms`,
          'CIRCUIT_BREAKER_OPEN',
          { state: this.state, nextAttempt: this.nextAttempt }
        );
      }
      this.state = 'HALF_OPEN';
      this.successes = 0;
    }
    
    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }
  
  private onSuccess(): void {
    this.failures = 0;
    
    if (this.state === 'HALF_OPEN') {
      this.successes++;
      if (this.successes >= this.config.successThreshold) {
        this.state = 'CLOSED';
        this.successes = 0;
      }
    }
  }
  
  private onFailure(): void {
    this.failures++;
    this.lastFailureTime = Date.now();
    
    if (this.failures >= this.config.failureThreshold) {
      this.state = 'OPEN';
      this.nextAttempt = Date.now() + this.config.timeout;
    }
  }
  
  getState(): { state: string; failures: number; successes: number } {
    return {
      state: this.state,
      failures: this.failures,
      successes: this.successes
    };
  }
  
  reset(): void {
    this.state = 'CLOSED';
    this.failures = 0;
    this.successes = 0;
    this.lastFailureTime = 0;
    this.nextAttempt = 0;
  }
}

/**
 * Error recovery strategy manager
 */
export class ErrorRecoveryManager {
  private strategies: ErrorRecoveryStrategy[] = [];
  
  constructor(strategies: ErrorRecoveryStrategy[] = []) {
    this.strategies = strategies.sort((a, b) => b.priority - a.priority);
  }
  
  addStrategy(strategy: ErrorRecoveryStrategy): void {
    this.strategies.push(strategy);
    this.strategies.sort((a, b) => b.priority - a.priority);
  }
  
  async recover(error: Error): Promise<void> {
    for (const strategy of this.strategies) {
      if (strategy.condition(error)) {
        try {
          await strategy.recovery(error);
          return;
        } catch (recoveryError) {
          // Continue to next strategy if recovery fails
          console.warn(`Recovery strategy '${strategy.name}' failed:`, recoveryError);
        }
      }
    }
    
    // No recovery strategy worked
    throw new LemmaError(
      'No recovery strategy available for error',
      'RECOVERY_FAILED',
      { originalError: error }
    );
  }
}

/**
 * Error reporting and monitoring
 */
export class ErrorReporter {
  private config: ErrorReportingConfig;
  private errorQueue: any[] = [];
  private isProcessing: boolean = false;
  
  constructor(config: ErrorReportingConfig) {
    this.config = config;
  }
  
  async report(error: Error, context: string = 'unknown'): Promise<void> {
    if (!this.config.enabled) {
      return;
    }
    
    const errorReport = this.createErrorReport(error, context);
    
    if (this.config.endpoint) {
      this.errorQueue.push(errorReport);
      this.processQueue();
    }
    
    // Log to console in debug mode
    if (this.config.includeStackTrace) {
      console.error('Lemma Error Report:', errorReport);
    }
  }
  
  private createErrorReport(error: Error, context: string): any {
    const report: any = {
      timestamp: Date.now(),
      context,
      message: error.message,
      name: error.name,
      type: error.constructor.name
    };
    
    if (error instanceof LemmaError) {
      report.code = error.code;
      report.isRetryable = error.isRetryable;
      report.retryCount = error.retryCount;
      report.details = error.details;
    }
    
    if (this.config.includeStackTrace) {
      report.stack = error.stack;
    }
    
    if (this.config.includeUserAgent) {
      report.userAgent = navigator.userAgent;
    }
    
    if (this.config.includeUrl) {
      report.url = window.location.href;
    }
    
    if (this.config.customFields) {
      report.custom = this.config.customFields;
    }
    
    return report;
  }
  
  private async processQueue(): Promise<void> {
    if (this.isProcessing || this.errorQueue.length === 0) {
      return;
    }
    
    this.isProcessing = true;
    
    const batch = this.errorQueue.splice(0, 10); // Process max 10 errors at once
    
    try {
      await fetch(this.config.endpoint!, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.config.apiKey && { 'Authorization': `Bearer ${this.config.apiKey}` })
        },
        body: JSON.stringify({ errors: batch })
      });
    } catch (error) {
      console.warn('Failed to report errors:', error);
      // Put errors back in queue for retry
      this.errorQueue.unshift(...batch);
    } finally {
      this.isProcessing = false;
      
      // Continue processing if more errors in queue
      if (this.errorQueue.length > 0) {
        setTimeout(() => this.processQueue(), 1000);
      }
    }
  }
}

/**
 * Comprehensive error handling coordinator
 */
export class ErrorHandler {
  private retryManager: RetryManager;
  private circuitBreaker: CircuitBreaker;
  private recoveryManager: ErrorRecoveryManager;
  private errorReporter: ErrorReporter;
  
  constructor(
    retryConfig: RetryConfig,
    circuitBreakerConfig: CircuitBreakerConfig,
    recoveryStrategies: ErrorRecoveryStrategy[],
    reportingConfig: ErrorReportingConfig
  ) {
    this.retryManager = new RetryManager(retryConfig);
    this.circuitBreaker = new CircuitBreaker(circuitBreakerConfig);
    this.recoveryManager = new ErrorRecoveryManager(recoveryStrategies);
    this.errorReporter = new ErrorReporter(reportingConfig);
    
    this.setupDefaultRecoveryStrategies();
  }
  
  /**
   * Execute operation with full error handling
   */
  async executeWithErrorHandling<T>(
    fn: () => Promise<T>,
    context: string = 'operation'
  ): Promise<T> {
    try {
      return await this.circuitBreaker.execute(
        () => this.retryManager.execute(fn, context),
        context
      );
    } catch (error) {
      // Report error
      await this.errorReporter.report(error as Error, context);
      
      // Attempt recovery
      try {
        await this.recoveryManager.recover(error as Error);
        // If recovery succeeds, retry the operation once
        return await fn();
      } catch (recoveryError) {
        // Recovery failed, throw original error
        throw error;
      }
    }
  }
  
  private setupDefaultRecoveryStrategies(): void {
    // Recovery strategy for initialization errors
    this.recoveryManager.addStrategy({
      name: 'WASM Reinitialization',
      condition: (error) => error instanceof LemmaInitializationError,
      recovery: async (error) => {
        // Clear any cached WASM module
        if ('lemma_wasm' in window) {
          delete (window as any).lemma_wasm;
        }
        // Force reload WASM module
        await new Promise(resolve => setTimeout(resolve, 1000));
      },
      priority: 10
    });
    
    // Recovery strategy for cache errors
    this.recoveryManager.addStrategy({
      name: 'Cache Clear',
      condition: (error) => error instanceof LemmaCacheError,
      recovery: async (error) => {
        // Clear caches
        if ('caches' in window) {
          const names = await caches.keys();
          await Promise.all(names.map(name => caches.delete(name)));
        }
        // Clear local storage
        localStorage.removeItem('lemma_cache');
        sessionStorage.removeItem('lemma_cache');
      },
      priority: 5
    });
    
    // Recovery strategy for network errors
    this.recoveryManager.addStrategy({
      name: 'Network Recovery',
      condition: (error) => error instanceof LemmaNetworkError,
      recovery: async (error) => {
        // Wait for network to recover
        await new Promise(resolve => {
          const checkOnline = () => {
            if (navigator.onLine) {
              resolve(void 0);
            } else {
              setTimeout(checkOnline, 1000);
            }
          };
          checkOnline();
        });
      },
      priority: 3
    });
  }
  
  getStatus(): {
    circuitBreaker: any;
    errorQueue: number;
  } {
    return {
      circuitBreaker: this.circuitBreaker.getState(),
      errorQueue: (this.errorReporter as any).errorQueue.length
    };
  }
}

/**
 * Create default error handler instance
 */
export function createErrorHandler(
  retryConfig: RetryConfig,
  circuitBreakerConfig: CircuitBreakerConfig,
  recoveryStrategies: ErrorRecoveryStrategy[],
  reportingConfig: ErrorReportingConfig
): ErrorHandler {
  return new ErrorHandler(
    retryConfig,
    circuitBreakerConfig,
    recoveryStrategies,
    reportingConfig
  );
}

/**
 * Utility function to wrap any function with error handling
 */
export function withErrorHandling<T extends (...args: any[]) => Promise<any>>(
  fn: T,
  errorHandler: ErrorHandler,
  context: string = 'function'
): T {
  return (async (...args: Parameters<T>): Promise<ReturnType<T>> => {
    return await errorHandler.executeWithErrorHandling(
      () => fn(...args),
      context
    );
  }) as T;
} 