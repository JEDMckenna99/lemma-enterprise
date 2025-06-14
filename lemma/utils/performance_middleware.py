"""
Performance Optimization Middleware for Lemma Enterprise
Implements aggressive caching, connection pooling, and request optimization
"""

import time
import gzip
import io
from flask import Flask, request, g, current_app, jsonify
from functools import wraps, lru_cache
import threading
import logging

logger = logging.getLogger(__name__)

class PerformanceMiddleware:
    """High-performance middleware for sub-250ms response times."""
    
    def __init__(self, app: Flask = None):
        self.app = app
        self.response_cache = {}
        self.cache_lock = threading.Lock()
        self.request_stats = {}
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize performance middleware."""
        app.before_request(self.optimize_request)
        app.after_request(self.optimize_response)
        app.before_request(self.cache_check)
        
    def optimize_request(self):
        """Optimize incoming requests."""
        # Start performance timer
        g.perf_start = time.time()
        
        # Skip heavy operations for API health checks and fast endpoints
        if request.path in ['/api/health', '/health', '/ping', '/api/ping', '/api/fast-test']:
            g.skip_heavy_ops = True
            g.skip_sre_metrics = True  # Skip SRE metrics collection for ultra-fast paths
        elif request.path in ['/api/generate-challenge']:
            g.skip_heavy_ops = True
            g.skip_sre_metrics = False  # Keep metrics for challenge generation
        else:
            g.skip_heavy_ops = False
            g.skip_sre_metrics = False
            
        # Enable request compression only for larger responses
        if 'gzip' in request.headers.get('Accept-Encoding', '') and not g.skip_heavy_ops:
            g.enable_compression = True
        else:
            g.enable_compression = False
    
    def cache_check(self):
        """Check cache for quick responses."""
        # Cache GET requests for non-auth endpoints
        if request.method == 'GET' and not request.headers.get('X-API-Key'):
            cache_key = f"{request.path}:{request.query_string.decode()}"
            
            with self.cache_lock:
                if cache_key in self.response_cache:
                    cached_response, timestamp = self.response_cache[cache_key]
                    # Cache valid for 60 seconds
                    if time.time() - timestamp < 60:
                        return cached_response
    
    def optimize_response(self, response):
        """Optimize outgoing responses."""
        # Skip optimization for static files to prevent RuntimeError
        if request.path.startswith('/static/'):
            return response
            
        # Calculate response time
        if hasattr(g, 'perf_start'):
            response_time = (time.time() - g.perf_start) * 1000
            response.headers['X-Response-Time'] = f"{response_time:.1f}ms"
            
            # Log slow responses
            if response_time > 250:
                logger.warning(f"Slow response: {request.path} took {response_time:.1f}ms")
        
        # Enable compression for large responses
        if (hasattr(g, 'enable_compression') and g.enable_compression and 
            len(response.get_data()) > 1024):
            
            compressed_data = gzip.compress(response.get_data())
            if len(compressed_data) < len(response.get_data()):
                response.set_data(compressed_data)
                response.headers['Content-Encoding'] = 'gzip'
                response.headers['Content-Length'] = len(compressed_data)
        
        # Cache successful GET responses
        if (request.method == 'GET' and response.status_code == 200 and 
            not request.headers.get('X-API-Key') and len(response.get_data()) < 10240):
            
            cache_key = f"{request.path}:{request.query_string.decode()}"
            with self.cache_lock:
                self.response_cache[cache_key] = (response, time.time())
                
                # Limit cache size
                if len(self.response_cache) > 1000:
                    # Remove oldest entries
                    oldest_keys = sorted(self.response_cache.keys())[:100]
                    for key in oldest_keys:
                        del self.response_cache[key]
        
        # Security headers for performance
        response.headers['Cache-Control'] = 'public, max-age=300'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        return response

# High-performance caching decorators
def performance_cache(seconds=300):
    """Cache function results for specified seconds."""
    def decorator(f):
        cache = {}
        cache_lock = threading.Lock()
        
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Create cache key
            cache_key = str(args) + str(sorted(kwargs.items()))
            
            with cache_lock:
                if cache_key in cache:
                    result, timestamp = cache[cache_key]
                    if time.time() - timestamp < seconds:
                        return result
                
                # Call function and cache result
                result = f(*args, **kwargs)
                cache[cache_key] = (result, time.time())
                
                # Limit cache size
                if len(cache) > 1000:
                    oldest_key = min(cache.keys(), key=lambda k: cache[k][1])
                    del cache[oldest_key]
                
                return result
        return wrapper
    return decorator

@lru_cache(maxsize=1000)
def fast_did_cache(did_string):
    """Ultra-fast DID resolution cache."""
    try:
        from lemma.core.did_resolver import get_did_resolver
        resolver = get_did_resolver()
        return resolver.resolve(did_string) if resolver else None
    except Exception as e:
        logger.error(f"DID resolution error: {e}")
        return None

def fast_json_response(data, status=200):
    """Optimized JSON response generation."""
    import json
    response_data = json.dumps(data, separators=(',', ':'))
    response = current_app.response_class(
        response_data,
        status=status,
        mimetype='application/json'
    )
    response.headers['Content-Length'] = len(response_data)
    return response

# Performance optimization for credential operations
@performance_cache(600)  # 10-minute cache
def cached_credential_verification(credential_data):
    """Cached credential verification for repeated checks."""
    try:
        from lemma.core.credential_service import get_credential_service
        service = get_credential_service()
        return service.verify_credential(credential_data) if service else False
    except Exception as e:
        logger.error(f"Credential verification error: {e}")
        return False

# Database connection pooling simulation
class ConnectionPool:
    """Simple connection pool for better performance."""
    
    def __init__(self, max_connections=50):
        self.connections = []
        self.max_connections = max_connections
        self.lock = threading.Lock()
    
    def get_connection(self):
        """Get a connection from the pool."""
        with self.lock:
            if self.connections:
                return self.connections.pop()
            return self._create_connection()
    
    def return_connection(self, conn):
        """Return a connection to the pool."""
        with self.lock:
            if len(self.connections) < self.max_connections:
                self.connections.append(conn)
    
    def _create_connection(self):
        """Create a new connection."""
        # Placeholder for actual connection creation
        return {"connection_id": time.time()}

# Global connection pool
connection_pool = ConnectionPool()

def init_performance_middleware(app: Flask):
    """Initialize performance optimizations."""
    middleware = PerformanceMiddleware(app)
    
    # Enable performance monitoring
    @app.before_request
    def performance_monitoring():
        g.request_start = time.time()
    
    @app.after_request
    def performance_headers(response):
        if hasattr(g, 'request_start'):
            duration = (time.time() - g.request_start) * 1000
            response.headers['X-Performance-Duration'] = f"{duration:.2f}ms"
            
            # Alert on slow requests
            if duration > 250:
                logger.warning(f"PERFORMANCE ALERT: {request.method} {request.path} took {duration:.1f}ms")
        
        return response
    
    logger.info("Performance middleware initialized - targeting <250ms response times")
    return middleware 