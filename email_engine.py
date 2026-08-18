import os
import time
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from imapclient import IMAPClient
from google import genai
import json
import traceback
import requests

from database import log_request, log_response, update_request_by_id

TARGET_MUNICIPALITIES = [{"name": "City of Boca Raton", "email": "brcityclerk@myboca.us", "type": "email"},
    {"name": "City of Delray Beach", "email": "cityclerk@mydelraybeach.com", "type": "email"},
    {"name": "City of Coconut Creek", "email": "publicrecords@coconutcreek.net", "type": "email"},
    {"name": "City of Parkland", "email": "amorales@cityofparkland.org", "type": "email"},
    {"name": "Town of Hillsboro Beach", "email": "+19544274834", "type": "fax"},
    {"name": "Town of Highland Beach", "email": "+15612653582", "type": "fax"},
    {"name": "City of Deerfield Beach", "email": "+19544804323", "type": "fax"},
    {"name": "City of Lighthouse Point", "email": "lhpadmin@lighthousepoint.com", "type": "email"},
    {"name": "City of Margate", "email": "recordsmanagement@margatefl.com", "type": "email"},
    {"name": "Town of Gulf Stream", "email": "townclerk@gulf-stream.org", "type": "email"},
    {"name": "City of Coral Springs", "email": "+18445421010", "type": "fax"},
    {"name": "City of Boynton Beach", "email": "+15617426090", "type": "fax"},
    {"name": "City of Pompano Beach", "email": "+19547864095", "type": "fax"},
    {"name": "Village of Sea Ranch Lakes", "email": "+19549435808", "type": "fax"},
    {"name": "City of Lauderhill", "email": "+19547303062", "type": "fax"},
    {"name": "City of Fort Lauderdale", "email": "PropertyRecords@fortlauderdale.gov", "type": "email"},
    {"name": "City of Aventura", "email": "+13054668998", "type": "fax"},
    {"name": "City of Atlantis", "email": "clerk@atlantisfl.gov", "type": "email"},
    {"name": "City of Avon Park", "email": "cityclerk@avonpark.city", "type": "email"},
    {"name": "City of Plantation", "email": "cityclerk@plantation.org", "type": "email"},
    {"name": "City of Belle Glade", "email": "cityclerk@bellegladegov.com", "type": "email"},
    {"name": "City of Bonita Springs", "email": "cityclerk@cityofbonitasprings.org", "type": "email"},
    {"name": "City of Doral", "email": "cityclerk@cityofdoral.com", "type": "email"},
    {"name": "City of Bradenton", "email": "cityclerk@cityofbradenton.com", "type": "email"},
    {"name": "City of Cape Coral", "email": "ctyclk@capecoral.gov", "type": "email"},
    {"name": "City of Clearwater", "email": "cityclerk@myclearwater.com", "type": "email"},
    {"name": "City of Clewiston", "email": "clerk@clewiston-fl.gov", "type": "email"},
    {"name": "City of Cocoa Beach", "email": "cityclerk@cityofcocoabeach.com", "type": "email"},
    {"name": "City of Cooper City", "email": "cityclerk@coopercity.gov", "type": "email"},
    {"name": "City of Coral Gables", "email": "cityclerk@coralgables.com", "type": "email"},
    {"name": "City of Dania Beach", "email": "cityclerk@daniabeachfl.gov", "type": "email"},
    {"name": "City of Daytona Beach", "email": "cityclerk@codb.us", "type": "email"},
    {"name": "City of Florida City", "email": "cityclerk@floridacityfl.gov", "type": "email"},
    {"name": "City of Fort Pierce", "email": "clerksoffice@cityoffortpierce.com", "type": "email"},
    {"name": "City of Gainesville", "email": "cityclerk@gainesvillefl.gov", "type": "email"},
    {"name": "City of Greenacres", "email": "cityclerk@greenacresfl.gov", "type": "email"},
    {"name": "City of Hallandale Beach", "email": "cityclerk@hallandalebeachfl.gov", "type": "email"},
    {"name": "City of Hialeah", "email": "cityclerk@hialeahfl.gov", "type": "email"},
    {"name": "City of Hialeah Gardens", "email": "clerk@cityofhialeahgardens.com", "type": "email"},
    {"name": "City of Hollywood", "email": "pcerny@hollywoodfl.org", "type": "email"},
    {"name": "City of Homestead", "email": "cityclerk@cityofhomestead.com", "type": "email"},
    {"name": "City of Jacksonville", "email": "publicrecords@coj.net", "type": "email"},
    {"name": "City of Key West", "email": "cityclerk@cityofkeywest-fl.gov", "type": "email"},
    {"name": "City of Kissimmee", "email": "cityclerk@kissimmee.gov", "type": "email"},
    {"name": "City of Lake Worth Beach", "email": "cityclerk@lakeworthbeachfl.gov", "type": "email"},
    {"name": "City of Lakeland", "email": "cityclerk@lakelandgov.net", "type": "email"},
    {"name": "City of Marco Island", "email": "cityclerk@cityofmarcoisland.com", "type": "email"},
    {"name": "City of Melbourne", "email": "cityclerk@mlbfl.org", "type": "email"},
    {"name": "City of Miami", "email": "cityclerk@miamigov.com", "type": "email"},
    {"name": "City of Miami Beach", "email": "cityclerk@miamibeachfl.gov", "type": "email"},
    {"name": "City of Miami Gardens", "email": "cityclerk@miamigardens-fl.gov", "type": "email"},
    {"name": "City of Miramar", "email": "clerksoffice@miramarfl.gov", "type": "email"},
    {"name": "City of Naples", "email": "cityclerk@naplesgov.com", "type": "email"},
    {"name": "City of North Lauderdale", "email": "clerk@nlauderdale.org", "type": "email"},
    {"name": "City of North Miami", "email": "cityclerk@northmiamifl.gov", "type": "email"},
    {"name": "City of North Miami Beach", "email": "cityclerk@citynmb.com", "type": "email"},
    {"name": "City of Oakland Park", "email": "publicrecords@oaklandparkfl.gov", "type": "email"},
    {"name": "City of Ocala", "email": "cityclerk@ocalafl.gov", "type": "email"},
    {"name": "City of Okeechobee", "email": "cityclerk@cityofokeechobee.com", "type": "email"},
    {"name": "City of Opa-locka", "email": "cityclerk@opalockafl.gov", "type": "email"},
    {"name": "City of Orlando", "email": "records@orlando.gov", "type": "email"},
    {"name": "City of Pahokee", "email": "cityclerk@cityofpahokee.com", "type": "email"},
    {"name": "City of Palm Bay", "email": "cityclerk@pbfl.org", "type": "email"},
    {"name": "City of Palm Beach Gardens", "email": "cityclerk@pbgfl.com", "type": "email"},
    {"name": "City of Panama City", "email": "cityclerk@panamacity.gov", "type": "email"},
    {"name": "City of Pembroke Pines", "email": "publicrecords@ppines.com", "type": "email"},
    {"name": "City of Pensacola", "email": "cityclerk@cityofpensacola.com", "type": "email"},
    {"name": "City of Port St. Lucie", "email": "pslclerk@cityofpsl.com", "type": "email"},
    {"name": "City of Riviera Beach", "email": "cityclerk@rivierabeach.org", "type": "email"},
    {"name": "City of Sarasota", "email": "cityclerk@sarasotafl.gov", "type": "email"},
    {"name": "City of Sebastian", "email": "cityclerk@cityofsebastian.org", "type": "email"},
    {"name": "City of Sebring", "email": "cityclerk@mysebring.com", "type": "email"},
    {"name": "City of South Bay", "email": "cityclerk@southbaycity.com", "type": "email"},
    {"name": "City of South Miami", "email": "cityclerk@southmiamifl.gov", "type": "email"},
    {"name": "City of St. Augustine", "email": "cityclerk@citystaug.com", "type": "email"},
    {"name": "City of St. Petersburg", "email": "cityclerk@stpete.org", "type": "email"},
    {"name": "City of Sunny Isles Beach", "email": "cityclerk@sibfl.net", "type": "email"},
    {"name": "City of Sunrise", "email": "CityClerk@sunrisefl.gov", "type": "email"},
    {"name": "City of Sweetwater", "email": "cityclerk@cityofsweetwater.fl.gov", "type": "email"},
    {"name": "City of Tallahassee", "email": "records@talgov.com", "type": "email"},
    {"name": "City of Tamarac", "email": "CityClerk@Tamarac.org", "type": "email"},
    {"name": "City of Tampa", "email": "publicrecords@tampagov.net", "type": "email"},
    {"name": "City of Titusville", "email": "cityclerk@titusville.com", "type": "email"},
    {"name": "City of Vero Beach", "email": "cityclerk@covb.org", "type": "email"},
    {"name": "City of West Palm Beach", "email": "cityclerk@wpb.org", "type": "email"},
    {"name": "City of Westlake", "email": "clerk@cityofwestlake-fl.gov", "type": "email"},
    {"name": "City of Weston", "email": "cityclerk@westonfl.org", "type": "email"},
    {"name": "City of Wilton Manors", "email": "cdsrecordsrequest@wiltonmanors.com", "type": "email"},
    {"name": "City of Winter Haven", "email": "cityclerk@mywinterhaven.com", "type": "email"},
    {"name": "Town of Bay Harbor Islands", "email": "clerk@bayharborislands-fl.gov", "type": "email"},
    {"name": "Town of Briny Breezes", "email": "townclerk@townofbrinybreezes-fl.gov", "type": "email"},
    {"name": "Town of Cloud Lake", "email": "clerk@cloudlakefl.gov", "type": "email"},
    {"name": "Town of Cutler Bay", "email": "clerk@cutlerbay-fl.gov", "type": "email"},
    {"name": "Town of Davie", "email": "townclerk@davie-fl.gov", "type": "email"},
    {"name": "Town of Glen Ridge", "email": "clerk@glenridgefl.gov", "type": "email"},
    {"name": "Town of Golden Beach", "email": "clerk@goldenbeachfl.gov", "type": "email"},
    {"name": "Town of Haverhill", "email": "clerk@townofhaverhill-fl.gov", "type": "email"},
    {"name": "Town of Hypoluxo", "email": "townclerk@hypoluxo.org", "type": "email"},
    {"name": "Town of Juno Beach", "email": "clerk@juno-beach.fl.us", "type": "email"},
    {"name": "Town of Jupiter", "email": "clerk@jupiter.fl.us", "type": "email"},
    {"name": "Town of Jupiter Inlet Colony", "email": "clerk@jupiterinletcolony.org", "type": "email"},
    {"name": "Town of Lake Clarke Shores", "email": "publicrecords@lakeclarkeshores.fl.gov", "type": "email"},
    {"name": "Town of Lake Park", "email": "townclerk@lakeparkflorida.gov", "type": "email"},
    {"name": "Town of Lantana", "email": "openrecords@lantana.org", "type": "email"},
    {"name": "Town of Lauderdale-by-the-Sea", "email": "publicrecords@lbts-fl.gov", "type": "email"},
    {"name": "Town of Loxahatchee Groves", "email": "clerk@loxahatcheegrovesfl.gov", "type": "email"},
    {"name": "Town of Manalapan", "email": "townclerk@manalapan.org", "type": "email"},
    {"name": "Town of Mangonia Park", "email": "clerk@townofmangoniapark.com", "type": "email"},
    {"name": "Town of Medley", "email": "clerk@townofmedley.com", "type": "email"},
    {"name": "Town of Miami Lakes", "email": "clerk@miamilakes-fl.gov", "type": "email"},
    {"name": "Town of Ocean Breeze", "email": "clerk@townofoceanbreeze.org", "type": "email"},
    {"name": "Town of Ocean Ridge", "email": "info@oceanridgeflorida.com", "type": "email"},
    {"name": "Town of Orchid", "email": "townclerk@townoforchid.com", "type": "email"},
    {"name": "Town of Palm Beach", "email": "townclerk@townofpalmbeach.com", "type": "email"},
    {"name": "Town of Pembroke Park", "email": "clerk@tobbfl.gov", "type": "email"},
    {"name": "Town of Sewall's Point", "email": "clerk@sewallspoint.org", "type": "email"},
    {"name": "Town of South Palm Beach", "email": "townclerk@southpalmbeach.com", "type": "email"},
    {"name": "Town of Southwest Ranches", "email": "clerk@southwestranches.net", "type": "email"},
    {"name": "Town of Stuart", "email": "cityclerk@ci.stuart.fl.us", "type": "email"},
    {"name": "Town of Surfside", "email": "clerk@townofsurfsidefl.gov", "type": "email"},
    {"name": "Town of West Miami", "email": "clerk@cityofwestmiamifl.com", "type": "email"},
    {"name": "Village of Bal Harbour", "email": "villageclerk@balharbourfl.gov", "type": "email"},
    {"name": "Village of Biscayne Park", "email": "clerk@biscayneparkfl.gov", "type": "email"},
    {"name": "Village of Golf", "email": "villageclerk@villageofgolf.org", "type": "email"},
    {"name": "Village of Indian Creek", "email": "clerk@indiancreekvillagefl.gov", "type": "email"},
    {"name": "Village of Key Biscayne", "email": "clerk@keybiscayne.fl.gov", "type": "email"},
    {"name": "Village of North Bay Village", "email": "villageclerk@nbvillage.com", "type": "email"},
    {"name": "Village of Palm Springs", "email": "clerk@vpsfl.org", "type": "email"},
    {"name": "Village of Palmetto Bay", "email": "clerk@palmettobay-fl.gov", "type": "email"},
    {"name": "Village of Pinecrest", "email": "clerk@pinecrest-fl.gov", "type": "email"},
    {"name": "Village of Royal Palm Beach", "email": "clerk@royalpalmbeachfl.gov", "type": "email"},
    {"name": "Village of Tequesta", "email": "clerk@tequesta.org", "type": "email"},
    {"name": "Village of Virginia Gardens", "email": "clerk@virginiagardens-fl.gov", "type": "email"},
    {"name": "Village of Wellington", "email": "clerk@wellingtonfl.gov", "type": "email"}
]

