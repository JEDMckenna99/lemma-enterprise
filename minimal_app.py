#!/usr/bin/env python3
"""
Minimal Flask app for debugging Render deployment
"""

import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({
        "status": "ok",
        "message": "Lemma Enterprise - Minimal Test App",
        "environment": {
            "PORT": os.environ.get('PORT', 'not set'),
            "FLASK_ENV": os.environ.get('FLASK_ENV', 'not set'),
            "LEMMA_API_KEY": "SET" if os.environ.get('LEMMA_API_KEY') else "NOT SET",
            "LEMMA_SECRET_KEY": "SET" if os.environ.get('LEMMA_SECRET_KEY') else "NOT SET"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "app": "minimal-lemma-test"})

@app.route('/test')
def test():
    return "Test endpoint working!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 