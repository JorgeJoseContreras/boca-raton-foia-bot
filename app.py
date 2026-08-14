from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import threading
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_requests, get_all_responses
from email_engine import send_foia_email, check_inbox, generate_foia_content
from telegram_bot import start_bot_thread

load_dotenv()

app = Flask(__name__)

# Initialize DB
init_db()

# Start Telegram Bot Polling thread
start_bot_thread()

# Setup background scheduler for checking inbox every 10 minutes
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_inbox, trigger="interval", minutes=10)
scheduler.start()

# Shut down scheduler gracefully
atexit.register(lambda: scheduler.shutdown())


@app.route("/")
def index():
    requests = get_all_requests()
    responses = get_all_responses()
    target_email = os.getenv("TARGET_EMAIL", "brcityclerk@myboca.us")
    sender_email = os.getenv("SENDER_EMAIL", "jorge.properties.123@gmail.com")
    return render_template("index.html", requests=requests, responses=responses, target_email=target_email, sender_email=sender_email)

@app.route("/api/preview", methods=["POST", "GET"])
def generate_preview():
    subject, body = generate_foia_content()
    target_email = os.getenv("TARGET_EMAIL", "brcityclerk@myboca.us")
    return jsonify({
        "status": "success",
        "subject": subject,
        "body": body,
        "recipient": target_email
    })

@app.route("/api/trigger", methods=["POST"])
def trigger_request():
    data = request.get_json(silent=True) or {}
    custom_subject = data.get("subject")
    custom_body = data.get("body")
    custom_recipient = data.get("recipient")
    
    def task():
        send_foia_email(custom_subject=custom_subject, custom_body=custom_body, custom_recipient=custom_recipient)
        
    thread = threading.Thread(target=task)
    thread.start()
    
    return jsonify({"status": "success", "message": "FOIA email dispatch triggered."})

@app.route("/api/check_inbox", methods=["POST"])
def trigger_inbox_check():
    res = check_inbox()
    return jsonify(res)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
