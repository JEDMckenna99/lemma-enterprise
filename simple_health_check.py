#!/usr/bin/env python3
"""
Simple health check app to test Render deployment.
"""

from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "Lemma Enterprise - Health Check OK"

@app.route('/health')
def health():
    return {"status": "ok", "message": "Simple health check working"}

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 