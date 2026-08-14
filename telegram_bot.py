import os
import time
import requests
import threading
from database import log_request

SAVED_CHAT_ID_FILE = "/data/telegram_chat_id.txt" if os.path.exists("/data") else "telegram_chat_id.txt"

def get_saved_chat_id():
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if chat_id:
        return chat_id
    if os.path.exists(SAVED_CHAT_ID_FILE):
        try:
            with open(SAVED_CHAT_ID_FILE, "r") as f:
                cid = f.read().strip()
                if cid:
                    return cid
        except Exception as e:
            print(f"Error reading saved chat_id: {e}")
    return None

def save_chat_id(chat_id):
    try:
        with open(SAVED_CHAT_ID_FILE, "w") as f:
            f.write(str(chat_id))
    except Exception as e:
        print(f"Error saving chat_id: {e}")

def get_bot_token():
    return os.getenv("TELEGRAM_BOT_TOKEN", "8856942581:AAFNDJOsutskSckuS883irZE8e4VVjskQBM")

def send_telegram_msg(chat_id, text, reply_markup=None):
    token = get_bot_token()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send telegram msg: {e}")

def get_main_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🚀 Send FOIA Request", "callback_data": "trigger_send"},
                {"text": "📬 Check Inbox", "callback_data": "trigger_check"}
            ]
        ]
    }

def run_telegram_bot_polling():
    # Lazy import to avoid circular dependencies
    from email_engine import send_foia_email, check_inbox
    
    token = get_bot_token()
    if not token:
        print("No TELEGRAM_BOT_TOKEN found, skipping Telegram bot polling.")
        return
        
    offset = None
    print("Starting Telegram Bot Polling thread...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset
                
            resp = requests.get(url, params=params, timeout=35)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        
                        # Handle direct message
                        if "message" in update:
                            msg = update["message"]
                            chat_id = msg["chat"]["id"]
                            save_chat_id(chat_id)
                            
                            welcome_txt = (
                                "🤖 <b>Boca Raton FOIA Automation Bot</b>\n\n"
                                "Notifications active! You will be alerted whenever a request is sent or a reply/attachment is received.\n\n"
                                "Use the buttons below to trigger actions directly from Telegram:"
                            )
                            send_telegram_msg(chat_id, welcome_txt, get_main_keyboard())
                            
                        # Handle callback queries (inline UI buttons)
                        elif "callback_query" in update:
                            cb = update["callback_query"]
                            chat_id = cb["message"]["chat"]["id"]
                            save_chat_id(chat_id)
                            cb_id = cb["id"]
                            data_action = cb.get("data")
                            
                            # Answer callback query to stop loading spinner
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id})
                            
                            if data_action == "trigger_send":
                                send_telegram_msg(chat_id, "⏳ <b>Generating Gemini FOIA Request & Dispatching Email...</b>")
                                res = send_foia_email()
                                if res.get("status") == "success":
                                    send_telegram_msg(
                                        chat_id,
                                        f"✅ <b>FOIA Request Sent!</b>\n\n<b>To:</b> {res['recipient']}\n<b>Subject:</b> {res['subject']}",
                                        get_main_keyboard()
                                    )
                                else:
                                    send_telegram_msg(chat_id, f"❌ <b>Failed to send:</b> {res.get('message')}", get_main_keyboard())
                                    
                            elif data_action == "trigger_check":
                                send_telegram_msg(chat_id, "🔍 <b>Checking IMAP Inbox for responses & attachments...</b>")
                                res = check_inbox()
                                count = res.get("count", 0)
                                send_telegram_msg(
                                    chat_id,
                                    f"📬 <b>Inbox Check Complete!</b> Found <b>{count}</b> relevant item(s).",
                                    get_main_keyboard()
                                )
        except Exception as e:
            print(f"Telegram polling loop error: {e}")
            time.sleep(5)

def start_bot_thread():
    t = threading.Thread(target=run_telegram_bot_polling, daemon=True)
    t.start()
