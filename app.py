from flask import Flask, render_template, jsonify, request, send_from_directory
from dotenv import load_dotenv
import threading
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_requests, get_all_responses, get_setting, set_setting, log_response, update_request_status_by_fax_id, clear_all_requests, get_archived_requests, purge_archived_requests, get_last_sent_timestamps, get_all_inbound_faxes, log_inbound_fax, get_response_by_id, DATABASE_PATH, delete_response_by_id, restore_response_by_id
from email_engine import send_all_foia_requests, send_single_foia_email, check_inbox, generate_foia_content, send_telegram_notification, sync_all_past_attachments, ATTACHMENTS_DIR, TARGET_MUNICIPALITIES, retroactive_sync_bodies
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

def sync_historical_inbound_faxes():
    """
    Queries Telnyx API for recent inbound faxes and syncs them to local DB / disk cache.
    """
    import requests
    import sqlite3
    
    api_key = get_setting("telnyx_api_key") or os.getenv("TELNYX_API_KEY")
    if not api_key:
        print("Telnyx API key not configured for historical sync.")
        return
        
    api_key = api_key.strip().strip('"').strip("'")
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        url = "https://api.telnyx.com/v2/faxes?filter[direction]=inbound&page[size]=50"
        print(f"Syncing historical faxes from Telnyx: {url}")
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"Telnyx list faxes API returned {r.status_code}: {r.text}")
            return
            
        data = r.json().get("data", [])
        print(f"Found {len(data)} inbound faxes in Telnyx account.")
        
        # Get existing fax IDs to avoid re-downloading
        from database import get_connection, format_eastern_timestamp
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fax_id FROM inbound_faxes")
        existing_ids = {row[0] for row in cursor.fetchall()}
        conn.close()
        
        inbound_dir = os.path.join(os.path.dirname(DATABASE_PATH), "inbound_faxes")
        os.makedirs(inbound_dir, exist_ok=True)
        
        for item in data:
            fax_id = item.get("id")
            if not fax_id or fax_id in existing_ids:
                continue
                
            sender = item.get("from")
            recipient = item.get("to")
            media_url = item.get("media_url")
            page_count = item.get("page_count", 1)
            status = item.get("status", "received")
            created_at = item.get("created_at")
            
            if not media_url:
                continue
                
            file_name = f"{fax_id}.pdf"
            dest_path = os.path.join(inbound_dir, file_name)
            
            # Download PDF
            print(f"Downloading historical fax {fax_id} from {media_url}...")
            fr = requests.get(media_url, headers=headers, timeout=30)
            if fr.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(fr.content)
                
                conn = get_connection()
                cursor = conn.cursor()
                try:
                    clean_ts = created_at.replace("T", " ").split(".")[0]
                    cursor.execute('''
                        INSERT OR REPLACE INTO inbound_faxes (sender_number, fax_id, file_name, num_pages, status, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (sender, fax_id, file_name, page_count, status, clean_ts))
                except Exception:
                    cursor.execute('''
                        INSERT OR REPLACE INTO inbound_faxes (sender_number, fax_id, file_name, num_pages, status)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (sender, fax_id, file_name, page_count, status))
                conn.commit()
                conn.close()
                print(f"Successfully synced historical fax {fax_id}.")
            else:
                print(f"Failed to download historical fax {fax_id}: HTTP {fr.status_code}")
                
    except Exception as e:
        import traceback
        print(f"Error syncing historical faxes: {traceback.format_exc()}")

# Sync historical faxes and past email attachments on startup
from datetime import datetime
scheduler.add_job(func=sync_historical_inbound_faxes, trigger="date", run_date=datetime.now())
scheduler.add_job(func=sync_all_past_attachments, trigger="date", run_date=datetime.now())
scheduler.add_job(func=retroactive_sync_bodies, trigger="date", run_date=datetime.now())

# Shut down scheduler gracefully
atexit.register(lambda: scheduler.shutdown())


