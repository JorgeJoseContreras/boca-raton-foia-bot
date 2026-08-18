import os
from imapclient import IMAPClient
import email
from email.header import decode_header
from database import log_response

def check_inbox():
    """
    Connects to IMAP, checks for recent emails from JustFOIA or Boca Raton,
    and logs them to the database if they have CSV/Excel attachments.
    """
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    email_user = os.getenv("SENDER_EMAIL")
    email_pass = os.getenv("SENDER_PASSWORD")
    
    if not email_user or not email_pass:
        return {"status": "error", "message": "IMAP credentials not configured"}
        
    try:
        with IMAPClient(imap_server, use_uid=True) as server:
            server.login(email_user, email_pass)
            server.select_folder('INBOX')
            
            # Search for unread emails or emails from justfoia
            messages = server.search(['UNSEEN'])
            
            logs = []
            for uid, message_data in server.fetch(messages, 'RFC822').items():
                email_message = email.message_from_bytes(message_data[b'RFC822'])
                
                subject, encoding = decode_header(email_message["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                    
                sender = email_message.get("From", "")
                
                # Check for attachments and extract body
                has_attachment = False
                attachment_name = ""
                body_text = ""
                
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        content_disposition = part.get('Content-Disposition')
                        content_type = part.get_content_type()
                        if content_disposition is None and content_type == 'text/plain':
                            try:
                                charset = part.get_content_charset() or 'utf-8'
                                body_text = part.get_payload(decode=True).decode(charset, errors='replace')
                            except Exception:
                                pass
                            continue
                        if content_disposition is None:
                            continue
                        
                        filename = part.get_filename()
                        if filename:
                            has_attachment = True
                            attachment_name = filename
                            if filename.endswith(('.csv', '.xlsx', '.xls')):
                                # We can process or download it here if needed
                                pass
                else:
                    if email_message.get_content_type() == 'text/plain':
                        try:
                            charset = email_message.get_content_charset() or 'utf-8'
                            body_text = email_message.get_payload(decode=True).decode(charset, errors='replace')
                        except Exception:
                            pass
                
                log_response(subject, sender, has_attachment, attachment_name, body_text)
                logs.append({"subject": subject, "sender": sender, "attachment": attachment_name})
                
                # Mark as read (uncomment for production)
                # server.add_flags(uid, ['\\Seen'])
                
        return {"status": "success", "count": len(logs), "logs": logs}
        
    except Exception as e:
        print(f"IMAP Error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print("Testing inbox check...")
    print(check_inbox())
