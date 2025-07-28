from flask import Flask, request, jsonify
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

app = Flask(__name__)

@app.route("/send_email", methods=["POST"])
def send_email():
    data = request.json
    template_id = data.get("template_id")
    recipient_email = data.get("recipient_email")
    first_name = data.get("first_name")

    if not template_id or not recipient_email or not first_name:
        return jsonify({"error": "Missing required fields"}), 400

    message = Mail(
        from_email="your_verified_sender@example.com",
        to_emails=recipient_email,
    )
    message.dynamic_template_data = {"first_name": first_name}
    message.template_id = template_id

    try:
        sg = SendGridAPIClient(api_key=os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        return jsonify({"status": "success", "code": response.status_code})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Only use debug in development
    app.run(host="0.0.0.0", port=5000)
