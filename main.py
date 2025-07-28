from flask import Flask, jsonify
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, HtmlContent
from dotenv import load_dotenv
import os
import requests
import logging

# Load environment variables locally if .env exists
load_dotenv()

app = Flask(__name__)

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')  # e.g., support@forex_bullion.com
TEMPLATE_PATH = "template.html"

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Email API is working!"}), 200

@app.route('/send-emails', methods=['GET'])
def send_emails():
    try:
        if not SENDGRID_API_KEY or not SENDER_EMAIL:
            return jsonify({"error": "Missing SendGrid API key or sender email."}), 500

        # Fetch contacts from SendGrid
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get("https://api.sendgrid.com/v3/marketing/contacts", headers=headers)

        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch contacts", "details": response.text}), 500

        contacts = response.json().get("result", [])
        if not contacts:
            return jsonify({"message": "No contacts found."}), 200

        # Read and render HTML template
        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as file:
            template = file.read()

        today = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = int(datetime.utcnow().timestamp())
        html = template.replace("{{TODAY}}", today).replace("{{TIMESTAMP}}", str(timestamp)).replace("{{DATE}}", today)

        sg = SendGridAPIClient(SENDGRID_API_KEY)

        # Send emails to all contacts
        for contact in contacts:
            email = contact.get("email")
            name = contact.get("first_name", "Trader")

            personalized_html = html.replace("{{NAME}}", name)

            message = Mail(
                from_email=From(SENDER_EMAIL, "Forex_Bullion"),
                to_emails=To(email),
                subject="📊 Daily Forex Signals - Forex_Bullion",
                html_content=HtmlContent(personalized_html)
            )

            sg.send(message)

        return jsonify({"message": f"Emails sent to {len(contacts)} contacts."}), 200

    except Exception as e:
        logging.exception("Error occurred during email sending:")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)


this is my flask api that sends email to clients using sendgrid. i want to automate it using n8n and send emails everyday at 10 am