def send_telegram_notification(message):
    from telegram_bot import get_saved_chat_id, get_bot_token
    token = get_bot_token()
    chat_id = get_saved_chat_id()
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram notification failed: {e}")

def get_municipality_addressee(city_name):
    if not city_name:
        return "Records Custodian"
    c_lower = city_name.lower()
    if "town" in c_lower:
        clerk_title = "Town Clerk / Records Custodian"
    elif "village" in c_lower:
        clerk_title = "Village Clerk / Records Custodian"
    elif "county" in c_lower:
        clerk_title = "County Records Custodian"
    else:
        clerk_title = "City Clerk / Records Custodian"
    return f"{clerk_title} of {city_name}"

def generate_foia_content(city_name="City of Boca Raton"):
    """
    Generates FOIA request content. If use_gemini_ai is enabled, calls Gemini API.
    Otherwise, uses custom template from database settings.
    """
    from database import get_setting
    
    use_ai = get_setting("use_gemini_ai", "true")
    custom_template = get_setting("foia_template")
    
    req_date = time.strftime("%B %d, %Y")
    days_offset = int(get_setting("start_date_days_ago", "30") or "30")
    # Default start date for demolition permits
    start_date = "January 1, 2024"
    addressee = get_municipality_addressee(city_name)
    
    standard_body = (
        f"Dear {addressee},\n\n"
        f"Pursuant to Florida Sunshine Law (Chapter 119, F.S.), I am submitting a formal public records request for the following digital records within {city_name}, split across distinct departmental queries:\n\n"
        f"1. Active Code Violations: A digital export or standard report of all open/active code enforcement violations as of {req_date}, including case number, property address, Folio / Parcel ID, and violation description (in native format/CSV if available).\n\n"
        f"2. Condemned Properties: A list or report of all properties currently designated as condemned or unfit for human habitation as of {req_date}.\n\n"
        f"3. Demolition Permits: A list of all demolition permits applied for, active, or completed in the last 30 days, including parcel ID, site address, and contractor/owner details.\n\n"
        f"Please note that I accept standard system exports, existing reports, or existing database dumps in their native format (such as CSV or Excel), and do not require the creation of a new record or custom query.\n\n"
        f"Please transmit all electronic files and CSV/Excel data exports to email: jorge.property.123@gmail.com\n\n"
        f"If search, retrieval, or redaction fees are expected to exceed $25.00, please provide an itemized cost estimate for approval prior to fulfilling the request.\n\n"
        f"Thank you for your assistance."
    )
    
    subject_default = f"Florida Chapter 119 Public Records Request - Code Compliance & Demolition Lists - {city_name}"
    
    if use_ai == "false" and custom_template:
        body = (custom_template
                .replace("{addressee}", addressee)
                .replace("City Clerk / Records Custodian of City of Boca Raton", addressee)
                .replace("City Clerk / Records Custodian of " + city_name, addressee)
                .replace("City Clerk of " + city_name, addressee)
                .replace("{city_name}", city_name)
                .replace("{date_of_request}", req_date)
                .replace("{current_date}", req_date)
                .replace("{req_date}", req_date)
                .replace("{start_date}", start_date)
                .replace("City of Boca Raton", city_name))
        return subject_default, body

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return subject_default, standard_body

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Generate a formal public records request email under Florida Chapter 119 (Sunshine Law).\n"
            f"The salutation MUST be addressed dynamically and accurately to: Dear {addressee},\n"
            f"The request MUST be split across distinct numbered items with these exact specifications:\n"
            f"1. Active Code Violations: A digital export or standard report of all open/active code enforcement violations as of {req_date}, including case number, property address, Folio / Parcel ID, and violation description (in native format/CSV if available).\n"
            f"2. Condemned Properties: A list or report of all properties currently designated as condemned or unfit for human habitation as of {req_date}.\n"
            f"3. Demolition Permits: A list of all demolition permits applied for, active, or completed in the last 30 days, including parcel ID, site address, and contractor/owner details.\n\n"
            f"Explicitly include a clause stating that you accept standard system exports, existing reports, or existing database dumps in their native format (such as CSV or Excel), and do not require the creation of a new record or custom query.\n"
            f"Explicitly include instruction to deliver data exports to email: jorge.property.123@gmail.com\n"
            f"Explicitly include this cost cap estimate clause: 'If search, retrieval, or redaction fees are expected to exceed $25.00, please provide an itemized cost estimate for approval prior to fulfilling the request.'\n"
            f"The email should not contain any name or signature at the end (just end with 'Thank you for your assistance.').\n"
            f"Return JSON format ONLY with keys 'subject' and 'body'. Do not include markdown codeblocks."
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
        data = json.loads(text)
        return data.get("subject", subject_default), data.get("body", standard_body)
    except Exception as e:
        print(f"Error generating content via Gemini API for {city_name}: {e}")
        return subject_default, standard_body

