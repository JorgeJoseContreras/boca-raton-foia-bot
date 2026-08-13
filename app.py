from flask import Flask, render_template, jsonify
from dotenv import load_dotenv
import threading
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_requests, get_all_responses
from automation import run_foia_request
from email_handler import check_inbox

load_dotenv()

app = Flask(__name__)

# Initialize DB
init_db()

# Setup background scheduler for checking inbox every 10 minutes
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_inbox, trigger="interval", minutes=10)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())


@app.route("/")
def index():
    requests = get_all_requests()
    responses = get_all_responses()
    return render_template("index.html", requests=requests, responses=responses)

@app.route("/api/trigger", methods=["POST"])
def trigger_request():
    # Run the automation in a separate thread so we don't block the UI
    def task():
        run_foia_request()
        
    thread = threading.Thread(target=task)
    thread.start()
    
    return jsonify({"status": "success", "message": "Automation triggered in background."})

@app.route("/api/check_inbox", methods=["POST"])
def trigger_inbox_check():
    res = check_inbox()
    return jsonify(res)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
