import os
import io
import time
import pypdf
import pymupdf
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas

def test_page2_alignment():
    template_path = "templates/hillsboro_form.pdf"
    overlay_packet = io.BytesIO()
    can = canvas.Canvas(overlay_packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    can.setFillColor(colors.HexColor("#0F172A"))
    
    # 1. Date of Request (After "Date of Request: ")
    formatted_date = time.strftime("%B %d, %Y")
    can.drawString(405, 560, formatted_date)
    
    # 2. From (After "From: (Optional) ")
    can.drawString(135, 537, "Jorge Contreras")
    
    # 3. Phone (After "Phone: (Optional) ")
    can.drawString(410, 537, "(561) 555-0199")
    
    # 4. Email Address (After "Email Address: (Optional) ")
    can.drawString(185, 513, "jorge.property.123@gmail.com")
    
    # 5. ITEM(S) REQUESTED (Inside Box 1, keeping OFFICE USE column clear)
    can.setFont("Helvetica", 9.5)
    can.drawString(55, 440, "Public Records Request under F.S. Chapter 119 for digital exports (CSV/Excel) covering")
    can.drawString(55, 420, "active code violations, condemned properties, and upcoming demolitions in Town of")
    can.drawString(55, 390, "Hillsboro Beach, including property owner mailing addresses.")
    
    can.save()
    overlay_packet.seek(0)
    
    overlay_pdf = pypdf.PdfReader(overlay_packet)
    original_pdf = pypdf.PdfReader(template_path)
    
    filled_form_page = original_pdf.pages[0]
    filled_form_page.merge_page(overlay_pdf.pages[0])
    
    writer = pypdf.PdfWriter()
    writer.add_page(filled_form_page)
    
    out_path = "scratch/aligned_page2_test.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)
        
    doc = pymupdf.open(out_path)
    doc[0].get_pixmap(dpi=150).save("scratch/aligned_page2_preview.png")
    print("Generated scratch/aligned_page2_preview.png successfully!")

test_page2_alignment()
