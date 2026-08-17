import sqlite3
import os

DATABASE_PATH = os.getenv("DATABASE_PATH", "foia.db")

DEFAULT_TEMPLATE = (
    "Pursuant to Florida Sunshine Law (Chapter 119, F.S.), I am requesting an electronic export (CSV or Excel format) "
    "of all active code violation cases, condemned properties, and upcoming demolition lists. "
    "Please explicitly include the property owner's mailing address column in the report.\n\n"
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
        "telnyx_fax_number": "+17624752325"
    }
    
    for key, val in defaults.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))
        
    # Force update legacy default Hillsboro fax number to +18445421010
    cursor.execute("UPDATE settings SET value = '+18445421010' WHERE key = 'fax_hillsboro_beach' AND (value = '+19544274027' OR value = '+19544274834')")
    
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

def log_request(status, record_type, recipient_email, subject, body_preview, city_name="City of Boca Raton"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO requests (status, record_type, recipient_email, subject, body_preview, city_name)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (status, record_type, recipient_email, subject, body_preview, city_name))
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
    cursor.execute('SELECT * FROM requests ORDER BY timestamp DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_responses():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM responses ORDER BY timestamp DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DATABASE_PATH}")
