import os
import io
import time
import pypdf
import pymupdf
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas

def test_split_alignment():
    template_path = "templates/hillsboro_form.pdf"
    overlay_packet = io.BytesIO()
    can = canvas.Canvas(overlay_packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    can.setFillColor(colors.HexColor("#0F172A"))
    
    # 1. Date of Request
    formatted_date = time.strftime("%B %d, %Y")
    can.drawString(405, 560, formatted_date)
    
    # 2. From
    can.drawString(135, 537, "Jorge Contreras")
    
    # 3. Phone -> Left blank
    
    # 4. Email Address
    can.drawString(185, 513, "jorge.properties.123@gmail.com")
    
    # 5. ITEM(S) REQUESTED (Split across rows 1, 2, and 3)
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
    
    writer = pypdf.PdfWriter()
    writer.add_page(filled_form_page)
    
    out_path = "scratch/split_page2.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)
        
    doc = pymupdf.open(out_path)
    doc[0].get_pixmap(dpi=150).save("scratch/split_page2.png")
    print("Generated scratch/split_page2.png successfully!")

test_split_alignment()
