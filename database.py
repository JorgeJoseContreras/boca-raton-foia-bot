import sqlite3
import os

DATABASE_PATH = os.getenv("DATABASE_PATH", "foia.db")

DEFAULT_TEMPLATE = (
    "Dear {addressee},\n\n"
    "Pursuant to Florida Sunshine Law (Chapter 119, F.S.), I am submitting a formal public records request for the following digital records within {city_name}, split across distinct departmental queries:\n\n"
    "1. Active Code Violations: A digital export or standard report of all open/active code enforcement violations as of {date_of_request}, including case number, property address, violation description, and owner mailing address (in native format/CSV if available).\n\n"
    "2. Condemned Properties: A list or report of all properties currently designated as condemned or unfit for human habitation as of {date_of_request}.\n\n"
    "3. Demolition Permits: A list of all demolition permits applied for, active, or completed between {start_date} and {date_of_request}, including parcel ID, site address, and contractor/owner details.\n\n"
    "Please transmit all electronic files and CSV/Excel exports to: jorge.properties.123@gmail.com\n\n"
    "If search, retrieval, or redaction fees are expected to exceed $25.00, please provide an itemized cost estimate for approval prior to fulfilling the request.\n\n"
    "Thank you for your assistance.\n\n"
    "Sincerely,\nJorge Contreras"
)

def get_connection():
    return sqlite3.connect(DATABASE_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table for tracking FOIA email requests sent
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            record_type TEXT,
            recipient_email TEXT,
            subject TEXT,
            body_preview TEXT,
            city_name TEXT
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE requests ADD COLUMN city_name TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE requests ADD COLUMN pdf_id TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Table for tracking archived / cleared FOIA requests
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS archived_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            timestamp DATETIME,
            archived_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            record_type TEXT,
            recipient_email TEXT,
            subject TEXT,
            body_preview TEXT,
            city_name TEXT,
            pdf_id TEXT
        )
    ''')

    # Table for tracking email responses and attachments
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            subject TEXT,
            sender TEXT,
            has_attachment BOOLEAN,
            attachment_name TEXT,
            FOREIGN KEY(request_id) REFERENCES requests(id)
        )
    ''')
    
    # Table for storing key-value settings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    
    # Seed default settings if missing
    defaults = {
        "foia_template": DEFAULT_TEMPLATE,
        "start_date_days_ago": "30",
        "delray_dept": "Code Enforcement",
        "delray_record_type": "Code Violations",
        "use_gemini_ai": "true",
        "schedule_frequency": "off",
        "fax_boca_raton": "+15613937704",
        "fax_delray_beach": "+15612437199",
        "fax_coconut_creek": "+19549736770",
        "fax_parkland": "+19547538838",
        "fax_hillsboro_beach": "+18445421010",
        "fax_highland_beach": "+18445421010",
        "fax_deerfield_beach": "+18445421010",
        "telnyx_fax_number": "+17624752325"
    }
    
    for key, val in defaults.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))
        
    # Force update legacy default Hillsboro, Highland Beach, and Deerfield Beach fax numbers to +18445421010
    cursor.execute("UPDATE settings SET value = '+18445421010' WHERE key = 'fax_hillsboro_beach' AND (value = '+19544274027' OR value = '+19544274834')")
    cursor.execute("UPDATE settings SET value = '+18445421010' WHERE key = 'fax_highland_beach' AND value = '+15612653582'")
    cursor.execute("UPDATE settings SET value = '+18445421010' WHERE key = 'fax_deerfield_beach' AND value = '+19544804323'")
    
    # Force update legacy default FOIA template to modern format with dynamic addressee & date placeholders
    cursor.execute("SELECT value FROM settings WHERE key = 'foia_template'")
    t_row = cursor.fetchone()
    if t_row and ("exceed $25.00" not in t_row[0] or "{addressee}" not in t_row[0] or "1. Active Code Violations" not in t_row[0]):
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'foia_template'", (DEFAULT_TEMPLATE,))

    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()

def format_eastern_timestamp(ts):
    if not ts:
        return ""
    from datetime import datetime, timezone
    import zoneinfo
    try:
        # SQLite CURRENT_TIMESTAMP is in UTC format 'YYYY-MM-DD HH:MM:SS'
        ts_clean = str(ts).strip()
        if "EDT" in ts_clean or "EST" in ts_clean:
            return ts_clean
        dt = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
        dt_utc = dt.replace(tzinfo=timezone.utc)
        ny_tz = zoneinfo.ZoneInfo("America/New_York")
        dt_ny = dt_utc.astimezone(ny_tz)
        return dt_ny.strftime("%Y-%m-%d %I:%M:%S %p EDT")
    except Exception:
        return str(ts)

def log_request(status, record_type, recipient_email, subject, body_preview, city_name="City of Boca Raton", pdf_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO requests (status, record_type, recipient_email, subject, body_preview, city_name, pdf_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (status, record_type, recipient_email, subject, body_preview, city_name, pdf_id))
    conn.commit()
    req_id = cursor.lastrowid
    conn.close()
    return req_id

def log_response(subject, sender, has_attachment, attachment_name=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO responses (subject, sender, has_attachment, attachment_name)
        VALUES (?, ?, ?, ?)
    ''', (subject, sender, has_attachment, attachment_name))
    conn.commit()
    conn.close()

def update_request_by_id(req_id, status=None, body_preview=None, subject=None, pdf_id=None):
    if not req_id:
        return
    conn = get_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if body_preview is not None:
        updates.append("body_preview = ?")
        params.append(body_preview)
    if subject is not None:
        updates.append("subject = ?")
        params.append(subject)
    if pdf_id is not None:
        updates.append("pdf_id = ?")
        params.append(pdf_id)
    if updates:
        params.append(req_id)
        cursor.execute(f"UPDATE requests SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()
    conn.close()

def update_request_status_by_fax_id(fax_id, new_status, failure_reason=None):
    if not fax_id or fax_id == "N/A":
        return
    conn = get_connection()
    cursor = conn.cursor()
    search_term = f"%{fax_id}%"
    if failure_reason:
        cursor.execute(
            "UPDATE requests SET status = ?, body_preview = body_preview || ' [Failure: ' || ? || ']' WHERE body_preview LIKE ?",
            (new_status, failure_reason, search_term)
        )
    else:
        cursor.execute(
            "UPDATE requests SET status = ? WHERE body_preview LIKE ?",
            (new_status, search_term)
        )
    conn.commit()
    conn.close()

def get_all_requests():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM requests ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["timestamp"] = format_eastern_timestamp(d.get("timestamp"))
        result.append(d)
    return result

def get_all_responses():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM responses ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["timestamp"] = format_eastern_timestamp(d.get("timestamp"))
        result.append(d)
    return result

def clear_all_requests():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO archived_requests (original_id, timestamp, status, record_type, recipient_email, subject, body_preview, city_name, pdf_id)
        SELECT id, timestamp, status, record_type, recipient_email, subject, body_preview, city_name, pdf_id
        FROM requests
    ''')
    cursor.execute('DELETE FROM requests')
    conn.commit()
    conn.close()

def get_archived_requests():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM archived_requests ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["timestamp"] = format_eastern_timestamp(d.get("timestamp"))
        d["archived_at"] = format_eastern_timestamp(d.get("archived_at"))
        result.append(d)
    return result

def purge_archived_requests():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM archived_requests')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DATABASE_PATH}")
