"""
Rate Limiting for Lemma IAM
Redis-based distributed rate limiting for production stability
"""

import os
import redis
import logging
from functools import wraps
from flask import request, jsonify
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Initialize Redis client
try:
    REDIS_URL = os.getenv('REDIS_URL')
    if REDIS_URL:
        # Configure SSL for Heroku Redis
        redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=False,
            ssl_cert_reqs=None  # Disable SSL cert verification for Heroku Redis
        )
        redis_client.ping()  # Test connection
        REDIS_AVAILABLE = True
        logger.info("✅ Redis rate limiting initialized")
    else:
        REDIS_AVAILABLE = False
        logger.warning("⚠️ REDIS_URL not set - rate limiting disabled")
except Exception as e:
    REDIS_AVAILABLE = False
    logger.warning(f"⚠️ Redis connection failed: {e}")
    logger.warning("   Rate limiting disabled - requests will not be limited")


def rate_limit(
    limit: int,
    period: int,
    key_func: Optional[Callable] = None,
    error_message: Optional[str] = None
):
    """
    Rate limiting decorator
    
    Args:
        limit: Maximum number of requests
        period: Time period in seconds
        key_func: Function to generate rate limit key (default: IP address)
        error_message: Custom error message
    
    Usage:
        @rate_limit(10, 3600)  # 10 requests per hour
        def my_endpoint():
            ...
        
        @rate_limit(100, 60, key_func=lambda: request.headers.get('X-API-Key'))
        def api_endpoint():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip if Redis not available
            if not REDIS_AVAILABLE:
                logger.warning(f"Rate limiting skipped for {f.__name__} (Redis unavailable)")
                return f(*args, **kwargs)
            
            try:
                # Generate rate limit key
                if key_func:
                    key = key_func()
                else:
                    key = request.remote_addr or 'unknown'
                
                rate_key = f'rate_limit:{f.__name__}:{key}'
                
                # Increment counter
                current = redis_client.incr(rate_key)
                
                # Set expiry on first request
                if current == 1:
                    redis_client.expire(rate_key, period)
                
                # Check if limit exceeded
                if current > limit:
                    ttl = redis_client.ttl(rate_key)
                    
                    # Log rate limit violation for security monitoring
                    from api.audit_logger import log_event, AuditEvent
                    log_event(
                        AuditEvent.RATE_LIMIT_EXCEEDED,
                        result='warning',
                        metadata={
                            'endpoint': f.__name__,
                            'key': key,
                            'current': current,
                            'limit': limit,
                            'period': period
                        }
                    )
                    
                    return jsonify({
                        'error': error_message or 'Rate limit exceeded',
                        'limit': limit,
                        'period': period,
                        'retry_after': ttl if ttl > 0 else period
                    }), 429
                
                # Add rate limit headers to response
                response = f(*args, **kwargs)
                
                # Add headers if response supports it
                if hasattr(response, 'headers'):
                    response.headers['X-RateLimit-Limit'] = str(limit)
                    response.headers['X-RateLimit-Remaining'] = str(max(0, limit - current))
                    response.headers['X-RateLimit-Reset'] = str(redis_client.ttl(rate_key))
                
                return response
                
            except redis.RedisError as e:
                logger.error(f"Rate limiting error: {e}")
                # Fail open - don't block requests if Redis is down
                return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def block_ip(ip_address: str, duration: int = 86400, reason: str = "Abuse detected"):
    """
    Block an IP address
    
    Args:
        ip_address: IP to block
        duration: Block duration in seconds (default: 24 hours)
        reason: Reason for blocking
    """
    if not REDIS_AVAILABLE:
        logger.warning("Cannot block IP - Redis unavailable")
        return False
    
    try:
        block_key = f'blocked_ip:{ip_address}'
        redis_client.setex(block_key, duration, reason)
        
        # Log the block
        from api.audit_logger import log_event, AuditEvent
        log_event(
            AuditEvent.IP_BLOCKED,
            result='warning',
            metadata={
                'ip_address': ip_address,
                'duration': duration,
                'reason': reason
            }
        )
        
        logger.warning(f"🚫 Blocked IP {ip_address} for {duration}s: {reason}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to block IP {ip_address}: {e}")
        return False


def unblock_ip(ip_address: str):
    """Unblock an IP address"""
    if not REDIS_AVAILABLE:
        return False
    
    try:
        block_key = f'blocked_ip:{ip_address}'
        redis_client.delete(block_key)
        logger.info(f"✅ Unblocked IP {ip_address}")
        return True
    except Exception as e:
        logger.error(f"Failed to unblock IP {ip_address}: {e}")
        return False


def is_ip_blocked(ip_address: str) -> tuple[bool, Optional[str]]:
    """
    Check if an IP address is blocked
    
    Returns:
        (is_blocked, reason)
    """
    if not REDIS_AVAILABLE:
        return False, None
    
    try:
        block_key = f'blocked_ip:{ip_address}'
        reason = redis_client.get(block_key)
        
        if reason:
            return True, reason.decode('utf-8') if isinstance(reason, bytes) else reason
        return False, None
        
    except Exception as e:
        logger.error(f"Failed to check IP block status: {e}")
        return False, None


def check_ip_not_blocked():
    """
    Decorator to check if IP is blocked before processing request
    
    Usage:
        @check_ip_not_blocked()
        def my_endpoint():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip_address = request.remote_addr
            is_blocked, reason = is_ip_blocked(ip_address)
            
            if is_blocked:
                logger.warning(f"🚫 Blocked IP attempted access: {ip_address}")
                return jsonify({
                    'error': 'Access denied',
                    'reason': 'Your IP address has been blocked',
                    'details': reason,
                    'contact': 'support@lemma.id'
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Pre-configured rate limiters for common use cases

def rate_limit_email_confirmation():
    """Rate limit for email confirmation requests: 10 per hour per email"""
    return rate_limit(
        10, 
        3600,
        key_func=lambda: request.json.get('user_email', request.remote_addr),
        error_message='Too many email confirmation requests. Please try again later.'
    )


def rate_limit_site_registration():
    """Rate limit for site registration: 5 per hour per IP"""
    return rate_limit(
        5,
        3600,
        error_message='Too many registration attempts. Please try again later.'
    )


def rate_limit_permission_grant():
    """Rate limit for permission grants: 100 per hour per API key"""
    return rate_limit(
        100,
        3600,
        key_func=lambda: request.headers.get('X-API-Key', request.remote_addr),
        error_message='Too many permission grants. Please contact support.'
    )


def rate_limit_access_verification():
    """Rate limit for access verification: 1000 per minute per API key"""
    return rate_limit(
        1000,
        60,
        key_func=lambda: request.headers.get('X-API-Key', request.remote_addr),
        error_message='Rate limit exceeded for access verification.'
    )


def rate_limit_oauth_token():
    """Rate limit for OAuth token requests: 20 per hour per client"""
    return rate_limit(
        20,
        3600,
        key_func=lambda: request.json.get('client_id', request.remote_addr),
        error_message='Too many token requests. Please try again later.'
    )


def rate_limit_audit_export():
    """Rate limit for audit log exports: 10 per hour per site"""
    return rate_limit(
        10,
        3600,
        key_func=lambda: request.args.get('site_id', request.remote_addr),
        error_message='Too many export requests. Please try again later.'
    )


# Adaptive rate limiting - slow down suspicious activity

def check_suspicious_activity(ip_address: str, threshold: int = 10) -> bool:
    """
    Check if IP shows suspicious activity patterns
    
    Args:
        ip_address: IP to check
        threshold: Number of violations before blocking
    
    Returns:
        True if IP should be blocked
    """
    if not REDIS_AVAILABLE:
        return False
    
    try:
        violation_key = f'violations:{ip_address}'
        violations = redis_client.get(violation_key)
        
        if violations:
            violation_count = int(violations)
            
            if violation_count >= threshold:
                # Block IP for 24 hours
                block_ip(ip_address, 86400, f"Suspicious activity ({violation_count} violations)")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to check suspicious activity: {e}")
        return False


def record_violation(ip_address: str, violation_type: str):
    """
    Record a rate limit or security violation
    
    After threshold violations, IP gets blocked automatically
    """
    if not REDIS_AVAILABLE:
        return
    
    try:
        violation_key = f'violations:{ip_address}'
        violations = redis_client.incr(violation_key)
        
        # Set 1-hour expiry
        if violations == 1:
            redis_client.expire(violation_key, 3600)
        
        logger.warning(f"⚠️ Violation recorded for {ip_address}: {violation_type} ({violations} total)")
        
        # Auto-block after 10 violations
        if violations >= 10:
            check_suspicious_activity(ip_address, threshold=10)
        
    except Exception as e:
        logger.error(f"Failed to record violation: {e}")


# Simple rate limit check (non-decorator)

def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """
    Simple rate limit check - returns True if under limit, False if exceeded
    
    Args:
        key: Unique key for this rate limit (e.g., "recovery:192.168.1.1")
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds
    
    Returns:
        True if request is allowed, False if rate limit exceeded
    """
    if not REDIS_AVAILABLE:
        # Fail open if Redis unavailable
        return True
    
    try:
        rate_key = f'rate_check:{key}'
        current = redis_client.incr(rate_key)
        
        if current == 1:
            redis_client.expire(rate_key, window_seconds)
        
        return current <= max_requests
        
    except Exception as e:
        logger.error(f"Rate limit check failed: {e}")
        return True  # Fail open


# Helper function to get rate limit stats

def get_rate_limit_stats() -> dict:
    """Get rate limiting statistics for monitoring dashboard"""
    if not REDIS_AVAILABLE:
        return {'available': False, 'message': 'Redis not configured'}
    
    try:
        # Get all rate limit keys
        rate_keys = redis_client.keys('rate_limit:*')
        violation_keys = redis_client.keys('violations:*')
        blocked_keys = redis_client.keys('blocked_ip:*')
        
        return {
            'available': True,
            'active_rate_limits': len(rate_keys),
            'ips_with_violations': len(violation_keys),
            'blocked_ips': len(blocked_keys),
            'blocked_list': [
                {
                    'ip': key.decode('utf-8').replace('blocked_ip:', ''),
                    'reason': redis_client.get(key).decode('utf-8'),
                    'ttl': redis_client.ttl(key)
                }
                for key in blocked_keys[:10]  # Show first 10
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to get rate limit stats: {e}")
        return {'available': False, 'error': str(e)}

