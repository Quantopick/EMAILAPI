from flask import Flask, jsonify
from datetime import datetime, timezone, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, HtmlContent
from dotenv import load_dotenv
import os
import requests
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# Load environment variables locally if .env exists
load_dotenv()

app = Flask(__name__)

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')  # e.g., support@forex_bullion.com
TEMPLATE_PATH = "template.html"

# ✅ UAE Timezone
UAE_TZ = pytz.timezone("Asia/Dubai")

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Email API is working!"}), 200

# ✅ Generic function to send emails with custom subject
def send_emails_with_subject(subject_prefix="📊 Daily Forex Signals - Forex_Bullion"):
    """
    Generic function to send emails with customizable subject
    Returns tuple (success: bool, message: str, count: int)
    """
    try:
        if not SENDGRID_API_KEY or not SENDER_EMAIL:
            return False, "Missing SendGrid API key or sender email.", 0

        # Fetch contacts from SendGrid
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get("https://api.sendgrid.com/v3/marketing/contacts", headers=headers)
        
        if response.status_code != 200:
            return False, f"Failed to fetch contacts: {response.text}", 0

        contacts = response.json().get("result", [])
        if not contacts:
            return True, "No contacts found.", 0

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
        
        # Send emails to all contacts
        for contact in contacts:
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

        return True, f"Emails sent to {len(contacts)} contacts.", len(contacts)
        
    except Exception as e:
        logging.exception("Error occurred during email sending:")
        return False, str(e), 0

@app.route('/send-emails', methods=['GET'])
def send_emails():
    """Original endpoint - maintains backward compatibility"""
    try:
        success, message, count = send_emails_with_subject("🌅 Morning Analysis")
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 500
    except Exception as e:
        logging.exception("Error occurred during email sending:")
        return jsonify({"error": str(e)}), 500

@app.route('/send-evening-emails', methods=['GET'])
def send_evening_emails():
    """New endpoint for evening emails"""
    try:
        success, message, count = send_emails_with_subject("📈 Evening Analysis")
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 500
    except Exception as e:
        logging.exception("Error occurred during evening email sending:")
        return jsonify({"error": str(e)}), 500

# ✅ Function to be called by the morning scheduler
def scheduled_morning_email_job():
    """Morning email job - 10:01 AM"""
    with app.app_context():
        print(f"[{datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S')}] Sending scheduled morning emails...")
        success, message, count = send_emails_with_subject("🌅 Morning Analysis")
        if success:
            print(f"✅ Morning emails sent successfully: {message}")
        else:
            print(f"❌ Morning email error: {message}")

# ✅ Function to be called by the evening scheduler
def scheduled_evening_email_job():
    """Evening email job - 4:25 PM"""
    with app.app_context():
        print(f"[{datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S')}] Sending scheduled evening emails...")
        success, message, count = send_emails_with_subject("🌇 Evening Analysis")
        if success:
            print(f"✅ Evening emails sent successfully: {message}")
        else:
            print(f"❌ Evening email error: {message}")

if __name__ == '__main__':
    # ✅ Scheduler Setup
    scheduler = BackgroundScheduler(timezone=UAE_TZ)
    
    # Morning job runs at 10:01 AM Monday to Friday
    scheduler.add_job(
        scheduled_morning_email_job,
        trigger='cron',
        day_of_week='mon-fri',
        hour=10,
        minute=1,
        id='morning_emails'
    )
    
    # ✅ NEW: Evening job runs at 4:25 PM Monday to Friday  
    scheduler.add_job(
        scheduled_evening_email_job,
        trigger='cron',
        day_of_week='mon-fri',
        hour=16,  # 4 PM in 24-hour format
        minute=0,
        id='evening_emails'
    )
    
    scheduler.start()
    print("📅 Email scheduler started:")
    print("  - Morning emails: Monday-Friday at 10:01 AM UAE time")
    print("  - Evening emails: Monday-Friday at 4:25 PM UAE time")
    
    try:
        app.run(host='0.0.0.0', port=5000)
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Shutting down scheduler...")
        scheduler.shutdown()


