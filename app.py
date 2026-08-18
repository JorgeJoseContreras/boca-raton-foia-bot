from flask import Flask, render_template, jsonify, request, send_from_directory
from dotenv import load_dotenv
import threading
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_requests, get_all_responses, get_setting, set_setting, log_response, update_request_status_by_fax_id, clear_all_requests, get_archived_requests, purge_archived_requests
from email_engine import send_all_foia_requests, send_single_foia_email, check_inbox, generate_foia_content, send_telegram_notification, TARGET_MUNICIPALITIES
from fax_engine import send_all_foia_faxes, send_single_foia_fax, PDF_STORAGE_DIR
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

def get_next_run_time():
    try:
        job = scheduler.get_job("automated_foia_job")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%b %d, %Y at %I:%M %p UTC")
    except Exception as e:
        print(f"Error reading next_run_time: {e}")
    return None

def update_schedule_job(freq):
    set_setting("schedule_frequency", freq)
    
    if scheduler.get_job("automated_foia_job"):
        scheduler.remove_job("automated_foia_job")
        
    freq_clean = (freq or "off").lower()
    
    if freq_clean == "daily":
        scheduler.add_job(func=send_all_foia_requests, trigger="interval", days=1, id="automated_foia_job")
    elif freq_clean == "weekly":
        scheduler.add_job(func=send_all_foia_requests, trigger="interval", weeks=1, id="automated_foia_job")
    elif freq_clean == "biweekly":
        scheduler.add_job(func=send_all_foia_requests, trigger="interval", weeks=2, id="automated_foia_job")
    elif freq_clean == "monthly":
        scheduler.add_job(func=send_all_foia_requests, trigger="interval", days=30, id="automated_foia_job")
        
    print(f"Automated Multi-City FOIA Schedule updated to: {freq_clean}")
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
    next_run = get_next_run_time()
    sender_email = os.getenv("SENDER_EMAIL", "jorge.property.123@gmail.com")
    return render_template(
        "index.html",
        requests=requests,
        responses=responses,
        schedule_freq=schedule_freq,
        next_run_time=next_run,
        municipalities=TARGET_MUNICIPALITIES,
        total_cities=len(TARGET_MUNICIPALITIES),
        sender_email=sender_email
    )

@app.route("/settings")
def settings_page():
    all_keys = [
        "use_gemini_ai", "foia_template", "start_date_days_ago", "delray_dept", "delray_record_type", "schedule_frequency",
        "telnyx_fax_number", "telnyx_connection_id", "telnyx_api_key",
        "fax_boca_raton", "fax_delray_beach", "fax_coconut_creek", "fax_parkland", "fax_hillsboro_beach", "fax_highland_beach", "fax_deerfield_beach"
    ]
    settings = {k: get_setting(k, "") for k in all_keys}
    return render_template("settings.html", settings=settings)

@app.route("/api/settings", methods=["POST"])
def save_settings_route():
    data = request.get_json(silent=True) or {}
    for key, val in data.items():
        set_setting(key, val)
    return jsonify({"status": "success", "message": "Settings saved successfully."})

@app.route("/api/preview", methods=["POST", "GET"])
def generate_preview():
    drafts = []
    for m in TARGET_MUNICIPALITIES:
        cname = m["name"]
        cemail = m["email"]
        sub, bdy = generate_foia_content(city_name=cname)
        drafts.append({
            "city": cname,
            "recipient": cemail,
            "subject": sub,
            "body": bdy
        })
    return jsonify({
        "status": "success",
        "drafts": drafts
    })

@app.route("/api/trigger", methods=["POST"])
def trigger_request():
    data = request.get_json(silent=True) or {}
    
    def task():
        send_all_foia_requests()
        
    thread = threading.Thread(target=task)
    thread.start()
    
    return jsonify({"status": "success", "message": "Multi-City FOIA email dispatch triggered for all 5 municipalities."})

@app.route("/api/trigger_single", methods=["POST"])
def trigger_single_request():
    data = request.get_json(silent=True) or {}
    city_name = data.get("city_name")
    
    if not city_name:
        return jsonify({"status": "error", "message": "city_name required"}), 400
        
    def task():
        target = next((m for m in TARGET_MUNICIPALITIES if m["name"] == city_name), None)
        if target and target.get("type") == "fax":
            from fax_engine import get_city_fax_number
            fax_num = get_city_fax_number(city_name) or target["email"]
            send_single_foia_fax(city_name, target_fax_number=fax_num)
        elif target:
            send_single_foia_email(city_name, target["email"])
                
    thread = threading.Thread(target=task)
    thread.start()
    
    return jsonify({"status": "success", "message": f"FOIA request triggered for {city_name}."})

