import pypdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import pymupdf
import io
import os

def generate_exact_hillsboro_pdf():
    template_path = "scratch/hillsboro_form.pdf"
    
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    can.setFillColorRGB(0, 0, 0.5) # Dark blue text for clear fill indication
    
    # Date of Request
    can.drawString(245, 574, "August 17, 2026")
    
    # From
    can.drawString(135, 549, "Jorge Contreras")
    
    # Phone
    can.drawString(410, 549, "(561) 555-0199")
    
    # Email Address
    can.drawString(180, 526, "jorge.property.123@gmail.com")
    
    # ITEM(S) REQUESTED (Line 1 & 2)
    can.setFont("Helvetica", 9)
    can.drawString(60, 432, "Public Records Request under F.S. Chapter 119 for digital exports (CSV/Excel) covering active code violations,")
    can.drawString(60, 372, "condemned properties, and upcoming demolitions in Town of Hillsboro Beach, including owner mailing addresses.")
    
    can.save()
    packet.seek(0)
    
    overlay_pdf = pypdf.PdfReader(packet)
    original_pdf = pypdf.PdfReader(template_path)
    writer = pypdf.PdfWriter()
    
    page = original_pdf.pages[0]
    page.merge_page(overlay_pdf.pages[0])
    writer.add_page(page)
    
    out_pdf = "scratch/filled_hillsboro_exact.pdf"
    with open(out_pdf, "wb") as f:
        writer.write(f)
        
    doc = pymupdf.open(out_pdf)
    pix = doc[0].get_pixmap(dpi=150)
    pix.save("scratch/filled_exact.png")
    print("Generated scratch/filled_exact.png successfully!")

generate_exact_hillsboro_pdf()
