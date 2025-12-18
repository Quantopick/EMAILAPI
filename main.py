from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, HtmlContent
from dotenv import load_dotenv
import os
import requests
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import traceback
import atexit
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)

# ===========================
# IMPROVED CORS CONFIGURATION
# ===========================

# Define allowed origins
ALLOWED_ORIGINS = [
    "https://quantopick.com",
    "https://www.quantopick.com",
    "http://localhost:3000",
    "http://localhost:5000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5000"
]

# Configure CORS with explicit settings
CORS(app, 
     resources={
         r"/*": {
             "origins": ALLOWED_ORIGINS,
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization", "X-API-Key", "Accept"],
             "expose_headers": ["Content-Type"],
             "supports_credentials": True,
             "max_age": 3600
         }
     }
)

# Additional CORS headers for all responses
@app.after_request
def after_request(response):
    """Add comprehensive CORS headers to all responses"""
    origin = request.headers.get('Origin')
    
    # Check if origin is allowed
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
    else:
        # For security, still allow the request but log it
        logger.warning(f"Request from non-whitelisted origin: {origin}")
        if origin:
            response.headers['Access-Control-Allow-Origin'] = origin
    
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, Accept'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age'] = '3600'
    
    # Prevent caching of CORS preflight
    if request.method == 'OPTIONS':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    
    return response

# Explicit OPTIONS handler for all routes
@app.route('/', methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path=None):
    """Handle preflight OPTIONS requests"""
    response = jsonify({'status': 'ok'})
    return response, 200

# Configuration
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
ALERT_EMAIL = os.getenv('ALERT_EMAIL')
TEMPLATE_PATH = os.getenv('TEMPLATE_PATH', 'template.html')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
ENABLE_MONITORING = os.getenv('ENABLE_MONITORING', 'true').lower() == 'true'
MONITORING_INTERVAL_HOURS = int(os.getenv('MONITORING_INTERVAL_HOURS', '6'))

# UAE Timezone
UAE_TZ = pytz.timezone("Asia/Dubai")

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Global variable to track last execution
last_execution = {
    "timestamp": None,
    "status": "Not started",
    "message": "",
    "emails_sent": 0,
    "error": None
}

# Global variable to track monitoring status
monitoring_status = {
    "last_check": None,
    "status": "Not started",
    "issues_found": [],
    "checks_passed": 0,
    "checks_failed": 0
}

# Global variable to store current schedule configuration
schedule_config = {
    "hour": 10,
    "minute": 0,
    "last_updated": None,
    "updated_by": "system"
}

# Config file path
CONFIG_FILE = 'schedule_config.json'

# ===========================
# CONFIGURATION MANAGEMENT
# ===========================

def load_schedule_config():
    """Load schedule configuration from file"""
    global schedule_config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                loaded_config = json.load(f)
                schedule_config.update(loaded_config)
                logger.info(f"✅ Loaded schedule config: {schedule_config['hour']:02d}:{schedule_config['minute']:02d}")
        else:
            logger.info("ℹ️ No config file found, using default schedule (10:00 AM)")
            save_schedule_config()
    except Exception as e:
        logger.error(f"❌ Error loading schedule config: {e}")