@app.route("/api/schedule", methods=["GET", "POST"])
def manage_schedule():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        freq = data.get("frequency", "off")
        new_freq = update_schedule_job(freq)
        return jsonify({"status": "success", "frequency": new_freq, "next_run": get_next_run_time()})
    else:
        freq = get_setting("schedule_frequency", "off")
        return jsonify({"status": "success", "frequency": freq, "next_run": get_next_run_time()})

@app.route("/api/requests", methods=["GET"])
def get_requests_api():
    requests_list = get_all_requests()
    return jsonify({"status": "success", "requests": requests_list})

@app.route("/api/clear_logs", methods=["POST"])
def clear_logs_endpoint():
    clear_all_requests()
    return jsonify({"status": "success", "message": "Outgoing request logs have been archived and cleared from active log."})

@app.route("/archive")
def archive_page():
    archived_logs = get_archived_requests()
    sender_email = os.getenv("SENDER_EMAIL", "jorge.property.123@gmail.com")
    return render_template("archive.html", archived_logs=archived_logs, sender_email=sender_email)

@app.route("/api/archive/purge", methods=["POST"])
def purge_archive_endpoint():
    purge_archived_requests()
    return jsonify({"status": "success", "message": "Archived request history has been permanently purged."})

@app.route("/api/check_inbox", methods=["POST"])
def trigger_inbox_check():
    res = check_inbox()
    return jsonify(res)

@app.route("/api/fax/pdf/<pdf_id>", methods=["GET"])
def serve_fax_pdf(pdf_id):
    if pdf_id.endswith(".pdf"):
        filename = pdf_id
    else:
        filename = f"foia_{pdf_id}.pdf"
    file_path = os.path.join(PDF_STORAGE_DIR, filename)
    if os.path.exists(file_path):
        return send_from_directory(PDF_STORAGE_DIR, filename, mimetype="application/pdf")
    local_pdf = os.path.join("pdfs", filename)
    if os.path.exists(local_pdf):
        return send_from_directory("pdfs", filename, mimetype="application/pdf")
    return jsonify({"status": "error", "message": "PDF not found"}), 404

@app.route("/api/fax/trigger", methods=["POST"])
def trigger_fax_request():
    def task():
        send_all_foia_faxes()
        
    thread = threading.Thread(target=task)
    thread.start()
    
    return jsonify({"status": "success", "message": "Multi-City FOIA Fax dispatch triggered for all 5 municipalities."})

@app.route("/api/fax/webhook", methods=["POST"])
def telnyx_fax_webhook():
    try:
        data = request.get_json(force=True, silent=True) or {}
        event = data.get("data", {})
        event_type = event.get("event_type", "")
        payload = event.get("payload", {})
        
        fax_id = payload.get("id", "N/A")
        to_num = payload.get("to", "N/A")
        from_num = payload.get("from", "N/A")
        
        if event_type == "fax.delivered":
            update_request_status_by_fax_id(fax_id, "Sent")
            send_telegram_notification(
                f"<b>Fax Delivered Successfully</b>\n"
                f"To: <code>{to_num}</code>\n"
                f"Fax ID: <code>{fax_id}</code>"
            )
        elif event_type == "fax.failed":
            reason = payload.get("failure_reason", "Unknown failure")
            update_request_status_by_fax_id(fax_id, "Failed", failure_reason=reason)
            send_telegram_notification(
                f"<b>Fax Transmission Failed</b>\n"
                f"To: <code>{to_num}</code>\n"
                f"Reason: {reason}\n"
                f"Fax ID: <code>{fax_id}</code>"
            )
        elif event_type == "fax.received":
            media_url = payload.get("media_url", "")
            subject = f"Incoming Fax Response from {from_num}"
            log_response(subject, from_num, True, media_url or "incoming_fax.pdf")
            
            media_link = f"\nMedia: <a href='{media_url}'>Download Fax PDF</a>" if media_url else ""
            send_telegram_notification(
                f"<b>Inbound Fax Response Received</b>\n"
                f"From: <code>{from_num}</code>\n"
                f"To: <code>{to_num}</code>"
                f"{media_link}"
            )
            
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Telnyx Webhook Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
