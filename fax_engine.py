import os
import time
import uuid
import json
import requests
import traceback
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from database import log_request, log_response, get_setting
from email_engine import generate_foia_content, send_telegram_notification, TARGET_MUNICIPALITIES

PDF_STORAGE_DIR = "/data/pdfs" if os.path.exists("/data") else "pdfs"
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

CITY_FAX_MAPPING = {
    "City of Boca Raton": "fax_boca_raton",
    "City of Delray Beach": "fax_delray_beach",
    "City of Coconut Creek": "fax_coconut_creek",
    "City of Parkland": "fax_parkland",
    "Town of Hillsboro Beach": "fax_hillsboro_beach"
}

def get_city_fax_number(city_name):
    setting_key = CITY_FAX_MAPPING.get(city_name)
    if setting_key:
        val = get_setting(setting_key)
        if val:
            return val
    # Defaults fallback
    defaults = {
        "City of Boca Raton": "+15613937704",
        "City of Delray Beach": "+15612437199",
        "City of Coconut Creek": "+19549736770",
        "City of Parkland": "+19547538838",
        "Town of Hillsboro Beach": "+18445421010"
    }
    return defaults.get(city_name, "")

def generate_foia_pdf(subject, body, output_path):
    """
    Renders a clean PDF document for the FOIA request using ReportLab.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=12
    )
    
    header_style = ParagraphStyle(
        'DocHeader',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#475569'),
        spaceAfter=16
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=12
    )
    
    story = []
    
    # Title
    story.append(Paragraph(subject, title_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=14))
    
    # Date & Reference Header
    formatted_date = time.strftime("%B %d, %Y")
    story.append(Paragraph(f"<b>Date:</b> {formatted_date}<br/><b>Transmission Type:</b> Official Public Records Request (Fax)", header_style))
    story.append(Spacer(1, 10))
    
    # Body Content (split by newlines into paragraphs)
    paragraphs = body.split("\n")
    for p in paragraphs:
        p_clean = p.strip()
        if p_clean:
            # Escape HTML characters for ReportLab XML parsing safety
            safe_text = p_clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_text, body_style))
        else:
            story.append(Spacer(1, 6))
            
    doc.build(story)

def send_single_foia_fax(city_name, target_fax_number=None, custom_subject=None, custom_body=None):
    """
    Sends a FOIA Request via Telnyx Fax API.
    """
    api_key = os.getenv("TELNYX_API_KEY") or get_setting("telnyx_api_key")
    connection_id = os.getenv("TELNYX_CONNECTION_ID") or get_setting("telnyx_connection_id", "3026849215633425751")
    from_fax = os.getenv("TELNYX_FAX_NUMBER") or get_setting("telnyx_fax_number", "+17624752325")
    base_url = os.getenv("APP_BASE_URL", "https://boca-raton-foia-bot.onrender.com").rstrip("/")
    
    if not target_fax_number:
        target_fax_number = get_city_fax_number(city_name)
        
    if custom_subject and custom_body:
        subject, body = custom_subject, custom_body
    else:
        subject, body = generate_foia_content(city_name=city_name)
        
    if not api_key:
        msg = "Telnyx API Key (TELNYX_API_KEY) missing. Configure in Render env vars or App Settings."
        log_request("Failed", "Fax Request", target_fax_number or "N/A", subject, msg, city_name=city_name)
        return {"status": "error", "message": msg, "city": city_name}

    if not target_fax_number:
        msg = f"No Fax number configured for {city_name}."
        log_request("Failed", "Fax Request", "N/A", subject, msg, city_name=city_name)
        return {"status": "error", "message": msg, "city": city_name}

    try:
        pdf_id = str(uuid.uuid4())
        pdf_filename = f"foia_{pdf_id}.pdf"
        pdf_path = os.path.join(PDF_STORAGE_DIR, pdf_filename)
        
        # Generate PDF
        generate_foia_pdf(subject, body, pdf_path)
        
        media_url = f"{base_url}/api/fax/pdf/{pdf_id}"
        webhook_url = f"{base_url}/api/fax/webhook"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "to": target_fax_number,
            "from": from_fax,
            "media_url": media_url,
            "webhook_url": webhook_url,
            "quality": "high"
        }
        
        if connection_id:
            payload["connection_id"] = connection_id
            
        res = requests.post("https://api.telnyx.com/v2/faxes", headers=headers, json=payload, timeout=15)
        
        if res.status_code in [200, 201, 202]:
            resp_data = res.json().get("data", {})
            fax_id = resp_data.get("id", "N/A")
            body_preview = (body[:150] + "...") if len(body) > 150 else body
            log_request("Sent", "Fax Request", target_fax_number, subject, f"[Fax ID: {fax_id}] {body_preview}", city_name=city_name)
            
            send_telegram_notification(
                f"<b>FOIA Fax Sent</b>\n"
                f"City: <b>{city_name}</b>\n"
                f"Fax Number: <code>{target_fax_number}</code>\n"
                f"Subject: {subject}\n"
                f"Fax ID: <code>{fax_id}</code>"
            )
            return {"status": "success", "city": city_name, "fax_id": fax_id, "recipient": target_fax_number}
        else:
            err_text = res.text
            log_request("Failed", "Fax Request", target_fax_number, subject, f"Telnyx API Error: {err_text}", city_name=city_name)
            return {"status": "error", "city": city_name, "message": err_text}

    except Exception as e:
        err_msg = str(e)
        print(f"Fax transmission error for {city_name}: {traceback.format_exc()}")
        log_request("Failed", "Fax Request", target_fax_number or "N/A", subject, f"Error: {err_msg}", city_name=city_name)
        return {"status": "error", "city": city_name, "message": err_msg}

def send_all_foia_faxes(custom_drafts=None):
    """
    Iterates through all target municipalities and sends FOIA requests via Fax.
    """
    results = []
    total = len(TARGET_MUNICIPALITIES)
    
    print(f"Starting batch Fax dispatch across {total} municipalities...")
    
    for idx, target in enumerate(TARGET_MUNICIPALITIES):
        city = target["name"]
        fax_num = get_city_fax_number(city)
        
        custom_sub = None
        custom_bdy = None
        if custom_drafts and city in custom_drafts:
            custom_sub = custom_drafts[city].get("subject")
            custom_bdy = custom_drafts[city].get("body")
            
        res = send_single_foia_fax(city, target_fax_number=fax_num, custom_subject=custom_sub, custom_body=custom_bdy)
        results.append(res)
        
        if idx < total - 1:
            time.sleep(5)
            
    sent_count = sum(1 for r in results if r.get("status") == "success")
    send_telegram_notification(f"📟 <b>Multi-City FOIA Fax Dispatch Complete</b>\nDispatched to <b>{sent_count}/{total}</b> municipalities via Fax.")
    
    return {"status": "success", "dispatched": sent_count, "total": total, "results": results}
