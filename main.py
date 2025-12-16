from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime
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
CORS(app)  # Enable CORS for all routes

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')  # e.g., reports@quantopick.com
TEMPLATE_PATH = "template.html"  # Your email template

# ✅ UAE Timezone
UAE_TZ = pytz.timezone("Asia/Dubai")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Email API is running - Automatic daily emails at 10:00 AM UAE time"}), 200

# ✅ Check if sender email is verified
@app.route('/check-sender', methods=['GET'])
def check_sender():
    """Check if sender email is verified in SendGrid"""
    try:
        if not SENDGRID_API_KEY or not SENDER_EMAIL:
            return jsonify({
                "status": "error",
                "message": "Missing SendGrid API key or sender email in .env file"
            }), 400

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Check verified senders
        response = requests.get(
            "https://api.sendgrid.com/v3/verified_senders",
            headers=headers
        )
        
        logger.info(f"🔍 Verified Senders Response Status: {response.status_code}")
        logger.info(f"📋 Response Body: {response.text}")
        
        if response.status_code != 200:
            return jsonify({
                "status": "error",
                "message": f"Failed to fetch verified senders: {response.text}"
            }), response.status_code
        
        senders_data = response.json()
        senders = senders_data.get("results", [])
        
        # Check if our sender email is verified
        is_verified = False
        sender_info = None
        
        for sender in senders:
            if sender.get("from_email") == SENDER_EMAIL:
                # Handle both boolean and dict formats for 'verified' field
                verified_field = sender.get("verified")
                
                # If verified is a boolean directly
                if isinstance(verified_field, bool):
                    is_verified = verified_field
                # If verified is a dict with 'status' key
                elif isinstance(verified_field, dict):
                    is_verified = verified_field.get("status", False)
                else:
                    is_verified = False
                
                sender_info = {
                    "email": sender.get("from_email"),
                    "name": sender.get("from_name"),
                    "verified": is_verified,
                    "created_at": sender.get("created_at"),
                    "reply_to": sender.get("reply_to"),
                    "nickname": sender.get("nickname")
                }
                break
        
        # Get all verified emails
        verified_emails = []
        for s in senders:
            verified_field = s.get("verified")
            is_sender_verified = False
            
            if isinstance(verified_field, bool):
                is_sender_verified = verified_field
            elif isinstance(verified_field, dict):
                is_sender_verified = verified_field.get("status", False)
            
            if is_sender_verified:
                verified_emails.append(s.get("from_email"))
        
        return jsonify({
            "status": "success",
            "sender_email_configured": SENDER_EMAIL,
            "is_verified": is_verified,
            "sender_info": sender_info,
            "all_verified_senders": verified_emails,
            "total_senders": len(senders),
            "message": "✅ Sender is verified! Ready to send emails." if is_verified else f"❌ {SENDER_EMAIL} is NOT verified yet. Please verify it in SendGrid dashboard.",
            "verification_url": "https://app.sendgrid.com/settings/sender_auth/senders"
        }), 200
        
    except Exception as e:
        logger.exception("❌ Error checking sender verification:")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# ✅ Status endpoint to check scheduler
