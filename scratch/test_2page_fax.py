import os
import io
import time
import pypdf
import pymupdf
import requests
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

def create_hillsboro_2page_fax(subject, body, sender_email, output_path):
    # Ensure sender email is explicitly in cover note body
    if sender_email not in body:
        email_note = f"\n\nPlease transmit all responsive public records and CSV/Excel data exports to email address: {sender_email}"
        cover_body = body + email_note
    else:
        cover_body = body

    # 1. Generate Page 1 (Cover Note)
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
    
    story = [
        Paragraph(subject, title_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=14),
        Paragraph(f"<b>Date:</b> {time.strftime('%B %d, %Y')}<br/><b>Transmission Type:</b> Official Public Records Request (Fax)<br/><b>Reply Email Address:</b> {sender_email}", header_style),
        Spacer(1, 10)
    ]
    
    for line in cover_body.split("\n"):
        line_clean = line.strip()
        if line_clean:
            story.append(Paragraph(line_clean, body_style))
            
    doc.build(story)
    cover_packet.seek(0)
    
    # 2. Generate Page 2 (Filled Official Form Overlay)
    template_path = "templates/hillsboro_form.pdf"
    overlay_packet = io.BytesIO()
    can = canvas.Canvas(overlay_packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    can.setFillColor(colors.HexColor("#0F172A"))
    
    formatted_date = time.strftime("%B %d, %Y")
    can.drawString(245, 574, formatted_date)
    can.drawString(135, 549, "Jorge Contreras")
    can.drawString(410, 549, "(561) 555-0199")
    can.drawString(180, 526, sender_email)
    
    can.setFont("Helvetica", 9.5)
    item_line1 = "Public Records Request under Florida Statute Chapter 119 for digital exports (CSV/Excel) covering active code"
    item_line2 = "violations, condemned properties, and upcoming demolitions in Town of Hillsboro Beach, including owner mailing addresses."
    
    can.drawString(60, 432, item_line1)
    can.drawString(60, 372, item_line2)
    
    can.save()
    overlay_packet.seek(0)
    
    overlay_pdf = pypdf.PdfReader(overlay_packet)
    original_pdf = pypdf.PdfReader(template_path)
    
    filled_form_page = original_pdf.pages[0]
    filled_form_page.merge_page(overlay_pdf.pages[0])
    
    # 3. Combine Page 1 (Cover Note) + Page 2 (Filled Form)
    cover_pdf = pypdf.PdfReader(cover_packet)
    
    writer = pypdf.PdfWriter()
    writer.add_page(cover_pdf.pages[0]) # Page 1: Cover Note
    writer.add_page(filled_form_page)   # Page 2: Filled Town Form
    
    with open(output_path, "wb") as f:
        writer.write(f)

create_hillsboro_2page_fax(
    "Florida Chapter 119 Public Records Request - Code Compliance & Condemned Properties - Town of Hillsboro Beach",
    "Dear City Clerk of Town of Hillsboro Beach,\n\nUnder Florida Chapter 119, I am submitting a public records request for digital exports (CSV/Excel) covering active code violations, condemned properties, and upcoming demolitions in Town of Hillsboro Beach, including property owner mailing addresses.\n\nThank you,\nJorge Contreras",
    "jorge.property.123@gmail.com",
    "scratch/hillsboro_2page_test.pdf"
)

doc = pymupdf.open("scratch/hillsboro_2page_test.pdf")
print("Generated 2-Page Fax PDF. Num Pages:", len(doc))
doc[0].get_pixmap(dpi=150).save("scratch/page1_preview.png")
doc[1].get_pixmap(dpi=150).save("scratch/page2_preview.png")
print("Saved page1_preview.png and page2_preview.png successfully!")
