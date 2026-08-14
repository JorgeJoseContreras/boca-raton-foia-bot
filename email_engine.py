import os
import time
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from imapclient import IMAPClient
from google import genai
import json
import traceback
import requests

from database import log_request, log_response

TARGET_MUNICIPALITIES = [
    {"name": "City of Boca Raton", "email": "brcityclerk@myboca.us"},
    {"name": "City of Delray Beach", "email": "cityclerk@mydelraybeach.com"},
    {"name": "City of Coconut Creek", "email": "publicrecords@coconutcreek.net"},
    {"name": "City of Parkland", "email": "amorales@cityofparkland.org"},
    {"name": "Town of Hillsboro Beach", "email": "townclerk@townofhillsborobeach.com"}
]

def send_telegram_notification(message):
    from telegram_bot import get_saved_chat_id, get_bot_token
    token = get_bot_token()
    chat_id = get_saved_chat_id()
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram notification failed: {e}")

def generate_foia_content(city_name="City of Boca Raton"):
    """
    Generates FOIA request content. If use_gemini_ai is enabled, calls Gemini API.
    Otherwise, uses custom template from database settings.
    """
    from database import get_setting
    
    use_ai = get_setting("use_gemini_ai", "true")
    custom_template = get_setting("foia_template")
    
    if use_ai == "false" and custom_template:
        subject = f"Public Records Request - Code Compliance & Demolition Lists (FL Ch 119) - {city_name}"
        body = custom_template.replace("City of Boca Raton", city_name)
        return subject, body

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        subject = f"Public Records Request - Code Compliance & Demolition Lists (FL Ch 119) - {city_name}"
        body = (custom_template or (
            f"Dear City Clerk of {city_name},\n\n"
            f"Pursuant to Florida Sunshine Law (Chapter 119, F.S.), I am requesting an electronic copy (CSV or Excel format) "
            f"of all active code violation cases, condemned properties, and upcoming demolition lists within {city_name}. "
            f"Please explicitly include the property owner's mailing address column in the report.\n\n"
            f"Thank you for your assistance.\n\n"
            f"Sincerely,\nJorge Contreras"
        )).replace("City of Boca Raton", city_name)
        return subject, body

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Generate a formal public records request email under Florida Chapter 119 (Sunshine Law) "
            f"directed specifically to the City Clerk / Records Custodian of {city_name}, Florida.\n"
            f"The request MUST ask for an electronic export (CSV or Excel) of:\n"
            f"1. Active code violation cases\n"
            f"2. Condemned properties\n"
            f"3. Upcoming demolition lists\n"
            f"4. Explicitly requesting the property owner's mailing address column.\n\n"
            f"Please make the wording unique, professional, and distinct while maintaining legal clarity under FL Ch. 119.\n"
            f"Return JSON format ONLY with keys 'subject' and 'body'. Do not include markdown codeblocks."
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
        data = json.loads(text)
        return data.get("subject"), data.get("body")
    except Exception as e:
        print(f"Error generating content via Gemini API for {city_name}: {e}")
        subject = f"Florida Chapter 119 Public Records Request - Code Compliance & Condemned Properties - {city_name}"
        body = (
            f"Dear City Clerk of {city_name},\n\n"
            f"Under Florida Chapter 119, I am submitting a public records request for digital exports (CSV/Excel) "
            f"covering active code violations, condemned properties, and upcoming demolitions in {city_name}, including property owner mailing addresses.\n\n"
            f"Thank you,\nJorge Contreras"
        )
        return subject, body

def send_single_foia_email(city_name, target_email, custom_subject=None, custom_body=None):
    """
    Sends an email via SMTP to a specific municipality target.
    """
    sender_email = os.getenv("SENDER_EMAIL", "jorge.properties.123@gmail.com")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    
    if not sender_email or not sender_password:
        msg = "SMTP Credentials not configured (SENDER_EMAIL or SENDER_PASSWORD missing)."
        log_request("Failed", "Email Request", target_email, "N/A", msg, city_name=city_name)
        return {"status": "error", "message": msg, "city": city_name}

    if custom_subject and custom_body:
        subject, body = custom_subject, custom_body
    else:
        subject, body = generate_foia_content(city_name=city_name)
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = target_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP_SSL(smtp_server, 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, target_email, msg.as_string())
            
        body_preview = body[:150] + "..." if len(body) > 150 else body
        log_request("Sent", "Email Request", target_email, subject, body_preview, city_name=city_name)
        
        # Send Telegram Alert per city
        send_telegram_notification(f"<b>FOIA Request Sent</b>\nCity: <b>{city_name}</b>\nTo: {target_email}\nSubject: {subject}")
        
        return {"status": "success", "city": city_name, "subject": subject, "recipient": target_email}
        
    except Exception as e:
        error_msg = str(e)
        print(f"SMTP Error for {city_name}: {traceback.format_exc()}")
        log_request("Failed", "Email Request", target_email, subject, f"Error: {error_msg}", city_name=city_name)
        return {"status": "error", "city": city_name, "message": error_msg}