def save_schedule_config():
    """Save schedule configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(schedule_config, f, indent=2)
        logger.info(f"✅ Saved schedule config: {schedule_config['hour']:02d}:{schedule_config['minute']:02d}")
    except Exception as e:
        logger.error(f"❌ Error saving schedule config: {e}")

# ===========================
# ERROR NOTIFICATION SYSTEM
# ===========================

def send_error_notification(error_type, error_message, additional_info=None):
    """Send email notification when an error occurs"""
    try:
        if not ALERT_EMAIL:
            logger.warning("⚠️ No ALERT_EMAIL configured - cannot send error notification")
            return False
            
        if not SENDGRID_API_KEY or not SENDER_EMAIL:
            logger.error("❌ Cannot send error notification - missing SendGrid config")
            return False
        
        now_uae = datetime.now(UAE_TZ)
        
        # Determine severity color
        severity_colors = {
            "API Started": "#28a745",
            "Schedule Updated": "#17a2b8",
            "Health Monitoring Alert": "#ffc107",
            "Partial Email Failure": "#fd7e14",
            "Configuration Error": "#dc3545",
            "Contact Fetch Error": "#dc3545",
            "Template Error": "#dc3545",
            "Critical Error": "#dc3545",
            "Monitoring Exception": "#dc3545",
            "Scheduler Exception": "#dc3545",
            "Email Sent Successfully": "#28a745",
            "Email Delivery Status": "#17a2b8"
        }
        
        bg_color = severity_colors.get(error_type, "#dc3545")
        is_success = error_type in ["API Started", "Schedule Updated", "Email Sent Successfully"]
        icon = "✅" if is_success else "🚨"
        
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: {bg_color}; color: white; padding: 20px; border-radius: 5px; }}
                .content {{ background: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
                .error-box {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 15px 0; }}
                .success-box {{ background: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 15px 0; }}
                .info {{ background: white; padding: 15px; margin: 10px 0; border-radius: 3px; }}
                .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{icon} {error_type}</h2>
                    <p>QuantoPick Email Scheduler</p>
                </div>
                
                <div class="content">
                    <h3>Notification Details</h3>
                    <div class="{'success-box' if is_success else 'error-box'}">
                        <strong>Type:</strong> {error_type}<br>
                        <strong>Time:</strong> {now_uae.strftime('%Y-%m-%d %H:%M:%S %Z')}<br>
                        <strong>Environment:</strong> {ENVIRONMENT}
                    </div>
                    
                    <div class="info">
                        <strong>Message:</strong>
                        <pre style="white-space: pre-wrap; word-wrap: break-word;">{error_message}</pre>
                    </div>
                    
                    {f'<div class="info"><strong>Additional Information:</strong><pre>{additional_info}</pre></div>' if additional_info else ''}
                    
                    <div class="info">
                        <strong>Current Schedule:</strong> {schedule_config['hour']:02d}:{schedule_config['minute']:02d} Dubai Time<br>
                        <strong>Last Successful Run:</strong> {last_execution.get('timestamp', 'Never')}<br>
                        <strong>Emails Sent in Last Run:</strong> {last_execution.get('emails_sent', 0)}
                    </div>
                </div>
                
                <div class="footer">
                    <p>This is an automated alert from QuantoPick Email API</p>
                    <p>Please check the logs and address the issue if needed.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        message = Mail(
            from_email=From(SENDER_EMAIL, "QuantoPick Alert System"),
            to_emails=To(ALERT_EMAIL),
            subject=f"{icon} {error_type} - QuantoPick Email API",
            html_content=HtmlContent(error_html)
        )
        
        response = sg.send(message)
        logger.info(f"✅ Notification sent to {ALERT_EMAIL} - Status: {response.status_code}")
        return True
        
    except Exception as e:
        logger.exception(f"❌ Failed to send notification: {str(e)}")
        return False

# ===========================
# MONITORING FUNCTIONS
# ===========================

def check_sendgrid_config():
    """Check if SendGrid is properly configured"""
    issues = []
    
    if not SENDGRID_API_KEY:
        issues.append("SendGrid API key not configured")
    
    if not SENDER_EMAIL:
        issues.append("Sender email not configured")
    
    if not os.path.exists(TEMPLATE_PATH):
        issues.append(f"Template file not found: {TEMPLATE_PATH}")
    
    # Check sender verification
    try:
        if SENDGRID_API_KEY and SENDER_EMAIL:
            headers = {
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json"
            }
            response = requests.get(
                "https://api.sendgrid.com/v3/verified_senders",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                senders = response.json().get("results", [])
                is_verified = False
                
                for sender in senders:
                    if sender.get("from_email") == SENDER_EMAIL:
                        verified_field = sender.get("verified")
                        if isinstance(verified_field, bool):
                            is_verified = verified_field
                        elif isinstance(verified_field, dict):
                            is_verified = verified_field.get("status", False)
                        break
                
                if not is_verified:
                    issues.append(f"Sender email {SENDER_EMAIL} is not verified in SendGrid")
            else:
                issues.append(f"Failed to verify sender status: HTTP {response.status_code}")
    except Exception as e:
        issues.append(f"Error checking sender verification: {str(e)}")
    
    return issues

def check_last_execution_status():
    """Check if the last execution was successful and recent"""
    issues = []
    
    if not last_execution.get('timestamp'):
        issues.append("No email executions recorded yet")
        return issues
    
    # Check if last execution failed
    if last_execution.get('status') == 'Failed':
        issues.append(f"Last execution failed: {last_execution.get('error', 'Unknown error')}")
    
    # Check if last execution was too long ago (more than 25 hours)
    try:
        last_time_str = last_execution.get('timestamp')
        if last_time_str:
            last_time = datetime.strptime(last_time_str.rsplit(' ', 1)[0], '%Y-%m-%d %H:%M:%S')
            last_time = UAE_TZ.localize(last_time)
            
            now = datetime.now(UAE_TZ)
            time_diff = now - last_time
            
            if time_diff > timedelta(hours=25):
                issues.append(f"No email sent in last 25 hours (last: {last_time_str})")
    except Exception as e:
        issues.append(f"Error parsing last execution timestamp: {str(e)}")
    
    return issues

def check_sendgrid_contacts():
    """Check if there are contacts in SendGrid"""
    issues = []
    
    try:
        if not SENDGRID_API_KEY:
            return ["SendGrid API key not configured"]
        
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(
            "https://api.sendgrid.com/v3/marketing/contacts",
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            search_payload = {"query": ""}
            response = requests.post(
                "https://api.sendgrid.com/v3/marketing/contacts/search",
                headers=headers,
                json=search_payload,
                timeout=10
            )
        
        if response.status_code == 200:
            contacts = response.json().get("result", [])
            if len(contacts) == 0:
                issues.append("No contacts found in SendGrid - emails won't be sent")
        else:
            issues.append(f"Failed to fetch contacts: HTTP {response.status_code}")
    except Exception as e:
        issues.append(f"Error checking contacts: {str(e)}")
    
    return issues

def run_health_monitoring():
    """Run comprehensive health monitoring"""
    try:
        now_uae = datetime.now(UAE_TZ)
        logger.info(f"🔍 [{now_uae.strftime('%Y-%m-%d %H:%M:%S')}] Running health monitoring...")
        
        all_issues = []
        checks_passed = 0
        checks_failed = 0
        
        logger.info("1️⃣ Checking SendGrid configuration...")
        config_issues = check_sendgrid_config()
        if config_issues:
            all_issues.extend(config_issues)
            checks_failed += 1
            logger.warning(f"  ⚠️ Found {len(config_issues)} configuration issue(s)")
        else:
            checks_passed += 1
            logger.info("  ✅ SendGrid configuration OK")
        
        logger.info("2️⃣ Checking last execution status...")
        exec_issues = check_last_execution_status()
        if exec_issues:
            all_issues.extend(exec_issues)
            checks_failed += 1
            logger.warning(f"  ⚠️ Found {len(exec_issues)} execution issue(s)")
        else:
            checks_passed += 1
            logger.info("  ✅ Last execution OK")
        
        logger.info("3️⃣ Checking SendGrid contacts...")
        contact_issues = check_sendgrid_contacts()
        if contact_issues:
            all_issues.extend(contact_issues)
            checks_failed += 1
            logger.warning(f"  ⚠️ Found {len(contact_issues)} contact issue(s)")
        else:
            checks_passed += 1
            logger.info("  ✅ Contacts check OK")
        
        monitoring_status["last_check"] = now_uae.strftime('%Y-%m-%d %H:%M:%S %Z')
        monitoring_status["issues_found"] = all_issues
        monitoring_status["checks_passed"] = checks_passed
        monitoring_status["checks_failed"] = checks_failed
        monitoring_status["status"] = "Healthy" if not all_issues else "Issues Found"
        
        if all_issues:
            logger.warning(f"⚠️ Monitoring found {len(all_issues)} issue(s)")
            issue_summary = "\n".join(f"• {issue}" for issue in all_issues)
            send_error_notification(
                "Health Monitoring Alert",
                f"Found {len(all_issues)} issue(s) during health check",
                issue_summary
            )
        else:
            logger.info(f"✅ Health monitoring passed all checks ({checks_passed} checks)")
        
        return all_issues
        
    except Exception as e:
        error_msg = f"Error during health monitoring: {str(e)}"
        error_trace = traceback.format_exc()
        logger.exception(f"❌ {error_msg}")
        
        monitoring_status["last_check"] = datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
        monitoring_status["status"] = "Error"
        monitoring_status["issues_found"] = [error_msg]
        
        send_error_notification("Monitoring Exception", error_msg, error_trace)
        return [error_msg]

def scheduled_monitoring_job():
    """Scheduled monitoring job that runs periodically"""
    if not ENABLE_MONITORING:
        logger.info("📊 Monitoring is disabled")
        return
    
    with app.app_context():
        logger.info("📊 Running scheduled health monitoring...")
        run_health_monitoring()

# ===========================
# ROUTES
# ===========================

@app.route('/', methods=['GET'])
def home():
    now_uae = datetime.now(UAE_TZ)
    return jsonify({
        "message": "Email API is working!",
        "status": "active",
        "schedule": f"Daily at {schedule_config['hour']:02d}:{schedule_config['minute']:02d} UAE time",
        "current_time_uae": now_uae.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "environment": ENVIRONMENT,
        "monitoring_enabled": ENABLE_MONITORING,
        "last_execution": last_execution,
        "monitoring_status": monitoring_status if ENABLE_MONITORING else None,
        "schedule_config": schedule_config,
        "cors_enabled": True,
        "allowed_origins": ALLOWED_ORIGINS
    }), 200

@app.route('/cors-test', methods=['GET'])
def cors_test():
    """Simple endpoint to test CORS configuration"""
    return jsonify({
        "status": "success",
        "message": "CORS is working!",
        "origin": request.headers.get('Origin', 'Unknown'),
        "timestamp": datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for monitoring"""
    now_uae = datetime.now(UAE_TZ)
    
    health_status = {
        "status": "healthy",
        "timestamp": now_uae.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "checks": {
            "sendgrid_configured": bool(SENDGRID_API_KEY),
            "sender_email_configured": bool(SENDER_EMAIL),
            "alert_email_configured": bool(ALERT_EMAIL),
            "template_exists": os.path.exists(TEMPLATE_PATH),
            "monitoring_enabled": ENABLE_MONITORING
        },
        "scheduler": {
            "next_run": f"Daily at {schedule_config['hour']:02d}:{schedule_config['minute']:02d} Dubai time",
            "last_execution": last_execution,
            "current_schedule": schedule_config
        },
        "monitoring": monitoring_status if ENABLE_MONITORING else None
    }
    
    if not all([SENDGRID_API_KEY, SENDER_EMAIL]):
        health_status["status"] = "degraded"
        health_status["warning"] = "Missing critical configuration"
    
    if ENABLE_MONITORING and monitoring_status.get("issues_found"):
        health_status["status"] = "degraded"
        health_status["warning"] = f"Monitoring found {len(monitoring_status['issues_found'])} issue(s)"
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code

