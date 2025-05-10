"""
WSGI entry point for Azure App Service
"""
from app import app

# This is the WSGI entry point that Azure will look for
if __name__ == '__main__':
    app.run()
