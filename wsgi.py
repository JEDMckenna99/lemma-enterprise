"""
WSGI entry point for Heroku deployment
"""
from app import app

# This is the WSGI entry point that Heroku will look for
if __name__ == '__main__':
    # Get port from environment or use default
    import os
    port = int(os.environ.get('PORT', 5000))
    
    # Run the application
    app.run(host='0.0.0.0', port=port)
