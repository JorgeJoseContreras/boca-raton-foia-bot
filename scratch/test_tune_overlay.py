import os
import io
import time
import pypdf
import pymupdf
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas

def test_perfect_alignment():
    template_path = "templates/hillsboro_form.pdf"
    overlay_packet = io.BytesIO()
    can = canvas.Canvas(overlay_packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    can.setFillColor(colors.HexColor("#0F172A"))
    
    # 1. Date of Request (Sitting on underline after Date of Request: )
    formatted_date = time.strftime("%B %d, %Y")
    can.drawString(405, 560, formatted_date)
    
    # 2. From (Sitting on underline after From: (Optional) )
    can.drawString(135, 537, "Jorge Contreras")
    
    # 3. Phone (Optional) -> REMOVED as requested (leave blank)
    
    # 4. Email Address (Sitting on underline after Email Address: (Optional) )
    can.drawString(185, 513, "jorge.property.123@gmail.com")
    
    # 5. ITEM(S) REQUESTED (Inside Box 1, perfectly on lines 1 & 2, keeping OFFICE USE clear)
    can.setFont("Helvetica", 9.5)
    # Line 1 sits on top line of Box 1 (y=423)
    can.drawString(55, 423, "Public Records Request under F.S. Chapter 119 for digital exports (CSV/Excel) covering")
    # Line 2 sits on second line of Box 1 (y=401)
    can.drawString(36, 401, "active code violations, condemned properties, demolitions, and owner mailing addresses.")
    
    can.save()
    overlay_packet.seek(0)
    
    overlay_pdf = pypdf.PdfReader(overlay_packet)
    original_pdf = pypdf.PdfReader(template_path)
    
    filled_form_page = original_pdf.pages[0]
    filled_form_page.merge_page(overlay_pdf.pages[0])
    
    writer = pypdf.PdfWriter()
    writer.add_page(filled_form_page)
    
    out_path = "scratch/perfect_page2.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)
        
    doc = pymupdf.open(out_path)
    doc[0].get_pixmap(dpi=150).save("scratch/perfect_page2.png")
    print("Generated scratch/perfect_page2.png successfully!")

test_perfect_alignment()
