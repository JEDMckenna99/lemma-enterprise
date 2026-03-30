"""
Sentry Configuration for Error Tracking
Automatically captures exceptions and performance data
"""

import os
import logging

logger = logging.getLogger(__name__)

def init_sentry(app):
    """
    Initialize Sentry error tracking
    
    Setup:
    1. Sign up at sentry.io (free tier)
    2. Create new project for "lemma-iam"
    3. Add SENTRY_DSN to Heroku config:
       heroku config:set SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
    """
    sentry_dsn = os.getenv('SENTRY_DSN')
    
    if not sentry_dsn:
        logger.warning("⚠️ SENTRY_DSN not set - error tracking disabled")
        logger.warning("   Sign up at sentry.io and set SENTRY_DSN env var")
        return False
    
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        
        # Capture all logs at INFO level and above
        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR
        )
        
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                FlaskIntegration(),
                sentry_logging
            ],
            
            # Performance monitoring (capture 10% of transactions)
            traces_sample_rate=0.1,
            
            # Environment
            environment=os.getenv('FLASK_ENV', 'production'),
            
            # Release tracking (use git commit hash if available)
            release=os.getenv('HEROKU_SLUG_COMMIT', 'unknown'),
            
            # Additional context
            attach_stacktrace=True,
            send_default_pii=False,  # Don't send user data automatically
            
            # Custom tags
            before_send=before_send_handler
        )
        
        logger.info("✅ Sentry initialized successfully")
        logger.info(f"   Environment: {os.getenv('FLASK_ENV', 'production')}")
        logger.info(f"   Release: {os.getenv('HEROKU_SLUG_COMMIT', 'unknown')[:8]}")
        return True
        
    except ImportError:
        logger.error("❌ sentry-sdk not installed")
        logger.error("   Run: pip install sentry-sdk[flask]")
        return False
    except Exception as e:
        logger.error(f"❌ Sentry initialization failed: {e}")
        return False


def before_send_handler(event, hint):
    """
    Filter and enrich events before sending to Sentry
    """
    # Add custom tags
    event.setdefault('tags', {})
    event['tags']['platform'] = 'lemma-iam'
    
    # Filter out noisy errors
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        
        # Don't report common user errors
        if isinstance(exc_value, KeyError) and 'api_key' in str(exc_value):
            # Missing API key is user error, not bug
            return None
        
        # Don't report rate limit errors (expected behavior)
        if 'rate limit' in str(exc_value).lower():
            return None
    
    return event


def capture_exception(exception, context=None):
    """
    Manually capture an exception with additional context
    
    Usage:
        try:
            risky_operation()
        except Exception as e:
            capture_exception(e, {
                'user_email': user_email,
                'site_id': site_id,
                'operation': 'permission_grant'
            })
            raise
    """
    try:
        import sentry_sdk
        
        if context:
            with sentry_sdk.push_scope() as scope:
                for key, value in context.items():
                    scope.set_context(key, value)
                sentry_sdk.capture_exception(exception)
        else:
            sentry_sdk.capture_exception(exception)
            
    except ImportError:
        logger.error(f"Exception occurred but Sentry not available: {exception}")


def capture_message(message, level='info', context=None):
    """
    Capture a message (not an exception) in Sentry
    
    Usage:
        capture_message('Suspicious activity detected', level='warning', context={
            'ip_address': request.remote_addr,
            'attempts': failed_attempts
        })
    """
    try:
        import sentry_sdk
        
        if context:
            with sentry_sdk.push_scope() as scope:
                for key, value in context.items():
                    scope.set_context(key, value)
                sentry_sdk.capture_message(message, level=level)
        else:
            sentry_sdk.capture_message(message, level=level)
            
    except ImportError:
        logger.warning(f"Message: {message} (Sentry not available)")


def set_user_context(user_email=None, user_did=None, site_id=None):
    """
    Set user context for error tracking
    
    Usage:
        set_user_context(
            user_email='user@example.com',
            site_id='site_123'
        )
    """
    try:
        import sentry_sdk
        
        sentry_sdk.set_user({
            'email': user_email,
            'id': user_did,
            'site_id': site_id
        })
        
    except ImportError:
        pass

