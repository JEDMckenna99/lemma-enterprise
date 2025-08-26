"""
Lemma Demo Site - Federated Identity Network Demonstration
A simple Flask app to showcase cross-site authentication capabilities
"""

from flask import Flask, render_template_string, request, redirect, url_for
import os

    app = Flask(__name__)
    
# Simple HTML template for serving our index.html
@app.route('/')
def home():
    """Serve the main demo page"""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        return """
        <h1>Lemma Demo Site</h1>
        <p>Demo site is being set up. Please check back in a moment.</p>
        <p><a href="https://lemma.id">Visit Main Lemma Site</a></p>
        """

@app.route('/verified')
def verified():
    """Handle Stripe Identity verification return"""
    return redirect('/?verified=true')

@app.route('/health')
    def health():
    """Health check endpoint for Heroku"""
    return {'status': 'healthy', 'site': 'lemma-demo'}

@app.route('/api/status')
def api_status():
    """API status endpoint"""
    return {
        'status': 'active',
        'site': 'lemma-demo',
        'federated_network': True,
        'lemma_integration': True
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 