@app.route("/")
def index():
    raw_requests = get_all_requests()
    responses = get_all_responses()
    schedule_freq = get_setting("schedule_frequency", "off")
    next_run = get_next_run_time()
    sender_email = os.getenv("SENDER_EMAIL", "jorge.property.123@gmail.com")

    # Group requests: bulk batches become one group; single sends stay solo
    from collections import OrderedDict
    groups = OrderedDict()
    for req in raw_requests:
        bid = req.get("batch_id") or f"solo_{req['id']}"
        if bid not in groups:
            groups[bid] = []
        groups[bid].append(req)

    # Build a list of group dicts for the template
    request_groups = []
    for bid, items in groups.items():
        is_bulk = len(items) > 1 and not bid.startswith("solo_")
        sent = sum(1 for r in items if r.get("status", "").lower() == "sent")
        failed = sum(1 for r in items if r.get("status", "").lower() == "failed")
        sending = sum(1 for r in items if "sending" in r.get("status", "").lower())
        if is_bulk:
            if sending > 0:
                bulk_status = "Sending"
            elif failed > 0 and sent == 0:
                bulk_status = "Failed"
            elif failed > 0:
                bulk_status = f"{sent} Sent / {failed} Failed"
            else:
                bulk_status = "Sent"
        else:
            bulk_status = items[0].get("status", "")
        request_groups.append({
            "batch_id": bid,
            "is_bulk": is_bulk,
            "items": items,
            "count": len(items),
            "sent": sent,
            "failed": failed,
            "bulk_status": bulk_status,
            "timestamp": items[0].get("timestamp", ""),
        })

    last_sent = get_last_sent_timestamps()
    inbound_faxes = get_all_inbound_faxes()

    # Trigger background check to pull any new historical faxes from Telnyx API
    from datetime import datetime
    scheduler.add_job(func=sync_historical_inbound_faxes, trigger="date", run_date=datetime.now())

    return render_template(
        "index.html",
        requests=raw_requests,
        request_groups=request_groups,
        responses=responses,
        schedule_freq=schedule_freq,
        next_run_time=next_run,
        municipalities=TARGET_MUNICIPALITIES,
        total_cities=len(TARGET_MUNICIPALITIES),
        sender_email=sender_email,
        last_sent=last_sent,
        inbound_faxes=inbound_faxes
    )

@app.route("/settings")
def settings_page():
    all_keys = [
        "use_gemini_ai", "foia_template", "start_date_days_ago", "delray_dept", "delray_record_type", "schedule_frequency",
        "telnyx_fax_number", "telnyx_connection_id", "telnyx_api_key",
        "fax_boca_raton", "fax_delray_beach", "fax_coconut_creek", "fax_parkland", "fax_hillsboro_beach", "fax_highland_beach", "fax_deerfield_beach",
        "fax_coral_springs", "fax_boynton_beach", "fax_pompano_beach", "fax_sea_ranch_lakes", "fax_lauderhill", "fax_aventura"
    ]
    settings = {k: get_setting(k, "") for k in all_keys}
    deleted_responses = [r for r in get_all_responses(include_deleted=True) if r.get("is_deleted") == 1]
    return render_template("settings.html", settings=settings, deleted_responses=deleted_responses)

@app.route("/api/settings", methods=["POST"])
def save_settings_route():
    data = request.get_json(silent=True) or {}
    for key, val in data.items():
        set_setting(key, val)
    return jsonify({"status": "success", "message": "Settings saved successfully."})

@app.route("/api/responses/delete/<int:response_id>", methods=["POST"])
def delete_response_endpoint(response_id):
    delete_response_by_id(response_id)
    return jsonify({"status": "success", "message": "Response deleted successfully."})

@app.route("/api/responses/restore/<int:response_id>", methods=["POST"])
def restore_response_endpoint(response_id):
    restore_response_by_id(response_id)
    return jsonify({"status": "success", "message": "Response restored successfully."})

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
    drafts_list = data.get("drafts", [])
    custom_drafts = {d["city"]: {"subject": d["subject"], "body": d["body"]} for d in drafts_list if "city" in d}
    print(f"DEBUG: /api/trigger received drafts for: {list(custom_drafts.keys())}")
    
    from datetime import datetime
    scheduler.add_job(
        func=send_all_foia_requests,
        trigger="date",
        run_date=datetime.now(),
        kwargs={"custom_drafts": custom_drafts}
    )
    
    return jsonify({"status": "success", "message": "Multi-City FOIA dispatch triggered."})

@app.route("/faxes/<filename>")
def serve_inbound_fax(filename):
    inbound_dir = os.path.join(os.path.dirname(DATABASE_PATH), "inbound_faxes")
    filename = os.path.basename(filename)
    return send_from_directory(inbound_dir, filename)

@app.route("/api/trigger_single", methods=["POST"])
def trigger_single_request():
    data = request.get_json(silent=True) or {}
    city_name = data.get("city_name")
    
    if not city_name:
        return jsonify({"status": "error", "message": "city_name required"}), 400
        
    target = next((m for m in TARGET_MUNICIPALITIES if m["name"] == city_name), None)
    if not target:
        return jsonify({"status": "error", "message": f"Municipality {city_name} not found"}), 404
        
    print(f"[SINGLE DISPATCH] Triggering FOIA request for: {city_name}")
    custom_drafts = {city_name: {}}
    from datetime import datetime
    scheduler.add_job(
        func=send_all_foia_requests,
        trigger="date",
        run_date=datetime.now(),
        kwargs={"custom_drafts": custom_drafts}
    )
    
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
    last_sent_map = get_last_sent_timestamps()
    return jsonify({"status": "success", "requests": requests_list, "last_sent": last_sent_map})

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
    # Trigger background check to pull any missing bodies for past response entries
    from datetime import datetime
    scheduler.add_job(func=retroactive_sync_bodies, trigger="date", run_date=datetime.now())
    return jsonify(res)

