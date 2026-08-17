import time
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_foia_pdf(subject, body, output_path):
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
            safe_text = p_clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_text, body_style))
        else:
            story.append(Spacer(1, 6))
            
    doc.build(story)

pdf_path = "test_hillsboro_foia.pdf"
subject = "Public Records Request - Code Compliance & Condemned Properties - Town of Hillsboro Beach"
body = """Town Clerk / Records Custodian
Town of Hillsboro Beach
1210 Hillsboro Mile, Hillsboro Beach, FL 33062

RE: Florida Sunshine Law Request (F.S. Chapter 119)

Dear Town Clerk,

Pursuant to Chapter 119 of the Florida Statutes, I hereby request an electronic export (CSV or Excel format) of all active code violation cases, condemned properties, and upcoming demolition lists within the Town of Hillsboro Beach.

Please explicitly include the property owner's mailing address column in the exported report.

Thank you for your prompt assistance with this public records request.

Sincerely,
Jorge Contreras
jorge.properties.123@gmail.com
"""

generate_foia_pdf(subject, body, pdf_path)
print(f"SUCCESS: PDF generated cleanly! Size: {len(open(pdf_path, 'rb').read())} bytes")