def send_single_foia_email(city_name, target_email, custom_subject=None, custom_body=None, batch_id=None):
    """
    Sends an email via SMTP to a specific municipality target.
    """
    sender_email = os.getenv("SENDER_EMAIL", "jorge.property.123@gmail.com")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    
    if not sender_email or not sender_password:
        msg = "SMTP Credentials not configured (SENDER_EMAIL or SENDER_PASSWORD missing)."
        log_request("Failed", "Email Request", target_email, "N/A", msg, city_name=city_name, batch_id=batch_id)
        return {"status": "error", "message": msg, "city": city_name}

    if custom_subject and custom_body:
        subject, body = custom_subject, custom_body
    else:
        subject, body = generate_foia_content(city_name=city_name)
    
    # 1. Log in progress immediately
    req_id = log_request("Sending...", "Email Request", target_email, subject, "Preparing transmission...", city_name=city_name, batch_id=batch_id)
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = target_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP_SSL(smtp_server, 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, target_email, msg.as_string())
            
        body_preview = body[:150] + "..." if len(body) > 150 else body
        update_request_by_id(req_id, status="Sent", body_preview=body_preview, subject=subject)
        
        # Send Telegram Alert per city
        send_telegram_notification(f"<b>FOIA Request Sent</b>\nCity: <b>{city_name}</b>\nTo: {target_email}\nSubject: {subject}")
        
        return {"status": "success", "city": city_name, "subject": subject, "recipient": target_email}
        
    except Exception as e:
        error_msg = str(e)
        print(f"SMTP Error for {city_name}: {traceback.format_exc()}")
        update_request_by_id(req_id, status="Failed", body_preview=f"Error: {error_msg}")
        return {"status": "error", "city": city_name, "message": error_msg}

