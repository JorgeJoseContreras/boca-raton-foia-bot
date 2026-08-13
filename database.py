import sqlite3
import os
from datetime import datetime

DATABASE_PATH = os.getenv("DATABASE_PATH", "foia.db")

def get_connection():
    return sqlite3.connect(DATABASE_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table for tracking FOIA requests sent
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            record_type TEXT,
            recipient_email TEXT,
            description TEXT
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
    
    conn.commit()
    conn.close()

def log_request(status, record_type, recipient_email, description):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO requests (status, record_type, recipient_email, description)
        VALUES (?, ?, ?, ?)
    ''', (status, record_type, recipient_email, description))
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