@app.route("/api/sync_attachments", methods=["POST"])
def trigger_sync_attachments():
    from datetime import datetime
    scheduler.add_job(func=sync_all_past_attachments, trigger="date", run_date=datetime.now())
    return jsonify({"status": "success", "message": "Retroactive attachment sync started in background."})

@app.route("/api/download/attachment/<int:response_id>", methods=["GET"])
def download_attachment(response_id):
    resp = get_response_by_id(response_id)
    if not resp:
        return jsonify({"status": "error", "message": "Response record not found"}), 404
    
    filename = resp.get("attachment_file") or resp.get("attachment_name")
    if not filename:
        return jsonify({"status": "error", "message": "No attachment recorded for this response"}), 404
    
    file_path = os.path.join(ATTACHMENTS_DIR, filename)
    
    # If file is not immediately at direct path, search ATTACHMENTS_DIR
    if not os.path.exists(file_path):
        orig_name = resp.get("attachment_name")
        matched_file = None
        if os.path.exists(ATTACHMENTS_DIR):
            for f in os.listdir(ATTACHMENTS_DIR):
                if f == orig_name or f.endswith(f"_{orig_name}"):
                    matched_file = f
                    break
        if matched_file:
            filename = matched_file
            file_path = os.path.join(ATTACHMENTS_DIR, filename)
        else:
            # Attempt instant sync for this message
            sync_all_past_attachments()
            if os.path.exists(os.path.join(ATTACHMENTS_DIR, filename)):
                file_path = os.path.join(ATTACHMENTS_DIR, filename)
            else:
                return jsonify({"status": "error", "message": "Attachment file could not be found or fetched from server."}), 404
                
    download_name = resp.get("attachment_name") or filename
    if "_" in download_name and download_name.split("_", 1)[0].isdigit():
        download_name = download_name.split("_", 1)[1]
        
    return send_from_directory(ATTACHMENTS_DIR, filename, as_attachment=True, download_name=download_name)


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
            fax_id_clean = payload.get("fax_id") or payload.get("id") or "N/A"
            page_count = payload.get("page_count", 1)
            
            subject = f"Incoming Fax Response from {from_num}"
            log_response(subject, from_num, True, media_url or "incoming_fax.pdf")
            
            if fax_id_clean != "N/A" and media_url:
                file_name = f"{fax_id_clean}.pdf"
                
                def download_job():
                    try:
                        import requests
                        api_key = get_setting("telnyx_api_key") or os.getenv("TELNYX_API_KEY")
                        headers = {}
                        if api_key:
                            headers["Authorization"] = f"Bearer {api_key}"
                        
                        inbound_dir = os.path.join(os.path.dirname(DATABASE_PATH), "inbound_faxes")
                        os.makedirs(inbound_dir, exist_ok=True)
                        
                        dest_path = os.path.join(inbound_dir, file_name)
                        print(f"Downloading inbound fax {fax_id_clean} from {media_url} to {dest_path}...")
                        
                        r = requests.get(media_url, headers=headers, timeout=30)
                        if r.status_code == 200:
                            with open(dest_path, "wb") as f:
                                f.write(r.content)
                            print(f"Successfully downloaded inbound fax {fax_id_clean}.")
                            
                            log_inbound_fax(from_num, fax_id_clean, file_name, page_count, "received")
                            
                            from database import resolve_sender_fax_to_city
                            resolved_city = resolve_sender_fax_to_city(from_num)
                            
                            send_telegram_notification(
                                f"📠 <b>Inbound Fax Received</b>\n"
                                f"From: <b>{resolved_city}</b> ({from_num})\n"
                                f"Pages: {page_count}\n"
                                f"File Name: <pre>{file_name}</pre>\n"
                                f"View link: {os.getenv('APP_BASE_URL', 'https://boca-raton-foia-bot.onrender.com')}/faxes/{file_name}"
                            )
                        else:
                            print(f"Failed to download fax {fax_id_clean}: HTTP {r.status_code} - {r.text}")
                    except Exception as e:
                        import traceback
                        print(f"Error downloading inbound fax {fax_id_clean}: {traceback.format_exc()}")
                
                from datetime import datetime
                scheduler.add_job(
                    func=download_job,
                    trigger="date",
                    run_date=datetime.now()
                )
            
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Telnyx Webhook Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