def send_all_foia_requests(custom_drafts=None):
    """
    Iterates through all target municipalities and sends requests.
    Hillsboro Beach is routed via Telnyx Fax API to +19544274834; others via Email.
    """
    from fax_engine import send_single_foia_fax
    import uuid
    
    batch_id = str(uuid.uuid4())
    results = []
    total = len(TARGET_MUNICIPALITIES)
    
    print(f"Starting batch dispatch across {total} municipalities...")
    
    for idx, target in enumerate(TARGET_MUNICIPALITIES):
        city = target["name"]
        addr = target["email"]
        dispatch_type = target.get("type", "email")
        
        custom_sub = None
        custom_bdy = None
        if custom_drafts and city in custom_drafts:
            custom_sub = custom_drafts[city].get("subject")
            custom_bdy = custom_drafts[city].get("body")
            
        if dispatch_type == "fax":
            from fax_engine import get_city_fax_number
            fax_num = get_city_fax_number(city) or addr
            res = send_single_foia_fax(city, target_fax_number=fax_num, custom_subject=custom_sub, custom_body=custom_bdy, batch_id=batch_id)
        else:
            res = send_single_foia_email(city, addr, custom_subject=custom_sub, custom_body=custom_bdy, batch_id=batch_id)
            
        results.append(res)
        
        # Rate limit delay (6s) between dispatches
        if idx < total - 1:
            time.sleep(6)
            
    sent_count = sum(1 for r in results if r.get("status") == "success")
    
    # Telegram summary alert
    send_telegram_notification(f"<b>Multi-City FOIA Dispatch Complete</b>\nDispatched to <b>{sent_count}/{total}</b> municipalities.")
    
    return {"status": "success", "dispatched": sent_count, "total": total, "results": results, "batch_id": batch_id}