@app.route('/status', methods=['GET'])
def status():
    """Check the status of the email scheduler"""
    try:
        now_uae = datetime.now(UAE_TZ)
        return jsonify({
            "status": "running",
            "message": "Email scheduler is active",
            "current_time_uae": now_uae.strftime('%Y-%m-%d %H:%M:%S %Z'),
            "schedule": "Daily at 10:00 AM UAE time",
            "next_run": "Every day at 10:00 AM Dubai time"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# ✅ Generic function to send emails with custom subject
def send_emails_with_subject(subject_prefix="📊 Daily Forex Signals - Forex_Bullion"):
    """
    Generic function to send emails with customizable subject
    Returns tuple (success: bool, message: str, count: int)
    """
    try:
        if not SENDGRID_API_KEY or not SENDER_EMAIL:
            return False, "Missing SendGrid API key or sender email.", 0

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # 🔍 Try the original GET endpoint first with debug logging
        logger.info("🔍 Attempting to fetch contacts using GET /v3/marketing/contacts...")
        response = requests.get("https://api.sendgrid.com/v3/marketing/contacts", headers=headers)
        
        logger.info(f"📊 GET Response Status: {response.status_code}")
        logger.info(f"📋 GET Response Body: {response.text[:500]}")  # First 500 chars
        
        contacts = []
        
        # If GET fails, try the search API
        if response.status_code != 200:
            logger.warning(f"⚠️ GET request failed with {response.status_code}, trying search API...")
            
            # ✅ Use the search API instead
            search_payload = {
                "query": ""  # Empty query returns all contacts
            }
            
            response = requests.post(
                "https://api.sendgrid.com/v3/marketing/contacts/search",
                headers=headers,
                json=search_payload
            )
            
            logger.info(f"📊 POST Search Response Status: {response.status_code}")
            logger.info(f"📋 POST Search Response Body: {response.text[:500]}")
            
            if response.status_code != 200:
                error_msg = f"Failed to fetch contacts via both methods. GET: {response.status_code}, Search: {response.text}"
                logger.error(f"❌ {error_msg}")
                return False, error_msg, 0
        
        # Parse contacts from response
        contacts = response.json().get("result", [])
        
        if not contacts:
            logger.info("ℹ️ No contacts found in SendGrid.")
            return True, "No contacts found.", 0
        
        logger.info(f"✅ Successfully fetched {len(contacts)} contacts")

        # Read and render HTML template
        try:
            with open(TEMPLATE_PATH, 'r', encoding='utf-8') as file:
                template = file.read()
        except FileNotFoundError:
            error_msg = f"Template file not found: {TEMPLATE_PATH}"
            logger.error(f"❌ {error_msg}")
            return False, error_msg, 0

        now = datetime.now(UAE_TZ)
        today_str = now.strftime('%d %B %Y')  # Example: 16 December 2025
        timestamp = int(now.timestamp())
        
        html = template.replace("{{TODAY}}", today_str)\
                       .replace("{{TIMESTAMP}}", str(timestamp))\
                       .replace("{{DATE}}", today_str)

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        
        # Send emails to all contacts
        logger.info(f"📧 Starting to send emails to {len(contacts)} contacts...")
        sent_count = 0
        failed_emails = []
        
        for contact in contacts:
            try:
                email = contact.get("email")
                name = contact.get("first_name", "Trader")
                personalized_html = html.replace("{{NAME}}", name)
                
                subject = f"{subject_prefix} - {today_str}"
                
                message = Mail(
                    from_email=From(SENDER_EMAIL, "QuantoPick"),
                    to_emails=To(email),
                    subject=subject,
                    html_content=HtmlContent(personalized_html)
                )
                
                response = sg.send(message)
                logger.info(f"✉️ Email sent to {email} - Status: {response.status_code}")
                sent_count += 1
                
            except Exception as email_error:
                error_details = str(email_error)
                logger.error(f"❌ Failed to send email to {email}: {error_details}")
                
                # Get more details from the exception
                if hasattr(email_error, 'body'):
                    error_details = f"{error_details} - Body: {email_error.body}"
                if hasattr(email_error, 'reason'):
                    error_details = f"{error_details} - Reason: {email_error.reason}"
                
                failed_emails.append({
                    "email": email,
                    "error": error_details
                })

        if failed_emails:
            logger.warning(f"⚠️ {len(failed_emails)} emails failed to send")
            logger.error(f"Failed emails details: {failed_emails}")
            
            # Return detailed error information
            return False, f"Sent {sent_count}/{len(contacts)} emails. Failures: {failed_emails}", sent_count

        logger.info(f"✅ All {sent_count} emails sent successfully!")
        return True, f"Emails sent to {sent_count} contacts.", sent_count
        
    except Exception as e:
        logger.exception("❌ Error occurred during email sending:")
        return False, str(e), 0

# ✅ Function to be called by the daily scheduler
def scheduled_daily_email_job():
    """Daily email job - 10:00 AM UAE time"""
    with app.app_context():
        logger.info(f"[{datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S')}] Sending scheduled daily emails...")
        success, message, count = send_emails_with_subject("📊 Daily Forex Signals - Forex_Bullion")
        if success:
            logger.info(f"✅ Daily emails sent successfully: {message}")
        else:
            logger.error(f"❌ Daily email error: {message}")

if __name__ == '__main__':
    # ✅ Scheduler Setup - Daily at 10:00 AM UAE time
    scheduler = BackgroundScheduler(timezone=UAE_TZ)
    
    # Daily job runs at 10:00 AM every day (including weekends)
    scheduler.add_job(
        scheduled_daily_email_job,
        trigger='cron',
        hour=10,
        minute=0,
        id='daily_emails'
    )
    
    scheduler.start()
    print("📅 Email scheduler started:")
    print("  - Daily emails: Every day at 10:00 AM UAE time (including weekends)")
    print("\n🌐 Available endpoints:")
    print("  - Home: http://localhost:5000/")
    print("  - Status: http://localhost:5000/status")
    print("  - Check sender: http://localhost:5000/check-sender")
    print("\n⚠️  Manual email sending has been disabled - emails are automatic only")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Shutting down scheduler...")
        scheduler.shutdown()
