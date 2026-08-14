from flask import Flask, render_template, jsonify
from dotenv import load_dotenv
import threading
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_requests, get_all_responses
from email_engine import send_foia_email, check_inbox

load_dotenv()

app = Flask(__name__)

# Initialize DB
init_db()

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

@app.route("/api/trigger", methods=["POST"])
def trigger_request():
    def task():
        send_foia_email()
        
    thread = threading.Thread(target=task)
    thread.start()
    
    return jsonify({"status": "success", "message": "Gemini FOIA Email generation & dispatch triggered."})

@app.route("/api/check_inbox", methods=["POST"])
def trigger_inbox_check():
    res = check_inbox()
    return jsonify(res)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
