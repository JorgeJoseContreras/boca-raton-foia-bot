import pypdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import os

def generate_filled_hillsboro_pdf(output_path):
    template_path = "scratch/hillsboro_form.pdf"
    
    # Create overlay canvas
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    
    # Date of Request (around x=400, y=695)
    can.drawString(380, 695, "August 17, 2026")
    
    # From (around x=90, y=675)
    can.drawString(90, 675, "Jorge Contreras")
    
    # Phone (around x=360, y=675)
    can.drawString(360, 675, "(561) 555-0199")
    
    # Email Address (around x=120, y=655)
    can.drawString(120, 655, "jorge.property.123@gmail.com")
    
    # Item 1 requested (around x=40, y=595)
    can.setFont("Helvetica", 9)
    can.drawString(45, 595, "Public Records Request under F.S. Chapter 119 for digital exports (CSV/Excel) covering active code")
    can.drawString(45, 570, "violations, condemned properties, and upcoming demolitions in Town of Hillsboro Beach, including owner mailing addresses.")
    
    can.save()
    packet.seek(0)
    
    # Merge overlay with original template
    overlay_pdf = pypdf.PdfReader(packet)
    original_pdf = pypdf.PdfReader(template_path)
    writer = pypdf.PdfWriter()
    
    page = original_pdf.pages[0]
    page.merge_page(overlay_pdf.pages[0])
    writer.add_page(page)
    
    with open(output_path, "wb") as f:
        writer.write(f)

generate_filled_hillsboro_pdf("scratch/filled_hillsboro_form.pdf")
print("Saved filled_hillsboro_form.pdf:", os.path.getsize("scratch/filled_hillsboro_form.pdf"), "bytes")
