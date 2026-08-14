import os
import time
import requests
import threading

SAVED_CHAT_ID_FILE = "/data/telegram_chat_id.txt" if os.path.exists("/data") else "telegram_chat_id.txt"

# In-memory store for pending email previews per chat_id
PENDING_DRAFTS = {}

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
        return requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send telegram msg: {e}")

def edit_telegram_msg(chat_id, message_id, text, reply_markup=None):
    token = get_bot_token()
    if not token or not chat_id or not message_id:
        return
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        return requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to edit telegram msg: {e}")

def get_bottom_keyboard():
    """Returns bottom persistent reply keyboard (not attached to message bubble)"""
    return {
        "keyboard": [
            [{"text": "🚀 Send FOIA Request"}, {"text": "📬 Check Inbox"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def get_preview_inline_keyboard():
    """Inline buttons attached specifically to the preview bubble"""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve & Send Email", "callback_data": "approve_send"},
                {"text": "🔄 Regenerate", "callback_data": "regenerate_draft"}
            ],
            [
                {"text": "❌ Cancel", "callback_data": "cancel_draft"}
            ]
        ]
    }

def handle_generate_and_preview(chat_id, edit_message_id=None):
    from email_engine import generate_foia_content
    
    target_email = os.getenv("TARGET_EMAIL", "brcityclerk@myboca.us")
    subject, body = generate_foia_content()
    PENDING_DRAFTS[chat_id] = {"subject": subject, "body": body, "recipient": target_email}
    
    preview_txt = (
        f"📝 <b>FOIA Request Email Draft (Gemini AI)</b>\n\n"
        f"<b>To:</b> <code>{target_email}</code>\n"
        f"<b>Subject:</b> {subject}\n\n"
        f"<b>Body:</b>\n<i>{body}</i>\n\n"
        f"<i>Review the draft above. Tap Approve to dispatch via SMTP or Regenerate for a new variation.</i>"
    )
    
    if edit_message_id:
        edit_telegram_msg(chat_id, edit_message_id, preview_txt, get_preview_inline_keyboard())
    else:
        send_telegram_msg(chat_id, preview_txt, get_preview_inline_keyboard())

def run_telegram_bot_polling():
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
                        
                        # Handle text messages / bottom keyboard presses
                        if "message" in update:
                            msg = update["message"]
                            chat_id = msg["chat"]["id"]
                            save_chat_id(chat_id)
                            text = msg.get("text", "").strip()
                            
                            if text == "🚀 Send FOIA Request":
                                send_telegram_msg(chat_id, "⏳ <b>Generating Gemini AI email draft...</b>", get_bottom_keyboard())
                                handle_generate_and_preview(chat_id)
                            elif text == "📬 Check Inbox":
                                send_telegram_msg(chat_id, "🔍 <b>Checking IMAP Inbox for responses...</b>", get_bottom_keyboard())
                                res = check_inbox()
                                count = res.get("count", 0)
                                send_telegram_msg(
                                    chat_id,
                                    f"📬 <b>Inbox Check Complete!</b> Found <b>{count}</b> relevant item(s).",
                                    get_bottom_keyboard()
                                )
                            else:
                                welcome_txt = (
                                    "🤖 <b>Boca Raton FOIA Automation Bot</b>\n\n"
                                    "Notifications active! Use the bottom menu buttons below to trigger requests or check inbox:"
                                )
                                send_telegram_msg(chat_id, welcome_txt, get_bottom_keyboard())
                            
                        # Handle callback queries (inline preview buttons)
                        elif "callback_query" in update:
                            cb = update["callback_query"]
                            chat_id = cb["message"]["chat"]["id"]
                            msg_id = cb["message"]["message_id"]
                            save_chat_id(chat_id)
                            cb_id = cb["id"]
                            action = cb.get("data")
                            
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id})
                            
                            if action == "approve_send":
                                draft = PENDING_DRAFTS.get(chat_id)
                                if not draft:
                                    edit_telegram_msg(chat_id, msg_id, "⚠️ <i>Draft expired. Tap 'Send FOIA Request' below to create a new draft.</i>")
                                    continue
                                    
                                edit_telegram_msg(chat_id, msg_id, "⏳ <b>Dispatching email via SMTP...</b>")
                                res = send_foia_email(
                                    custom_subject=draft["subject"],
                                    custom_body=draft["body"],
                                    custom_recipient=draft["recipient"]
                                )
                                
                                if res.get("status") == "success":
                                    edit_telegram_msg(
                                        chat_id,
                                        msg_id,
                                        f"✅ <b>FOIA Request Approved & Sent!</b>\n\n"
                                        f"<b>To:</b> {res['recipient']}\n"
                                        f"<b>Subject:</b> {res['subject']}"
                                    )
                                else:
                                    edit_telegram_msg(
                                        chat_id,
                                        msg_id,
                                        f"❌ <b>SMTP Dispatch Failed:</b> {res.get('message')}"
                                    )
                                PENDING_DRAFTS.pop(chat_id, None)
                                
                            elif action == "regenerate_draft":
                                edit_telegram_msg(chat_id, msg_id, "⏳ <b>Regenerating new draft with Gemini AI...</b>")
                                handle_generate_and_preview(chat_id, edit_message_id=msg_id)
                                
                            elif action == "cancel_draft":
                                PENDING_DRAFTS.pop(chat_id, None)
                                edit_telegram_msg(chat_id, msg_id, "🚫 <i>Draft cancelled.</i>")
                                
        except Exception as e:
            print(f"Telegram polling loop error: {e}")
            time.sleep(5)

def start_bot_thread():
    t = threading.Thread(target=run_telegram_bot_polling, daemon=True)
    t.start()
