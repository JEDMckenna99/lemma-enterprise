"""
WSGI entry point for Heroku deployment
"""
import os
import sys
import logging
from lemma import create_app

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

try:
    # Log startup information
    logger.info("Starting Lemma Enterprise on Heroku")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Directory contents: {os.listdir(os.getcwd())}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Environment variables: {[k for k in os.environ.keys() if 'LEMMA' in k or 'STRIPE' in k or 'DID' in k]}")

    # Create the application instance
    app = create_app()
    logger.info("Successfully created Flask application instance")

    # Push an application context
    ctx = app.app_context()
    ctx.push()
    logger.info("Successfully pushed application context")

except Exception as e:
    logger.error(f"Failed to initialize application: {e}", exc_info=True)
    raise

# This is the WSGI entry point that Heroku will look for
if __name__ == '__main__':
    try:
        # Get port from environment or use default
        port = int(os.environ.get('PORT', 5000))
        
        # Run the application
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        logger.error(f"Failed to run application: {e}", exc_info=True)
        raise
