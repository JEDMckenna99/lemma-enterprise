"""
Lemma route blueprints for the web application.
"""

from lemma.routes.main import main_bp
from lemma.routes.admin import admin_bp
from lemma.routes.api import api_bp
from lemma.routes.shopify_app import shopify_bp

__all__ = ['main_bp', 'admin_bp', 'api_bp', 'shopify_bp']
