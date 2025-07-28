from flask import Flask, jsonify, request
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, HtmlContent
from dotenv import load_dotenv
import os
import requests
import logging
import traceback

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
TEMPLATE_PATH = "template.html"
AUTH_TOKEN = os.getenv('API_AUTH_TOKEN')  # For securing API endpoint

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Email API is working!", "status": "healthy"}), 200

@app.route('/send-emails', methods=['POST'])
def send_emails():
    try:
        # Authentication check
        if AUTH_TOKEN:
            auth_header = request.headers.get('Authorization')
            if not auth_header or auth_header != f"Bearer {AUTH_TOKEN}":
                logger.warning("Unauthorized access attempt")
                return jsonify({
                    "success": False,
                    "error": "Unauthorized"
                }), 401

        if not SENDGRID_API_KEY or not SENDER_EMAIL:
            logger.error("Missing SendGrid configuration")
            return jsonify({
                "success": False,
                "error": "Missing SendGrid API key or sender email."
            }), 500

        # Fetch contacts from SendGrid
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        logger.info("Fetching contacts from SendGrid")
        response = requests.get(
            "https://api.sendgrid.com/v3/marketing/contacts",
            headers=headers,
            params={"page_size": 1000}
        )

        if response.status_code != 200:
            logger.error(f"Failed to fetch contacts: {response.text}")
            return jsonify({
                "success": False,
                "error": "Failed to fetch contacts",
                "details": response.text
            }), 500

        contacts = response.json().get("result", [])
        if not contacts:
            logger.info("No contacts found to send emails to")
            return jsonify({
                "success": True,
                "message": "No contacts found.",
                "count": 0
            }), 200

        # Read email template
        try:
            with open(TEMPLATE_PATH, 'r', encoding='utf-8') as file:
                template = file.read()
        except Exception as e:
            logger.error(f"Failed to read template: {str(e)}")
            return jsonify({
                "success": False,
                "error": "Failed to read email template",
                "details": str(e)
            }), 500

        today = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = int(datetime.utcnow().timestamp())
        base_html = template.replace("{{TODAY}}", today)\
                           .replace("{{TIMESTAMP}}", str(timestamp))\
                           .replace("{{DATE}}", today)

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        success_count = 0
        failure_count = 0
        failed_emails = []

        # Send emails to all contacts
        for contact in contacts:
            email = contact.get("email")
            if not email:
                continue

            name = contact.get("first_name", "Trader")
            personalized_html = base_html.replace("{{NAME}}", name)

            message = Mail(
                from_email=From(SENDER_EMAIL, "Forex_Bullion"),
                to_emails=To(email),
                subject="📊 Daily Forex Signals - Forex_Bullion",
                html_content=HtmlContent(personalized_html)
            )

            try:
                response = sg.send(message)
                if response.status_code == 202:
                    success_count += 1
                else:
                    failure_count += 1
                    failed_emails.append({
                        "email": email,
                        "error": f"SendGrid returned status {response.status_code}"
                    })
                    logger.warning(f"Failed to send to {email}: {response.status_code}")
            except Exception as e:
                failure_count += 1
                failed_emails.append({
                    "email": email,
                    "error": str(e)
                })
                logger.error(f"Error sending to {email}: {str(e)}")

        # Prepare response
        response_data = {
            "success": True,
            "message": f"Email sending completed. Success: {success_count}, Failures: {failure_count}",
            "stats": {
                "total_contacts": len(contacts),
                "success_count": success_count,
                "failure_count": failure_count,
                "failed_emails": failed_emails if failed_emails else None
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Email sending completed. Success: {success_count}, Failures: {failure_count}")
        return jsonify(response_data), 200

    except Exception as e:
        logger.exception("Critical error occurred during email sending")
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