# Backwards compatibility wrapper
def send_foia_email(custom_subject=None, custom_body=None, custom_recipient=None):
    return send_all_foia_requests()

def check_inbox():
    """
    Connects via IMAP to check recent messages for responses or CSV/Excel attachments from any target municipality.
    """
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    email_user = os.getenv("SENDER_EMAIL")
    email_pass = os.getenv("SENDER_PASSWORD")
    
    target_domains = ["myboca.us", "mydelraybeach.com", "coconutcreek.net", "cityofparkland.org", "townofhillsborobeach.com"]
    target_emails = [t["email"].lower() for t in TARGET_MUNICIPALITIES]
    
    if not email_user or not email_pass:
        return {"status": "error", "message": "IMAP credentials not configured"}
        
    try:
        with IMAPClient(imap_server, use_uid=True) as server:
            server.login(email_user, email_pass)
            server.select_folder('INBOX')
            
            messages = server.search(['ALL'])
            recent_uids = messages[-25:] if len(messages) > 25 else messages
            
            logs = []
            for uid in reversed(recent_uids):
                fetch_data = server.fetch([uid], 'RFC822')
                if not fetch_data or uid not in fetch_data:
                    continue
                    
                message_data = fetch_data[uid]
                email_message = email.message_from_bytes(message_data[b'RFC822'])
                
                subject_header = email_message.get("Subject", "No Subject")
                decoded_list = decode_header(subject_header)
                subject, encoding = decoded_list[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
                    
                sender = email_message.get("From", "").lower()
                
                has_attachment = False
                attachment_name = ""
                
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue
                        filename = part.get_filename()
                        if filename:
                            has_attachment = True
                            attachment_name = filename
                
                # Match sender against target emails/domains
                is_target_sender = any(em in sender for em in target_emails) or any(dom in sender for dom in target_domains)
                is_foia_related = "foia" in subject.lower() or "public record" in subject.lower() or "code" in subject.lower()
                
                if is_target_sender or has_attachment or is_foia_related:
                    log_response(subject, sender, has_attachment, attachment_name)
                    logs.append({"subject": subject, "sender": sender, "attachment": attachment_name})
                    
                    # Notify via Telegram
                    attach_msg = f"\nAttachment: {attachment_name}" if has_attachment else ""
                    send_telegram_notification(f"<b>New Inbox Activity Detected</b>\nFrom: {sender}\nSubject: {subject}{attach_msg}")
                
        return {"status": "success", "count": len(logs), "logs": logs}
        
    except Exception as e:
        print(f"IMAP Error: {e}")
        return {"status": "error", "message": str(e)}
