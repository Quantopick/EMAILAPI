from fastapi import FastAPI
from datetime import datetime
from fastapi.responses import HTMLResponse
import pytz

app = FastAPI()

@app.get("/daily-template", response_class=HTMLResponse)
def get_email_template():
    # Date and timestamp logic
    now = datetime.now(pytz.timezone("Asia/Dubai"))  # Adjust timezone if needed
    today = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H%M%S")

    # Load your template string from a file or string
    with open("email_template.html", "r") as file:
        html = file.read()

    # Replace placeholders
    html = html.replace("{{TODAY}}", today)
    html = html.replace("{{TIMESTAMP}}", timestamp)
    html = html.replace("{{DATE}}", now.strftime("%B %d, %Y"))

    return html
