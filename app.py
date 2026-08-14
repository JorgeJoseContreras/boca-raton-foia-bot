from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import threading
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_requests, get_all_responses, get_setting, set_setting
from email_engine import send_foia_email, check_inbox, generate_foia_content
from telegram_bot import start_bot_thread

load_dotenv()

app = Flask(__name__)

# Initialize DB
init_db()

# Start Telegram Bot Polling thread
start_bot_thread()

# Setup background scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_inbox, trigger="interval", minutes=10, id="imap_check_job")
scheduler.start()

def update_schedule_job(freq):
    set_setting("schedule_frequency", freq)
    
    if scheduler.get_job("automated_foia_job"):
        scheduler.remove_job("automated_foia_job")
        
    freq_clean = (freq or "off").lower()
    
    if freq_clean == "daily":
        scheduler.add_job(func=send_foia_email, trigger="interval", days=1, id="automated_foia_job")
    elif freq_clean == "weekly":
        scheduler.add_job(func=send_foia_email, trigger="interval", weeks=1, id="automated_foia_job")
    elif freq_clean == "biweekly":
        scheduler.add_job(func=send_foia_email, trigger="interval", weeks=2, id="automated_foia_job")
    elif freq_clean == "monthly":
        scheduler.add_job(func=send_foia_email, trigger="interval", days=30, id="automated_foia_job")
        
    print(f"Automated FOIA Schedule updated to: {freq_clean}")
    return freq_clean

# Initialize schedule on startup
current_schedule = get_setting("schedule_frequency", "off")
update_schedule_job(current_schedule)

# Shut down scheduler gracefully
atexit.register(lambda: scheduler.shutdown())


@app.route("/")
def index():
    requests = get_all_requests()
    responses = get_all_responses()
    schedule_freq = get_setting("schedule_frequency", "off")
    target_email = os.getenv("TARGET_EMAIL", "brcityclerk@myboca.us")
    sender_email = os.getenv("SENDER_EMAIL", "jorge.properties.123@gmail.com")
    return render_template(
        "index.html",
        requests=requests,
        responses=responses,
        schedule_freq=schedule_freq,
        target_email=target_email,
        sender_email=sender_email
    )

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

@app.route("/api/schedule", methods=["GET", "POST"])
def manage_schedule():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        freq = data.get("frequency", "off")
        new_freq = update_schedule_job(freq)
        return jsonify({"status": "success", "frequency": new_freq})
    else:
        freq = get_setting("schedule_frequency", "off")
        return jsonify({"status": "success", "frequency": freq})

@app.route("/api/check_inbox", methods=["POST"])
def trigger_inbox_check():
    res = check_inbox()
    return jsonify(res)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