def send_all_foia_requests(custom_drafts=None):
    """
    Iterates through all target municipalities and sends requests with 6-second rate limiting delays.
    """
    results = []
    total = len(TARGET_MUNICIPALITIES)
    
    print(f"Starting batch dispatch across {total} municipalities...")
    
    for idx, target in enumerate(TARGET_MUNICIPALITIES):
        city = target["name"]
        email_addr = target["email"]
        
        custom_sub = None
        custom_bdy = None
        if custom_drafts and city in custom_drafts:
            custom_sub = custom_drafts[city].get("subject")
            custom_bdy = custom_drafts[city].get("body")
            
        res = send_single_foia_email(city, email_addr, custom_subject=custom_sub, custom_body=custom_bdy)
        results.append(res)
        
        # Rate limit delay (6s) between dispatches to avoid spam filters
        if idx < total - 1:
            time.sleep(6)
            
    sent_count = sum(1 for r in results if r.get("status") == "success")
    
    # Telegram summary alert
    send_telegram_notification(f"<b>Multi-City FOIA Dispatch Complete</b>\nDispatched to <b>{sent_count}/{total}</b> municipalities.")
    
    return {"status": "success", "dispatched": sent_count, "total": total, "results": results}

# Backwards compatibility wrapper
def send_foia_email(custom_subject=None, custom_body=None, custom_recipient=None):
    return send_all_foia_requests()

def check_inbox():
    """
    Connects via IMAP to check recent messages for responses or CSV/Excel attachments from any target municipality.
    """
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    email_user = os.getenv("SENDER_EMAIL")
    email_pass = os.getenv("SENDER_PASSWORD")
    
    target_domains = ["myboca.us", "mydelraybeach.com", "coconutcreek.net", "cityofparkland.org", "townofhillsborobeach.com"]
    target_emails = [t["email"].lower() for t in TARGET_MUNICIPALITIES]
    
    if not email_user or not email_pass:
        return {"status": "error", "message": "IMAP credentials not configured"}
        
    try:
        with IMAPClient(imap_server, use_uid=True) as server:
            server.login(email_user, email_pass)
            server.select_folder('INBOX')
            
            messages = server.search(['ALL'])
            recent_uids = messages[-25:] if len(messages) > 25 else messages
            
            logs = []
            for uid in reversed(recent_uids):
                fetch_data = server.fetch([uid], 'RFC822')
                if not fetch_data or uid not in fetch_data:
                    continue
                    
                message_data = fetch_data[uid]
                email_message = email.message_from_bytes(message_data[b'RFC822'])
                
                subject_header = email_message.get("Subject", "No Subject")
                decoded_list = decode_header(subject_header)
                subject, encoding = decoded_list[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
                    
                sender = email_message.get("From", "").lower()
                
                has_attachment = False
                attachment_name = ""
                
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue
                        filename = part.get_filename()
                        if filename:
                            has_attachment = True
                            attachment_name = filename
                
                # Match sender against target emails/domains
                is_target_sender = any(em in sender for em in target_emails) or any(dom in sender for dom in target_domains)
                is_foia_related = "foia" in subject.lower() or "public record" in subject.lower() or "code" in subject.lower()
                
                if is_target_sender or has_attachment or is_foia_related:
                    log_response(subject, sender, has_attachment, attachment_name)
                    logs.append({"subject": subject, "sender": sender, "attachment": attachment_name})
                    
                    # Notify via Telegram
                    attach_msg = f"\nAttachment: {attachment_name}" if has_attachment else ""
                    send_telegram_notification(f"<b>New Inbox Activity Detected</b>\nFrom: {sender}\nSubject: {subject}{attach_msg}")
                
        return {"status": "success", "count": len(logs), "logs": logs}
        
    except Exception as e:
        print(f"IMAP Error: {e}")
        return {"status": "error", "message": str(e)}
