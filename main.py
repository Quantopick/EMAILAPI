from flask import Flask, jsonify
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, HtmlContent
import os
import requests

app = Flask(__name__)

SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')  # Example: 'support@forex_bullion.com'

# Replace these with your own
TEMPLATE_PATH = "template.html"

@app.route('/send-emails', methods=['GET'])
def send_emails():
    try:
        # Fetch contacts
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get("https://api.sendgrid.com/v3/marketing/contacts", headers=headers)
        contacts = response.json().get("result", [])

        # Read template and replace placeholders
        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as file:
            template = file.read()

        today = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = int(datetime.utcnow().timestamp())
        html = template.replace("{{TODAY}}", today).replace("{{TIMESTAMP}}", str(timestamp)).replace("{{DATE}}", today)

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        for contact in contacts:
            email = contact.get("email")
            name = contact.get("first_name", "")
            message = Mail(
                from_email=From(SENDER_EMAIL, "Forex_Bullion"),
                to_emails=To(email),
                subject="📊 Daily Forex Signals - Forex_Bullion",
                html_content=HtmlContent(html)
            )
            sg.send(message)

        return jsonify({"message": f"Emails sent to {len(contacts)} contacts."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
