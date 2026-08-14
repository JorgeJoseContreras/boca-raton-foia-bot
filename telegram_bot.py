import os
import time
import requests
import threading

SAVED_CHAT_ID_FILE = "/data/telegram_chat_id.txt" if os.path.exists("/data") else "telegram_chat_id.txt"

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
    """Returns bottom persistent reply keyboard"""
    return {
        "keyboard": [
            [{"text": "🚀 Send All FOIA Requests"}, {"text": "📬 Check Inbox"}],
            [{"text": "⚙️ Automation Schedule"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def get_preview_inline_keyboard():
    """Inline buttons attached specifically to the batch preview bubble"""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve & Send All (5 Cities)", "callback_data": "approve_send_all"},
                {"text": "Regenerate All", "callback_data": "regenerate_all"}
            ],
            [
                {"text": "❌ Cancel", "callback_data": "cancel_draft"}
            ]
        ]
    }

def get_schedule_inline_keyboard():
    """Inline buttons for selecting automation frequency"""
    return {
        "inline_keyboard": [
            [
                {"text": "🟢 Daily", "callback_data": "sched_daily"},
                {"text": "🔵 Weekly", "callback_data": "sched_weekly"}
            ],
            [
                {"text": "🟣 Bi-weekly", "callback_data": "sched_biweekly"},
                {"text": "🔴 Monthly", "callback_data": "sched_monthly"}
            ],
            [
                {"text": "⚪ Turn Off (Manual Only)", "callback_data": "sched_off"}
            ]
        ]
    }

def handle_generate_and_preview_all(chat_id, edit_message_id=None):
    from email_engine import generate_foia_content, TARGET_MUNICIPALITIES
    
    drafts = {}
    preview_items = []
    
    for target in TARGET_MUNICIPALITIES:
        cname = target["name"]
        cemail = target["email"]
        sub, bdy = generate_foia_content(city_name=cname)
        drafts[cname] = {"subject": sub, "body": bdy, "recipient": cemail}
        preview_items.append(f"• <b>{cname}</b> ({cemail})\n  <i>Subject: {sub}</i>")
        
    PENDING_DRAFTS[chat_id] = drafts
    
    preview_txt = (
        f"📝 <b>Multi-City FOIA Requests Drafted ({len(TARGET_MUNICIPALITIES)} Municipalities)</b>\n\n"
        + "\n\n".join(preview_items) +
        f"\n\n<i>Tap Approve to dispatch all {len(TARGET_MUNICIPALITIES)} emails via SMTP with 6s rate limiting.</i>"
    )
    
    if edit_message_id:
        edit_telegram_msg(chat_id, edit_message_id, preview_txt, get_preview_inline_keyboard())
    else:
        send_telegram_msg(chat_id, preview_txt, get_preview_inline_keyboard())

def run_telegram_bot_polling():
    from email_engine import send_all_foia_requests, check_inbox
    from database import get_setting
    from app import update_schedule_job
    
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
                            
                            if text in ["🚀 Send All FOIA Requests", "🚀 Send FOIA Request"]:
                                send_telegram_msg(chat_id, "⏳ <b>Generating Gemini AI email drafts for all 5 municipalities...</b>", get_bottom_keyboard())
                                handle_generate_and_preview_all(chat_id)
                            elif text == "📬 Check Inbox":
                                send_telegram_msg(chat_id, "🔍 <b>Checking IMAP Inbox for responses...</b>", get_bottom_keyboard())
                                res = check_inbox()
                                count = res.get("count", 0)
                                send_telegram_msg(
                                    chat_id,
                                    f"📬 <b>Inbox Check Complete!</b> Found <b>{count}</b> relevant item(s).",
                                    get_bottom_keyboard()
                                )
                            elif text == "⚙️ Automation Schedule":
                                curr_freq = get_setting("schedule_frequency", "off").capitalize()
                                txt = f"⚙️ <b>Automated FOIA Schedule Manager</b>\n\nCurrent Schedule: <b>{curr_freq}</b>\n\nWhen enabled, requests for all 5 municipalities are generated with Gemini AI and dispatched automatically without requiring manual confirmation."
                                send_telegram_msg(chat_id, txt, get_schedule_inline_keyboard())
                            else:
                                welcome_txt = (
                                    "🤖 <b>Multi-City FOIA Automation Bot</b>\n\n"
                                    "Notifications active for Boca Raton, Delray Beach, Coconut Creek, Parkland & Hillsboro Beach!\n\n"
                                    "Use the bottom menu buttons below to trigger dispatches or manage schedules:"
                                )
                                send_telegram_msg(chat_id, welcome_txt, get_bottom_keyboard())
                            
                        # Handle callback queries (inline preview/schedule buttons)
                        elif "callback_query" in update:
                            cb = update["callback_query"]
                            chat_id = cb["message"]["chat"]["id"]
                            msg_id = cb["message"]["message_id"]
                            save_chat_id(chat_id)
                            cb_id = cb["id"]
                            action = cb.get("data")
                            
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id})
                            
                            if action == "approve_send_all":
                                draft_map = PENDING_DRAFTS.get(chat_id)
                                edit_telegram_msg(chat_id, msg_id, "⏳ <b>Dispatching FOIA emails to all 5 municipalities via SMTP...</b>")
                                res = send_all_foia_requests(custom_drafts=draft_map)
                                
                                count = res.get("dispatched", 0)
                                total = res.get("total", 5)
                                edit_telegram_msg(
                                    chat_id,
                                    msg_id,
                                    f"✅ <b>Multi-City FOIA Batch Complete!</b>\n\n"
                                    f"Successfully sent: <b>{count}/{total}</b> emails via SMTP."
                                )
                                PENDING_DRAFTS.pop(chat_id, None)
                                
                            elif action == "regenerate_all":
                                edit_telegram_msg(chat_id, msg_id, "⏳ <b>Regenerating new drafts for all 5 municipalities...</b>")
                                handle_generate_and_preview_all(chat_id, edit_message_id=msg_id)
                                
                            elif action == "cancel_draft":
                                PENDING_DRAFTS.pop(chat_id, None)
                                edit_telegram_msg(chat_id, msg_id, "🚫 <i>Batch draft cancelled.</i>")

                            elif action.startswith("sched_"):
                                target_freq = action.replace("sched_", "")
                                new_freq = update_schedule_job(target_freq)
                                label_map = {"daily": "Daily", "weekly": "Weekly", "biweekly": "Bi-weekly", "monthly": "Monthly", "off": "Off (Manual Only)"}
                                readable = label_map.get(new_freq, new_freq.capitalize())
                                
                                edit_telegram_msg(
                                    chat_id,
                                    msg_id,
                                    f"✅ <b>Automated Schedule Saved!</b>\n\n"
                                    f"Frequency: <b>{readable}</b>\n\n"
                                    f"<i>Multi-city dispatches will now run automatically on this interval across all 5 municipalities without requiring manual confirmation.</i>"
                                )
                                
        except Exception as e:
            print(f"Telegram polling loop error: {e}")
            time.sleep(5)

def start_bot_thread():
    t = threading.Thread(target=run_telegram_bot_polling, daemon=True)
    t.start()
