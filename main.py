from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, HtmlContent
from dotenv import load_dotenv
import os
import requests
import logging
import pytz

# Load environment variables locally if .env exists
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')  # e.g., support@forex_bullion.com
TEMPLATE_PATH = "template.html"

# UAE Timezone
UAE_TZ = pytz.timezone("Asia/Dubai")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Email API is working!", 
        "endpoints": {
            "send_morning_emails": "/send-morning-emails",
            "send_evening_emails": "/send-evening-emails",
            "send_custom_emails": "/send-custom-emails"
        }
    }), 200

# Generic function to send emails with custom subject
def send_emails_with_subject(subject_prefix="📊 Daily Forex Signals - Forex_Bullion"):
    """
    Generic function to send emails with customizable subject
    Returns tuple (success: bool, message: str, count: int)
    """
    try:
        if not SENDGRID_API_KEY or not SENDER_EMAIL:
            logger.error("Missing SendGrid API key or sender email")
            return False, "Missing SendGrid API key or sender email.", 0

        # Fetch contacts from SendGrid
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        logger.info("Fetching contacts from SendGrid...")
        response = requests.get("https://api.sendgrid.com/v3/marketing/contacts", headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch contacts: {response.text}")
            return False, f"Failed to fetch contacts: {response.text}", 0

        contacts = response.json().get("result", [])
        if not contacts:
            logger.info("No contacts found")
            return True, "No contacts found.", 0

        # Check if template file exists
        if not os.path.exists(TEMPLATE_PATH):
            logger.error(f"Template file not found: {TEMPLATE_PATH}")
            return False, f"Template file not found: {TEMPLATE_PATH}", 0

        # Read and render HTML template
        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as file:
            template = file.read()

        now = datetime.now(UAE_TZ)
        today_str = now.strftime('%d %B %Y')  # Example: 28 July 2025
        timestamp = int(now.timestamp())
        
        html = template.replace("{{TODAY}}", today_str)\
                       .replace("{{TIMESTAMP}}", str(timestamp))\
                       .replace("{{DATE}}", today_str)

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        
        logger.info(f"Sending emails to {len(contacts)} contacts...")
        
        # Send emails to all contacts
        sent_count = 0
        for contact in contacts:
            try:
                email = contact.get("email")
                name = contact.get("first_name", "Trader")
                personalized_html = html.replace("{{NAME}}", name)
                
                subject = f"{subject_prefix} - {today_str}"
                
                message = Mail(
                    from_email=From(SENDER_EMAIL, "Forex_Bullion"),
                    to_emails=To(email),
                    subject=subject,
                    html_content=HtmlContent(personalized_html)
                )
                sg.send(message)
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Failed to send email to {email}: {str(e)}")
                continue

        logger.info(f"Successfully sent {sent_count} emails")
        return True, f"Emails sent to {sent_count}/{len(contacts)} contacts.", sent_count
        
    except Exception as e:
        logger.exception("Error occurred during email sending:")
        return False, str(e), 0

@app.route('/send-morning-emails', methods=['POST'])
def send_morning_emails():
    """Endpoint for sending morning emails via button click"""
    try:
        logger.info("Morning email request received")
        success, message, count = send_emails_with_subject("🌅 Morning Analysis - Forex_Bullion")
        
        if success:
            logger.info(f"Morning emails sent successfully: {message}")
            return jsonify({
                "success": True,
                "message": message, 
                "count": count,
                "type": "morning"
            }), 200
        else:
            logger.error(f"Morning email failed: {message}")
            return jsonify({
                "success": False,
                "error": message,
                "type": "morning"
            }), 500
            
    except Exception as e:
        logger.exception("Error occurred during morning email sending:")
        return jsonify({
            "success": False,
            "error": str(e),
            "type": "morning"
        }), 500

@app.route('/send-evening-emails', methods=['POST'])
def send_evening_emails():
    """Endpoint for sending evening emails via button click"""
    try:
        logger.info("Evening email request received")
        success, message, count = send_emails_with_subject("🌙 Evening Analysis - Forex_Bullion")
        
        if success:
            logger.info(f"Evening emails sent successfully: {message}")
            return jsonify({
                "success": True,
                "message": message, 
                "count": count,
                "type": "evening"
            }), 200
        else:
            logger.error(f"Evening email failed: {message}")
            return jsonify({
                "success": False,
                "error": message,
                "type": "evening"
            }), 500
            
    except Exception as e:
        logger.exception("Error occurred during evening email sending:")
        return jsonify({
            "success": False,
            "error": str(e),
            "type": "evening"
        }), 500

@app.route('/send-custom-emails', methods=['POST'])
def send_custom_emails():
    """Endpoint for sending emails with custom subject via button click"""
    try:
        # Get custom subject from request body
        data = request.get_json() or {}
        custom_subject = data.get('subject', '📊 Custom Analysis - Forex_Bullion')
        
        logger.info(f"Custom email request received with subject: {custom_subject}")
        success, message, count = send_emails_with_subject(custom_subject)
        
        if success:
            logger.info(f"Custom emails sent successfully: {message}")
            return jsonify({
                "success": True,
                "message": message, 
                "count": count,
                "type": "custom",
                "subject": custom_subject
            }), 200
        else:
            logger.error(f"Custom email failed: {message}")
            return jsonify({
                "success": False,
                "error": message,
                "type": "custom"
            }), 500
            
    except Exception as e:
        logger.exception("Error occurred during custom email sending:")
        return jsonify({
            "success": False,
            "error": str(e),
            "type": "custom"
        }), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(UAE_TZ).isoformat(),
        "timezone": "Asia/Dubai"
    }), 200

if __name__ == '__main__':
    print("🚀 Email API Server Starting...")
    print("📧 Available endpoints:")
    print("  - POST /send-morning-emails")
    print("  - POST /send-evening-emails") 
    print("  - POST /send-custom-emails")
    print("  - GET /health")
    print("  - GET /")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
