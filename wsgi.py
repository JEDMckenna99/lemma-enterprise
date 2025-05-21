"""
WSGI entry point for Heroku deployment
"""
import os
import logging
from lemma import create_app

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the application instance with Heroku-specific settings
logger.info("Starting Lemma Enterprise on Heroku")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Directory contents: {os.listdir(os.getcwd())}")

# Create the application instance
app = create_app()

# Push an application context
ctx = app.app_context()
ctx.push()

# This is the WSGI entry point that Heroku will look for
if __name__ == '__main__':
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Run the application
    app.run(host='0.0.0.0', port=port)