@app.route('/get-schedule', methods=['GET'])
def get_schedule():
    """Get current schedule configuration"""
    return jsonify({
        "status": "success",
        "schedule": schedule_config,
        "schedule_string": f"{schedule_config['hour']:02d}:{schedule_config['minute']:02d}",
        "timezone": "Asia/Dubai"
    }), 200

@app.route('/update-schedule', methods=['POST'])
def update_schedule():
    """Update email schedule time"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "No data provided"
            }), 400
        
        hour = data.get('hour')
        minute = data.get('minute')
        updated_by = data.get('updated_by', 'web_interface')
        
        if hour is None or minute is None:
            return jsonify({
                "status": "error",
                "message": "Both hour and minute are required"
            }), 400
        
        try:
            hour = int(hour)
            minute = int(minute)
        except ValueError:
            return jsonify({
                "status": "error",
                "message": "Hour and minute must be valid numbers"
            }), 400
        
        if not (0 <= hour <= 23):
            return jsonify({
                "status": "error",
                "message": "Hour must be between 0 and 23"
            }), 400
        
        if not (0 <= minute <= 59):
            return jsonify({
                "status": "error",
                "message": "Minute must be between 0 and 59"
            }), 400
        
        old_schedule = f"{schedule_config['hour']:02d}:{schedule_config['minute']:02d}"
        new_schedule = f"{hour:02d}:{minute:02d}"
        
        schedule_config['hour'] = hour
        schedule_config['minute'] = minute
        schedule_config['last_updated'] = datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
        schedule_config['updated_by'] = updated_by
        
        save_schedule_config()
        reschedule_daily_job(hour, minute)
        
        logger.info(f"✅ Schedule updated from {old_schedule} to {new_schedule} by {updated_by}")
        
        send_error_notification(
            "Schedule Updated",
            f"Email schedule has been successfully updated from {old_schedule} to {new_schedule} Dubai Time",
            f"Updated by: {updated_by}\nNew schedule: Daily at {new_schedule} Dubai Time\nEffective immediately"
        )
        
        return jsonify({
            "status": "success",
            "message": f"Schedule updated successfully to {new_schedule} Dubai Time",
            "old_schedule": old_schedule,
            "new_schedule": new_schedule,
            "schedule_config": schedule_config
        }), 200
        
    except Exception as e:
        error_msg = f"Error updating schedule: {str(e)}"
        error_trace = traceback.format_exc()
        logger.exception(f"❌ {error_msg}")
        
        send_error_notification("Schedule Update Failed", error_msg, error_trace)
        
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 500

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
        
        response = requests.get(
            "https://api.sendgrid.com/v3/verified_senders",
            headers=headers
        )
        
        logger.info(f"🔍 Verified Senders Response Status: {response.status_code}")
        
        if response.status_code != 200:
            return jsonify({
                "status": "error",
                "message": f"Failed to fetch verified senders: {response.text}"
            }), response.status_code
        
        senders_data = response.json()
        senders = senders_data.get("results", [])
        
        is_verified = False
        sender_info = None
        
        for sender in senders:
            if sender.get("from_email") == SENDER_EMAIL:
                verified_field = sender.get("verified")
                
                if isinstance(verified_field, bool):
                    is_verified = verified_field
                elif isinstance(verified_field, dict):
                    is_verified = verified_field.get("status", False)
                
                sender_info = {
                    "email": sender.get("from_email"),
                    "name": sender.get("from_name"),
                    "verified": is_verified,
                    "created_at": sender.get("created_at")
                }
                break
        
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
            "message": "✅ Sender is verified!" if is_verified else f"❌ {SENDER_EMAIL} is NOT verified",
            "verification_url": "https://app.sendgrid.com/settings/sender_auth/senders"
        }), 200
        
    except Exception as e:
        logger.exception("❌ Error checking sender verification:")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/status', methods=['GET'])
def status():
    """Detailed status of the email scheduler"""
    try:
        now_uae = datetime.now(UAE_TZ)
        return jsonify({
            "status": "running",
            "message": "Email scheduler is active",
            "current_time_uae": now_uae.strftime('%Y-%m-%d %H:%M:%S %Z'),
            "schedule": f"Daily at {schedule_config['hour']:02d}:{schedule_config['minute']:02d} UAE time",
            "schedule_config": schedule_config,
            "last_execution": last_execution,
            "monitoring": {
                "enabled": ENABLE_MONITORING,
                "interval_hours": MONITORING_INTERVAL_HOURS if ENABLE_MONITORING else None,
                "status": monitoring_status if ENABLE_MONITORING else None
            },
            "configuration": {
                "sendgrid_configured": bool(SENDGRID_API_KEY),
                "sender_email": SENDER_EMAIL,
                "alert_email": ALERT_EMAIL if ALERT_EMAIL else "Not configured",
                "template_path": TEMPLATE_PATH,
                "environment": ENVIRONMENT
            }
        }), 200
    except Exception as e:
        logger.exception("❌ Error in status endpoint:")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/monitor', methods=['POST'])
def manual_monitor():
    """Manually trigger health monitoring"""
    try:
        logger.info("🔧 Manual monitoring triggered...")
        issues = run_health_monitoring()
        
        return jsonify({
            "status": "success" if not issues else "issues_found",
            "timestamp": datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z'),
            "checks_passed": monitoring_status.get("checks_passed", 0),
            "checks_failed": monitoring_status.get("checks_failed", 0),
            "issues": issues
        }), 200 if not issues else 207
        
    except Exception as e:
        logger.exception("❌ Error in manual monitoring:")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/trigger-test', methods=['POST'])
def trigger_test():
    """Manual trigger for testing - requires API key in header for security"""
    try:
        api_key = request.headers.get('X-API-Key')
        expected_key = os.getenv('MANUAL_TRIGGER_KEY', 'test-key-12345')
        
        if api_key != expected_key:
            return jsonify({
                "status": "error",
                "message": "Unauthorized - Invalid API key"
            }), 401
        
        logger.info("🔧 Manual trigger initiated...")
        success, message, count = send_emails_with_subject("🧪 TEST - Daily Forex Signals")
        
        return jsonify({
            "status": "success" if success else "error",
            "message": message,
            "emails_sent": count,
            "timestamp": datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
        }), 200 if success else 500
        
    except Exception as e:
        logger.exception("❌ Error in manual trigger:")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/last-execution', methods=['GET'])
def get_last_execution():
    """Get details of the last execution"""
    return jsonify({
        "last_execution": last_execution,
        "current_time_uae": datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
    }), 200

@app.route('/monitoring-report', methods=['GET'])
def monitoring_report():
    """Get comprehensive monitoring report"""
    if not ENABLE_MONITORING:
        return jsonify({
            "status": "disabled",
            "message": "Monitoring is not enabled"
        }), 200
    
    return jsonify({
        "monitoring_enabled": ENABLE_MONITORING,
        "monitoring_status": monitoring_status,
        "last_execution": last_execution,
        "schedule_config": schedule_config,
        "configuration": {
            "monitoring_interval_hours": MONITORING_INTERVAL_HOURS,
            "alert_email": ALERT_EMAIL if ALERT_EMAIL else "Not configured",
            "environment": ENVIRONMENT
        },
        "current_time_uae": datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
    }), 200

# ===========================
# EMAIL SENDING LOGIC
# ===========================

def send_emails_with_subject(subject_prefix="📊 Daily Forex Signals - Forex_Bullion"):
    """Generic function to send emails with customizable subject"""
    try:
        logger.info(f"📧 Starting email send process with subject: {subject_prefix}")
        
        if not SENDGRID_API_KEY or not SENDER_EMAIL:
            error_msg = "Missing SendGrid API key or sender email"
            logger.error(f"❌ {error_msg}")
            send_error_notification("Configuration Error", error_msg)
            return False, error_msg, 0

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        logger.info("🔍 Fetching contacts from SendGrid...")
        
        response = requests.get("https://api.sendgrid.com/v3/marketing/contacts", headers=headers)
        logger.info(f"📊 GET Response Status: {response.status_code}")
        
        contacts = []
        
        if response.status_code != 200:
            logger.warning(f"⚠️ GET request failed, trying search API...")
            search_payload = {"query": ""}
            response = requests.post(
                "https://api.sendgrid.com/v3/marketing/contacts/search",
                headers=headers,
                json=search_payload
            )
            logger.info(f"📊 POST Search Response Status: {response.status_code}")
            
            if response.status_code != 200:
                error_msg = f"Failed to fetch contacts. Status: {response.status_code}, Response: {response.text}"
                logger.error(f"❌ {error_msg}")
                send_error_notification("Contact Fetch Error", error_msg, f"Response: {response.text[:500]}")
                return False, error_msg, 0
        
        contacts = response.json().get("result", [])
        
        if not contacts:
            logger.warning("ℹ️ No contacts found in SendGrid")
            return True, "No contacts found", 0
        
        logger.info(f"✅ Successfully fetched {len(contacts)} contacts")

        try:
            with open(TEMPLATE_PATH, 'r', encoding='utf-8') as file:
                template = file.read()
            logger.info(f"✅ Template loaded from {TEMPLATE_PATH}")
        except FileNotFoundError:
            error_msg = f"Template file not found: {TEMPLATE_PATH}"
            logger.error(f"❌ {error_msg}")
            send_error_notification("Template Error", error_msg, f"Expected path: {os.path.abspath(TEMPLATE_PATH)}")
            return False, error_msg, 0

        now = datetime.now(UAE_TZ)
        today_str = now.strftime('%d %B %Y')
        timestamp = int(now.timestamp())
        
        html = template.replace("{{TODAY}}", today_str)\
                       .replace("{{TIMESTAMP}}", str(timestamp))\
                       .replace("{{DATE}}", today_str)

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        
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
                
                if hasattr(email_error, 'body'):
                    error_details = f"{error_details} - Body: {email_error.body}"
                
                failed_emails.append({
                    "email": email,
                    "error": error_details
                })

        if failed_emails:
            logger.warning(f"⚠️ {len(failed_emails)} emails failed to send")
            error_summary = f"Sent {sent_count}/{len(contacts)} emails"
            send_error_notification(
                "Partial Email Failure",
                error_summary,
                f"Failed emails: {failed_emails}"
            )
            return False, f"{error_summary}. Failures: {failed_emails}", sent_count

        logger.info(f"✅ All {sent_count} emails sent successfully!")
        
        send_error_notification(
            "Email Sent Successfully",
            f"Successfully sent {sent_count} emails to subscribers",
            f"Subject: {subject_prefix}\nContacts: {sent_count}\nTime: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        
        return True, f"Emails sent to {sent_count} contacts", sent_count
        
    except Exception as e:
        error_msg = f"Critical error during email sending: {str(e)}"
        error_trace = traceback.format_exc()
        logger.exception(f"❌ {error_msg}")
        send_error_notification("Critical Error", error_msg, error_trace)
        return False, error_msg, 0

# ===========================
# SCHEDULED JOB
# ===========================

def scheduled_daily_email_job():
    """Daily email job - runs at configured time in UAE timezone"""
    try:
        now_uae = datetime.now(UAE_TZ)
        logger.info(f"⏰ [{now_uae.strftime('%Y-%m-%d %H:%M:%S %Z')}] Starting scheduled daily email job...")
        
        last_execution["timestamp"] = now_uae.strftime('%Y-%m-%d %H:%M:%S %Z')
        last_execution["status"] = "Running"
        
        with app.app_context():
            success, message, count = send_emails_with_subject("📊 Daily Forex Signals - Forex_Bullion")
            
            last_execution["status"] = "Success" if success else "Failed"
            last_execution["message"] = message
            last_execution["emails_sent"] = count
            last_execution["error"] = None if success else message
            
            if success:
                logger.info(f"✅ Daily emails sent successfully: {message}")
            else:
                logger.error(f"❌ Daily email job failed: {message}")
        
    except Exception as e:
        error_msg = f"Scheduler job exception: {str(e)}"
        error_trace = traceback.format_exc()
        logger.exception(f"❌ {error_msg}")
        
        last_execution["status"] = "Error"
        last_execution["error"] = error_msg
        last_execution["timestamp"] = datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
        
        send_error_notification("Scheduler Exception", error_msg, error_trace)

# ===========================
# SCHEDULER SETUP
# ===========================

scheduler = BackgroundScheduler(timezone=UAE_TZ)

def reschedule_daily_job(hour, minute):
    """Reschedule the daily email job with new time"""
    try:
        if scheduler.get_job('daily_emails'):
            scheduler.remove_job('daily_emails')
            logger.info("🔄 Removed existing daily email job")
        
        scheduler.add_job(
            scheduled_daily_email_job,
            trigger='cron',
            hour=hour,
            minute=minute,
            id='daily_emails',
            name='Daily Email Job',
            replace_existing=True
        )
        
        logger.info(f"✅ Rescheduled daily email job to {hour:02d}:{minute:02d} UAE time")
        
    except Exception as e:
        logger.error(f"❌ Error rescheduling job: {e}")
        raise

load_schedule_config()

scheduler.add_job(
    scheduled_daily_email_job,
    trigger='cron',
    hour=schedule_config['hour'],
    minute=schedule_config['minute'],
    id='daily_emails',
    name='Daily Email Job',
    replace_existing=True
)

if ENABLE_MONITORING:
    scheduler.add_job(
        scheduled_monitoring_job,
        trigger='interval',
        hours=MONITORING_INTERVAL_HOURS,
        id='health_monitoring',
        name='Health Monitoring Job',
        replace_existing=True
    )
    logger.info(f"📊 Monitoring job scheduled every {MONITORING_INTERVAL_HOURS} hours")

scheduler.start()
logger.info("📅 Email scheduler started successfully")
logger.info(f"  - Daily emails: Every day at {schedule_config['hour']:02d}:{schedule_config['minute']:02d} UAE time")
if ENABLE_MONITORING:
    logger.info(f"  - Health monitoring: Every {MONITORING_INTERVAL_HOURS} hours")

atexit.register(lambda: scheduler.shutdown())

# ===========================
# MAIN
# ===========================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("📅 EMAIL SCHEDULER STARTED")
    print("="*60)
    print(f"Environment: {ENVIRONMENT}")
    print(f"Schedule: Daily at {schedule_config['hour']:02d}:{schedule_config['minute']:02d} UAE time")
    print(f"Monitoring: {'Enabled' if ENABLE_MONITORING else 'Disabled'}")
    if ENABLE_MONITORING:
        print(f"Monitoring Interval: Every {MONITORING_INTERVAL_HOURS} hours")
    print(f"Current time: {datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("\n🌐 Available endpoints:")
    print("  - Home:            GET  /")
    print("  - CORS Test:       GET  /cors-test")
    print("  - Health:          GET  /health")
    print("  - Status:          GET  /status")
    print("  - Get schedule:    GET  /get-schedule")
    print("  - Update schedule: POST /update-schedule")
    print("  - Check sender:    GET  /check-sender")
    print("  - Last execution:  GET  /last-execution")
    print("  - Manual trigger:  POST /trigger-test (requires X-API-Key header)")
    if ENABLE_MONITORING:
        print("  - Manual monitor:  POST /monitor")
        print("  - Monitor report:  GET  /monitoring-report")
    print("\n📧 Configuration:")
    print(f"  - Sender: {SENDER_EMAIL}")
    print(f"  - Alert Email: {ALERT_EMAIL if ALERT_EMAIL else 'Not configured'}")
    print(f"  - Template: {TEMPLATE_PATH}")
    print(f"\n🔒 CORS Configuration:")
    print(f"  - Enabled: Yes")
    print(f"  - Allowed Origins: {len(ALLOWED_ORIGINS)}")
    for origin in ALLOWED_ORIGINS:
        print(f"    • {origin}")
    print("="*60 + "\n")
    
    try:
        if ALERT_EMAIL:
            send_error_notification(
                "API Started",
                f"Email API has been started successfully at {datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}",
                f"Environment: {ENVIRONMENT}\nSchedule: Daily at {schedule_config['hour']:02d}:{schedule_config['minute']:02d} UAE time\nMonitoring: {'Enabled' if ENABLE_MONITORING else 'Disabled'}\nCORS: Enabled"
            )
    except Exception as e:
        logger.warning(f"Could not send startup notification: {e}")
    
    if ENABLE_MONITORING:
        try:
            logger.info("🔍 Running initial health check...")
            run_health_monitoring()
        except Exception as e:
            logger.warning(f"Could not run initial health check: {e}")
    
    port = int(os.getenv('PORT', 5000))
    debug_mode = ENVIRONMENT == 'development'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        use_reloader=False
    )
