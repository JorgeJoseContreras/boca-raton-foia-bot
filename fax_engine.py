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
from reportlab.pdfgen import canvas

from database import log_request, log_response, get_setting, update_request_by_id
from email_engine import generate_foia_content, send_telegram_notification, TARGET_MUNICIPALITIES

PDF_STORAGE_DIR = "/data/pdfs" if os.path.exists("/data") else "pdfs"
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

CITY_FAX_MAPPING = {
    "City of Boca Raton": "fax_boca_raton",
    "City of Delray Beach": "fax_delray_beach",
    "City of Coconut Creek": "fax_coconut_creek",
    "City of Parkland": "fax_parkland",
    "Town of Hillsboro Beach": "fax_hillsboro_beach",
    "Town of Highland Beach": "fax_highland_beach"
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
        "Town of Hillsboro Beach": "+18445421010",
        "Town of Highland Beach": "+15612653582"
    }
    return defaults.get(city_name, "")

import io
import pypdf

def generate_hillsboro_official_pdf(subject, body, output_path):
    """
    Fills out the official Town of Hillsboro Beach Public Records Request PDF form template
    and combines it into a 2-page fax package (Page 1: Cover Note + Reply Email, Page 2: Filled Form).
    """
    template_path = os.path.join(os.path.dirname(__file__), "templates", "hillsboro_form.pdf")
    sender_email = os.getenv("SENDER_EMAIL", "jorge.properties.123@gmail.com")
    
    if not os.path.exists(template_path):
        try:
            r = requests.get("https://www.townofhillsborobeach.com/DocumentCenter/View/66/Police-Department-Records-Request-PDF", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                os.makedirs(os.path.dirname(template_path), exist_ok=True)
                with open(template_path, "wb") as f:
                    f.write(r.content)
        except Exception as e:
            print("Could not fetch remote template:", e)

    if not os.path.exists(template_path):
        return generate_foia_pdf(subject, body, output_path)

    try:
        # --- Page 1: Generate Cover Note with explicit Reply Email ---
        cover_packet = io.BytesIO()
        doc = SimpleDocTemplate(
            cover_packet,
            pagesize=letter,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=54
        )
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor('#0F172A'), spaceAfter=12)
        header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#475569'), spaceAfter=16)
        body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=11, leading=16, textColor=colors.HexColor('#1E293B'), spaceAfter=12)
        
        cover_body = body
        if sender_email not in cover_body:
            cover_body += f"\n\nPlease transmit all responsive public records and CSV/Excel data exports to email address: {sender_email}"
            
        story = [
            Paragraph(subject, title_style),
            HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=14),
            Paragraph(f"<b>Date:</b> {time.strftime('%B %d, %Y')}<br/><b>Transmission Type:</b> Official Public Records Request (Fax)<br/><b>Reply Email Address:</b> <b>{sender_email}</b>", header_style),
            Spacer(1, 10)
        ]
        
        for line in cover_body.split("\n"):
            line_clean = line.strip()
            if line_clean:
                story.append(Paragraph(line_clean, body_style))
                
        doc.build(story)
        cover_packet.seek(0)

        # --- Page 2: Generate Filled Official Form Overlay ---
        overlay_packet = io.BytesIO()
        can = canvas.Canvas(overlay_packet, pagesize=letter)
        can.setFont("Helvetica-Bold", 10)
        can.setFillColor(colors.HexColor("#0F172A"))
        
        # 1. Date of Request (Sitting on underline after Date of Request: )
        formatted_date = time.strftime("%B %d, %Y")
        can.drawString(405, 560, formatted_date)
        
        # 2. From (Sitting on underline after From: (Optional) )
        can.drawString(135, 537, "Jorge Contreras")
        
        # 3. Phone (Optional) -> Omitted / left blank
        
        # 4. Email Address (Sitting on underline after Email Address: (Optional) )
        can.drawString(185, 513, sender_email)
        
        # 5. ITEM(S) REQUESTED (Split across numbered rows 1, 2, and 3, keeping OFFICE USE column clear)
        can.setFont("Helvetica", 8.8)
        
        # --- Box 1: Active Code Violations ---
        can.drawString(55, 423, "Active Code Violations: Digital export of all open/active code violations as of " + formatted_date + ",")
        can.drawString(36, 401, "including case number, property address, violation description, and owner mailing address (CSV).")
        
        # --- Box 2: Condemned Properties ---
        can.drawString(55, 360, "Condemned Properties: List of all properties currently designated as condemned or unfit for human")
        can.drawString(36, 338, "habitation as of " + formatted_date + ".")
        
        # --- Box 3: Demolition Permits ---
        can.drawString(55, 298, "Demolition Permits: List of all demolition permits applied for, active, or completed between")
        can.drawString(36, 276, "January 1, 2024 and " + formatted_date + ", including parcel ID, site address, and contractor/owner details.")
        
        can.save()
        overlay_packet.seek(0)
        
        overlay_pdf = pypdf.PdfReader(overlay_packet)
        original_pdf = pypdf.PdfReader(template_path)
        
        filled_form_page = original_pdf.pages[0]
        filled_form_page.merge_page(overlay_pdf.pages[0])

        # --- Combine Page 1 + Page 2 into 2-Page Fax Package ---
        cover_pdf = pypdf.PdfReader(cover_packet)
        writer = pypdf.PdfWriter()
        writer.add_page(cover_pdf.pages[0])   # Page 1: Cover Note
        writer.add_page(filled_form_page)     # Page 2: Filled Town Form
        
        with open(output_path, "wb") as f:
            writer.write(f)
    except Exception as e:
        print("Error generating Hillsboro official 2-page PDF overlay, fallback to standard:", e)
        generate_foia_pdf(subject, body, output_path)

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
    sender_email = os.getenv("SENDER_EMAIL", "jorge.properties.123@gmail.com")
    story.append(Paragraph(f"<b>Date:</b> {formatted_date}<br/><b>Transmission Type:</b> Official Public Records Request (Fax)<br/><b>Reply Email Address:</b> <b>{sender_email}</b>", header_style))
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
    raw_key = os.getenv("TELNYX_API_KEY") or get_setting("telnyx_api_key") or ""
    api_key = raw_key.strip().strip('"').strip("'")
    
    raw_conn = os.getenv("TELNYX_CONNECTION_ID") or get_setting("telnyx_connection_id", "3026849215633425751") or ""
    connection_id = raw_conn.strip().strip('"').strip("'")
    
    raw_from = os.getenv("TELNYX_FAX_NUMBER") or get_setting("telnyx_fax_number", "+17624752325") or ""
    from_fax = raw_from.strip().strip('"').strip("'")
    
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

    # 1. Log in progress immediately
    req_id = log_request("Sending...", "Fax Request", target_fax_number or "N/A", subject, "Generating PDF & initiating fax call...", city_name=city_name)

    try:
        pdf_id = str(uuid.uuid4())
        pdf_filename = f"foia_{pdf_id}.pdf"
        pdf_path = os.path.join(PDF_STORAGE_DIR, pdf_filename)
        
        # Generate PDF (Use official Town PDF template for Hillsboro Beach)
        if city_name == "Town of Hillsboro Beach":
            generate_hillsboro_official_pdf(subject, body, pdf_path)
        else:
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
            update_request_by_id(req_id, status="Sent", body_preview=f"[Fax ID: {fax_id}] {body_preview}", pdf_id=pdf_id)
            
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
            update_request_by_id(req_id, status="Failed", body_preview=f"Telnyx API Error: {err_text}", pdf_id=pdf_id)
            return {"status": "error", "city": city_name, "message": err_text}

    except Exception as e:
        err_msg = str(e)
        print(f"Fax transmission error for {city_name}: {traceback.format_exc()}")
        update_request_by_id(req_id, status="Failed", body_preview=f"Error: {err_msg}")
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
