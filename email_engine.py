import os
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

DEFAULT_TARGET_EMAIL = "brcityclerk@myboca.us"

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

def generate_foia_content():
    """
    Uses Gemini API (google-genai) to generate a unique, formal Florida Chapter 119 public records request.
    Returns tuple of (subject, body).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        subject = "Public Records Request - Code Compliance & Demolition Lists (FL Ch 119)"
        body = (
            "Dear City Clerk,\n\n"
            "Pursuant to Florida Sunshine Law (Chapter 119, F.S.), I am requesting an electronic copy (CSV or Excel format) "
            "of all active code violation cases, condemned properties, and upcoming demolition lists within the City of Boca Raton. "
            "Please explicitly include the property owner's mailing address column in the report.\n\n"
            "Thank you for your assistance.\n\n"
            "Sincerely,\nJorge Contreras"
        )
        return subject, body

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Generate a formal public records request email under Florida Chapter 119 (Sunshine Law) "
            "directed to the City Clerk of Boca Raton, FL.\n"
            "The request MUST ask for an electronic export (CSV or Excel) of:\n"
            "1. Active code violation cases\n"
            "2. Condemned properties\n"
            "3. Upcoming demolition lists\n"
            "4. Explicitly requesting the property owner's mailing address column.\n\n"
            "Please make the wording unique, professional, and distinct while maintaining legal clarity under FL Ch. 119.\n"
            "Return JSON format ONLY with keys 'subject' and 'body'. Do not include markdown codeblocks."
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
        print(f"Error generating content via Gemini API: {e}")
        subject = "Florida Chapter 119 Public Records Request - Code Compliance & Condemned Properties"
        body = (
            "Dear Boca Raton City Clerk,\n\n"
            "Under Florida Chapter 119, I am submitting a public records request for digital exports (CSV/Excel) "
            "covering active code violations, condemned properties, and upcoming demolitions, including property owner mailing addresses.\n\n"
            "Thank you,\nJorge Contreras"
        )
        return subject, body

def send_foia_email(custom_subject=None, custom_body=None, custom_recipient=None):
    """
    Sends an email via SMTP. Uses custom subject/body if provided, otherwise generates via Gemini.
    """
    sender_email = os.getenv("SENDER_EMAIL", "jorge.properties.123@gmail.com")
    sender_password = os.getenv("SENDER_PASSWORD")
    target_email = custom_recipient or os.getenv("TARGET_EMAIL", DEFAULT_TARGET_EMAIL)
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    
    if not sender_email or not sender_password:
        msg = "SMTP Credentials not configured (SENDER_EMAIL or SENDER_PASSWORD missing)."
        log_request("Failed", "Email Request", target_email, "N/A", msg)
        return {"status": "error", "message": msg}

    if custom_subject and custom_body:
        subject, body = custom_subject, custom_body
    else:
        subject, body = generate_foia_content()
    
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
        log_request("Sent", "Email Request", target_email, subject, body_preview)
        
        # Send Telegram Alert
        send_telegram_notification(f"✅ <b>FOIA Request Sent</b>\nTo: {target_email}\nSubject: {subject}")
        
        return {"status": "success", "subject": subject, "recipient": target_email}
        
    except Exception as e:
        error_msg = str(e)
        print(f"SMTP Error: {traceback.format_exc()}")
        log_request("Failed", "Email Request", target_email, subject, f"Error: {error_msg}")
        return {"status": "error", "message": error_msg}

def check_inbox():
    """
    Connects via IMAP to check recent messages for responses or CSV/Excel attachments.
    """
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    email_user = os.getenv("SENDER_EMAIL")
    email_pass = os.getenv("SENDER_PASSWORD")
    target_email = os.getenv("TARGET_EMAIL", DEFAULT_TARGET_EMAIL)
    
    if not email_user or not email_pass:
        return {"status": "error", "message": "IMAP credentials not configured"}
        
    try:
        with IMAPClient(imap_server, use_uid=True) as server:
            server.login(email_user, email_pass)
            server.select_folder('INBOX')
            
            # Search recent 20 messages in INBOX
            messages = server.search(['ALL'])
            recent_uids = messages[-20:] if len(messages) > 20 else messages
            
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
                    
                sender = email_message.get("From", "")
                
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
                
                # Check relevance: sender matches target OR has attachment OR contains FOIA/Boca keywords
                is_target_sender = target_email.lower() in sender.lower() or "boca" in sender.lower()
                is_foia_related = "foia" in subject.lower() or "public record" in subject.lower() or "code" in subject.lower()
                
                if is_target_sender or has_attachment or is_foia_related:
                    log_response(subject, sender, has_attachment, attachment_name)
                    logs.append({"subject": subject, "sender": sender, "attachment": attachment_name})
                    
                    # Notify via Telegram
                    attach_msg = f"\n📎 Attachment: {attachment_name}" if has_attachment else ""
                    send_telegram_notification(f"📬 <b>New Inbox Activity Detected!</b>\nFrom: {sender}\nSubject: {subject}{attach_msg}")
                
        return {"status": "success", "count": len(logs), "logs": logs}
        
    except Exception as e:
        print(f"IMAP Error: {e}")
        return {"status": "error", "message": str(e)}
