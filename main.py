from flask import Flask, jsonify
import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To
import requests

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__)

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

# Load the email template once when the server starts
with open("template.html", "r", encoding="utf-8") as file:
    EMAIL_TEMPLATE = file.read()

def fetch_contacts():
    """Fetch contacts from SendGrid Marketing API."""
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    url = "https://api.sendgrid.com/v3/marketing/contacts"

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch contacts: {response.text}")
    
    data = response.json()
    return data.get("result", [])

def send_email(to_email, first_name):
    """Send personalized email to a contact."""
    html_content = EMAIL_TEMPLATE.replace("{{ first_name }}", first_name)

    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=To(email=to_email, name=first_name),
        subject="📈 Your Daily Forex Signal Report",
        html_content=html_content
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        return response.status_code
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return None

@app.route("/send-emails", methods=["GET"])
def send_emails():
    try:
        contacts = fetch_contacts()
        results = []
        for contact in contacts:
            email = contact.get("email")
            first_name = contact.get("first_name", "Trader")
            status_code = send_email(email, first_name)
            results.append({"email": email, "status_code": status_code})
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
