"""
Debug Email System
Simple endpoint to test email functionality and debug issues
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import os
import smtplib
from email.mime.text import MimeText

logger = logging.getLogger(__name__)

debug_email_bp = Blueprint('debug_email', __name__)

@debug_email_bp.route('/api/debug/email-config', methods=['GET'])
@cross_origin()
def debug_email_config():
    """Debug email configuration"""
    try:
        config = {
            'smtp_server': os.getenv('SMTP_SERVER', 'NOT SET'),
            'smtp_port': os.getenv('SMTP_PORT', 'NOT SET'),
            'smtp_username': os.getenv('SMTP_USERNAME', 'NOT SET'),
            'smtp_password_set': 'YES' if os.getenv('SMTP_PASSWORD') else 'NO',
            'mailgun_domain': os.getenv('MAILGUN_DOMAIN', 'NOT SET'),
            'mailgun_api_key_set': 'YES' if os.getenv('MAILGUN_API_KEY') else 'NO'
        }
        
        return jsonify({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        logger.error(f"Debug email config error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@debug_email_bp.route('/api/debug/send-simple-test', methods=['POST'])
@cross_origin()
def send_simple_test():
    """Send simple test email to debug SMTP"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        # Get SMTP config
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        
        if not all([smtp_server, smtp_username, smtp_password]):
            return jsonify({
                'success': False,
                'error': 'SMTP configuration incomplete',
                'config': {
                    'server': smtp_server or 'MISSING',
                    'username': smtp_username or 'MISSING',
                    'password': 'SET' if smtp_password else 'MISSING'
                }
            }), 400
        
        # Try to send simple email
        
        msg = MimeText("This is a simple test email from Lemma IAM system.")
        msg['Subject'] = "Simple Test Email - Lemma IAM"
        msg['From'] = smtp_username
        msg['To'] = email
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        logger.info(f"✅ Simple test email sent to {email}")
        
        return jsonify({
            'success': True,
            'message': f'Simple test email sent to {email}',
            'smtp_config': {
                'server': smtp_server,
                'port': smtp_port,
                'username': smtp_username
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Simple test email failed: {e}")
        return jsonify({
            'success': False,
            'error': f'Email sending failed: {str(e)}',
            'error_type': type(e).__name__
        }), 500
