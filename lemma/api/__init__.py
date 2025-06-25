# API module for React frontend integration
from flask import Blueprint

def register_api_routes(app):
    """Register all API routes with the Flask app"""
    from lemma.api.v2.auth import auth_api
    from lemma.api.v2.verification import verification_api
    from lemma.api.v2.analytics import analytics_api
    from lemma.api.v2.credentials import credentials_api
    
    app.register_blueprint(auth_api)
    app.register_blueprint(verification_api)
    app.register_blueprint(analytics_api)
    app.register_blueprint(credentials_api) 