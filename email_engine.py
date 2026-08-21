import os
import time
import smtplib
import email
import re
import html as html_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from imapclient import IMAPClient
from google import genai
import json
import traceback
import requests

from database import get_setting, log_request, log_response, set_setting, update_request_by_id, DATABASE_PATH

RECENT_INBOX_BACKFILL_WINDOW = 200

ATTACHMENTS_DIR = os.path.join(os.path.dirname(DATABASE_PATH), "attachments") if os.path.exists(os.path.dirname(DATABASE_PATH)) and os.path.dirname(DATABASE_PATH) else "attachments"
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)


def _extract_text_from_html(html_content):
    if not html_content:
        return ""

    text = re.sub(r'(?is)<(script|style).*?>.*?</\1>', ' ', html_content)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</p\s*>', '\n\n', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    text = re.sub(r'\r\n?', '\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _decode_message_part(part):
    charset = part.get_content_charset() or 'utf-8'
    payload = part.get_payload(decode=True)
    if payload is None:
        raw_payload = part.get_payload()
        if isinstance(raw_payload, str):
            return raw_payload
        if isinstance(raw_payload, bytes):
            payload = raw_payload
    if payload is None:
        return ""
    try:
        return payload.decode(charset, errors='replace')
    except Exception:
        return payload.decode('utf-8', errors='replace')

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
    {"name": "City of Coral Springs", "email": "+19543441016", "type": "fax"},
    {"name": "City of Boynton Beach", "email": "cityclerk@bbfl.us", "type": "email"},
    {"name": "City of Pompano Beach", "email": "", "type": "none"},
    {"name": "Village of Sea Ranch Lakes", "email": "", "type": "none"},
    {"name": "City of Lauderhill", "email": "+19547303062", "type": "fax"},
    {"name": "City of Fort Lauderdale", "email": "PropertyRecords@fortlauderdale.gov", "type": "email"},
    {"name": "City of Aventura", "email": "", "type": "none"},
    {"name": "City of Atlantis", "email": "", "type": "none"},
    {"name": "City of Avon Park", "email": "chardman@avonpark.city", "type": "email"},
    {"name": "City of Plantation", "email": "cityclerk@plantation.org", "type": "email"},
    {"name": "City of Belle Glade", "email": "cityclerk@bellegladegov.com", "type": "email"},
    {"name": "City of Bonita Springs", "email": "cityclerk@cityofbonitasprings.org", "type": "email"},
    {"name": "City of Doral", "email": "cityclerk@cityofdoral.com", "type": "email"},
    {"name": "City of Bradenton", "email": "cityclerk@cityofbradenton.com", "type": "email"},
    {"name": "City of Cape Coral", "email": "ctyclk@capecoral.gov", "type": "email"},
    {"name": "City of Clearwater", "email": "cityclerk@myclearwater.com", "type": "email"},
    {"name": "City of Clewiston", "email": "clerk@clewiston-fl.gov", "type": "email"},
    {"name": "City of Cocoa Beach", "email": "cityclerk@cityofcocoabeach.com", "type": "email"},
    {"name": "City of Cooper City", "email": "cityclerk@coopercityfl.org", "type": "email"},
    {"name": "City of Coral Gables", "email": "cityclerk@coralgables.com", "type": "email"},
    {"name": "City of Dania Beach", "email": "cityclerk@daniabeachfl.gov", "type": "email"},
    {"name": "City of Daytona Beach", "email": "clerk@codb.us", "type": "email"},
    {"name": "City of Florida City", "email": "cityclerk@floridacityfl.gov", "type": "email"},
    {"name": "City of Fort Pierce", "email": "cityclerk@cityoffortpierce.com", "type": "email"},
    {"name": "City of Gainesville", "email": "cityclerk@gainesvillefl.gov", "type": "email"},
    {"name": "City of Greenacres", "email": "cityclerk@greenacresfl.gov", "type": "email"},
    {"name": "City of Hallandale Beach", "email": "cityclerks@cohb.org", "type": "email"},
    {"name": "City of Hialeah", "email": "cityclerk@hialeahfl.gov", "type": "email"},
    {"name": "City of Hialeah Gardens", "email": "mjoffee@cityofhialeahgardens.com", "type": "email"},
    {"name": "City of Hollywood", "email": "pcerny@hollywoodfl.org", "type": "email"},
    {"name": "City of Homestead", "email": "cityrecords@homesteadfl.gov", "type": "email"},
    {"name": "City of Jacksonville", "email": "", "type": "none"},
    {"name": "City of Key West", "email": "Clerk@cityofkeywest-fl.gov", "type": "email"},
    {"name": "City of Kissimmee", "email": "cityclerk@kissimmee.gov", "type": "email"},
    {"name": "City of Lake Worth Beach", "email": "cityclerk@lakeworthbeachfl.gov", "type": "email"},
    {"name": "City of Lakeland", "email": "cityclerk@lakelandgov.net", "type": "email"},
    {"name": "City of Marco Island", "email": "cityclerk@cityofmarcoisland.com", "type": "email"},
    {"name": "City of Melbourne", "email": "city.clerk@mlbfl.org", "type": "email"},
    {"name": "City of Miami", "email": "cityclerk@miamigov.com", "type": "email"},
    {"name": "City of Miami Beach", "email": "cityclerk@miamibeachfl.gov", "type": "email"},
    {"name": "City of Miami Gardens", "email": "mbataille@miamigardens-fl.gov", "type": "email"},
    {"name": "City of Miramar", "email": "clerksoffice@miramarfl.gov", "type": "email"},
    {"name": "City of Naples", "email": "", "type": "none"},
    {"name": "City of North Lauderdale", "email": "clerk@nlauderdale.org", "type": "email"},
    {"name": "City of North Miami", "email": "cityclerk@northmiamifl.gov", "type": "email"},
    {"name": "City of North Miami Beach", "email": "cityclerk@citynmb.com", "type": "email"},
    {"name": "City of Oakland Park", "email": "", "type": "none"},
    {"name": "City of Ocala", "email": "clerk@ocalafl.gov", "type": "email"},
    {"name": "City of Okeechobee", "email": "lgamiotea@cityofokeechobee.com", "type": "email"},
    {"name": "City of Opa-locka", "email": "cityclerk@opalockafl.gov", "type": "email"},
    {"name": "City of Orlando", "email": "records@orlando.gov", "type": "email"},
    {"name": "City of Pahokee", "email": "cityclerk@cityofpahokee.com", "type": "email"},
    {"name": "City of Palm Bay", "email": "cityclerk@pbfl.org", "type": "email"},
    {"name": "City of Palm Beach Gardens", "email": "cityclerk@pbgfl.com", "type": "email"},
    {"name": "City of Panama City", "email": "cityclerk@panamacity.gov", "type": "email"},
    {"name": "City of Pembroke Pines", "email": "+19545178402", "type": "fax"},
    {"name": "City of Pensacola", "email": "cityclerk@cityofpensacola.com", "type": "email"},
    {"name": "City of Port St. Lucie", "email": "", "type": "none"},
    {"name": "City of Riviera Beach", "email": "cityclerk@rivierabeach.org", "type": "email"},
    {"name": "City of Sarasota", "email": "cityclerk@sarasotafl.gov", "type": "email"},
    {"name": "City of Sebastian", "email": "cityclerk@cityofsebastian.com", "type": "email"},
    {"name": "City of Sebring", "email": "KathyHaley@mysebring.com", "type": "email"},
    {"name": "City of South Bay", "email": "", "type": "none"},
    {"name": "City of South Miami", "email": "cityclerk@southmiamifl.gov", "type": "email"},
    {"name": "City of St. Augustine", "email": "cityclerk@citystaug.com", "type": "email"},
    {"name": "City of St. Petersburg", "email": "cityclerk@stpete.org", "type": "email"},
    {"name": "City of Sunny Isles Beach", "email": "cityclerk@sibfl.net", "type": "email"},
    {"name": "City of Sunrise", "email": "CityClerk@sunrisefl.gov", "type": "email"},
    {"name": "City of Sweetwater", "email": "", "type": "none"},
    {"name": "City of Tallahassee", "email": "records@talgov.com", "type": "email"},
    {"name": "City of Tamarac", "email": "CityClerk@Tamarac.org", "type": "email"},
    {"name": "City of Tampa", "email": "publicrecords@tampagov.net", "type": "email"},
    {"name": "City of Titusville", "email": "Cityrecords@Titusville.com", "type": "email"},
    {"name": "City of Vero Beach", "email": "cityclerk@covb.org", "type": "email"},
    {"name": "City of West Palm Beach", "email": "cityclerk@wpb.org", "type": "email"},
    {"name": "City of Westlake", "email": "publicrecords@westlakegov.com", "type": "email"},
    {"name": "City of Weston", "email": "cityclerk@westonfl.org", "type": "email"},
    {"name": "City of Wilton Manors", "email": "cityclerk@wiltonmanors.com", "type": "email"},
    {"name": "City of Winter Haven", "email": "records@mywinterhaven.com", "type": "email"},
    {"name": "Town of Bay Harbor Islands", "email": "eherbello@bayharborislands-fl.gov", "type": "email"},
    {"name": "Town of Briny Breezes", "email": "townclerk@townofbrinybreezes-fl.gov", "type": "email"},
    {"name": "Town of Cloud Lake", "email": "clerk@cloudlakefl.us", "type": "email"},
    {"name": "Town of Cutler Bay", "email": "townclerk@cutlerbay-fl.gov", "type": "email"},
    {"name": "Town of Davie", "email": "townclerk@davie-fl.gov", "type": "email"},
    {"name": "Town of Glen Ridge", "email": "", "type": "none"},
    {"name": "Town of Golden Beach", "email": "lperez@goldenbeach.us", "type": "email"},
    {"name": "Town of Haverhill", "email": "publicrecordsrequest@haverhillma.gov", "type": "email"},
    {"name": "Town of Hypoluxo", "email": "HYPOLUXO@HYPOLUXO.ORG", "type": "email"},
    {"name": "Town of Juno Beach", "email": "townclerk@juno-beach.fl.us", "type": "email"},
    {"name": "Town of Jupiter", "email": "townclerk@jupiter.fl.us", "type": "email"},
    {"name": "Town of Jupiter Inlet Colony", "email": "", "type": "none"},
    {"name": "Town of Lake Clarke Shores", "email": "mpinkerman@lakeclarke.org", "type": "email"},
    {"name": "Town of Lake Park", "email": "townclerk@lakeparkflorida.gov", "type": "email"},
    {"name": "Town of Lantana", "email": "", "type": "none"},
    {"name": "Town of Lauderdale-by-the-Sea", "email": "townclerk@lbts-fl.gov", "type": "email"},
    {"name": "Town of Loxahatchee Groves", "email": "prr@loxahatcheegrovesfl.gov", "type": "email"},
    {"name": "Town of Manalapan", "email": "Epetersen@manalapan.org", "type": "email"},
    {"name": "Town of Mangonia Park", "email": "clerk@townofmangoniapark.com", "type": "email"},
    {"name": "Town of Medley", "email": "townclerk@townofmedley.com", "type": "email"},
    {"name": "Town of Miami Lakes", "email": "clerk@miamilakes-fl.gov", "type": "email"},
    {"name": "Town of Ocean Breeze", "email": "townclerk@townofoceanbreeze.org", "type": "email"},
    {"name": "Town of Ocean Ridge", "email": "info@oceanridgeflorida.com", "type": "email"},
    {"name": "Town of Orchid", "email": "townclerk@townoforchid.com", "type": "email"},
    {"name": "Town of Palm Beach", "email": "townclerk@townofpalmbeach.com", "type": "email"},
    {"name": "Town of Pembroke Park", "email": "townclerk@townofbrinybreezes-fl.gov", "type": "email"},
    {"name": "Town of Sewall's Point", "email": "clerk@sewallspoint.org", "type": "email"},
    {"name": "Town of South Palm Beach", "email": "ydavenport@southpalmbeach.com", "type": "email"},
    {"name": "Town of Southwest Ranches", "email": "Records@Southwestranches.org", "type": "email"},
    {"name": "Town of Stuart", "email": "cityclerk@ci.stuart.fl.us", "type": "email"},
    {"name": "Town of Surfside", "email": "clerk@townofsurfsidefl.gov", "type": "email"},
    {"name": "Town of West Miami", "email": "anneryg@cityofwestmiami.gov", "type": "email"},
    {"name": "Village of Bal Harbour", "email": "records@balharbourfl.gov", "type": "email"},
    {"name": "Village of Biscayne Park", "email": "villageclerk@biscayneparkfl.gov", "type": "email"},
    {"name": "Village of Golf", "email": "", "type": "none"},
    {"name": "Village of Indian Creek", "email": "clerk@indiancreekvillagefl.gov", "type": "email"},
    {"name": "Village of Key Biscayne", "email": "clerk@keybiscayne.fl.gov", "type": "email"},
    {"name": "Village of North Bay Village", "email": "villageclerk@nbvillage.com", "type": "email"},
    {"name": "Village of Palm Springs", "email": "clerk@vpsfl.org", "type": "email"},
    {"name": "Village of Palmetto Bay", "email": "clerk@palmettobay-fl.gov", "type": "email"},
    {"name": "Village of Pinecrest", "email": "clerk@pinecrest-fl.gov", "type": "email"},
    {"name": "Village of Royal Palm Beach", "email": "clerk@royalpalmbeachfl.gov", "type": "email"},
    {"name": "Village of Tequesta", "email": "", "type": "none"},
    {"name": "Village of Virginia Gardens", "email": "clerk@virginiagardens-fl.gov", "type": "email"},
    {"name": "Village of Wellington", "email": "clerk@wellingtonfl.gov", "type": "email"}
]

TARGET_COUNTIES = [
    {"name": "Alachua County", "email": "osr@alachuaclerk.org", "type": "email"},
    {"name": "Brevard County", "email": "", "type": "none"},
    {"name": "Broward County", "email": "", "type": "none"},
    {"name": "Collier County", "email": "PublicRecordRequest@collier.gov", "type": "email"},
    {"name": "Duval County", "email": "public.info@duvalclerk.com", "type": "email"},
    {"name": "Escambia County", "email": "admin@myescambia.com", "type": "email"},
    {"name": "Hendry County", "email": "emily.hunter@hendryfla.net", "type": "email"},
    {"name": "Highlands County", "email": "clkbusor@hcclerk.org", "type": "email"},
    {"name": "Hillsborough County", "email": "publicrecords@hillsclerk.com", "type": "email"},
    {"name": "Indian River County", "email": "clerk@indianriverclerk.com", "type": "email"},
    {"name": "Lee County", "email": "", "type": "none"},
    {"name": "Leon County", "email": "BOCCPublicRecordsRequests@leoncountyfl.gov", "type": "email"},
    {"name": "Manatee County", "email": "public.records@mymanatee.org", "type": "email"},
    {"name": "Marion County", "email": "PublicRecords@MarionFL.org", "type": "email"},
    {"name": "Martin County", "email": "RecordRequest@MartinClerk.com", "type": "email"},
    {"name": "Miami-Dade County", "email": "cocpubreq@miamidadeclerk.gov", "type": "email"},
    {"name": "Monroe County", "email": "", "type": "none"},
    {"name": "Okeechobee County", "email": "records@myokeeclerk.com", "type": "email"},
    {"name": "Orange County", "email": "PublicRecordRequest@ocfl.net", "type": "email"},
    {"name": "Osceola County", "email": "", "type": "none"},
    {"name": "Palm Beach County", "email": "publicrecords@mypalmbeachclerk.com", "type": "email"},
    {"name": "Pinellas County", "email": "clerkinfo@mypinellasclerk.gov", "type": "email"},
    {"name": "Polk County", "email": "Records@PolkClerkFL.gov", "type": "email"},
    {"name": "Sarasota County", "email": "PublicRecords@scgov.net", "type": "email"},
    {"name": "St. Johns County", "email": "publicrecords@sjcfl.us", "type": "email"},
    {"name": "St. Lucie County", "email": "aghlc.nm@gmail.com", "type": "email"},
    {"name": "Volusia County", "email": "", "type": "none"}
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
            model='gemini-2.0-flash',
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

def send_single_foia_email(city_name, target_email, custom_subject=None, custom_body=None, batch_id=None, smtp_server_session=None, record_type="Email Request"):
    """
    Sends an email via SMTP to a specific municipality target.
    """
    sender_email = os.getenv("SENDER_EMAIL", "jorge.property.123@gmail.com")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    
    if not sender_email or not sender_password:
        msg = "SMTP Credentials not configured (SENDER_EMAIL or SENDER_PASSWORD missing)."
        log_request("Failed", record_type, target_email, "N/A", msg, city_name=city_name, batch_id=batch_id)
        return {"status": "error", "message": msg, "city": city_name}

    if custom_subject and custom_body:
        subject, body = custom_subject, custom_body
    else:
        subject, body = generate_foia_content(city_name=city_name)
    
    # 1. Log in progress immediately
    req_id = log_request("Sending...", record_type, target_email, subject, "Preparing transmission...", city_name=city_name, batch_id=batch_id)
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = target_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        if smtp_server_session is not None:
            smtp_server_session.sendmail(sender_email, target_email, msg.as_string())
        else:
            with smtplib.SMTP_SSL(smtp_server, 465, timeout=15) as server:
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
    
    sender_email = os.getenv("SENDER_EMAIL", "jorge.property.123@gmail.com")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    
    smtp_session = None
    if sender_email and sender_password:
        try:
            print("Establishing SMTP SSL connection for batch...")
            smtp_session = smtplib.SMTP_SSL(smtp_server, 465, timeout=15)
            smtp_session.login(sender_email, sender_password)
            print("SMTP login successful.")
        except Exception as smtp_err:
            print(f"Failed to establish SMTP batch session: {smtp_err}. Will fallback to individual connections.")
            smtp_session = None

    try:
        sent_any = False
        for idx, target in enumerate(TARGET_MUNICIPALITIES):
            city = target["name"]
            addr = target["email"]
            dispatch_type = target.get("type", "email")
            
            if custom_drafts is not None and city not in custom_drafts:
                continue
                
            if sent_any:
                time.sleep(6)
                
            custom_sub = None
            custom_bdy = None
            if custom_drafts and city in custom_drafts:
                custom_sub = custom_drafts[city].get("subject")
                custom_bdy = custom_drafts[city].get("body")
                
            try:
                if dispatch_type == "fax":
                    from fax_engine import get_city_fax_number
                    fax_num = get_city_fax_number(city) or addr
                    res = send_single_foia_fax(city, target_fax_number=fax_num, custom_subject=custom_sub, custom_body=custom_bdy, batch_id=batch_id)
                else:
                    res = send_single_foia_email(city, addr, custom_subject=custom_sub, custom_body=custom_bdy, batch_id=batch_id, smtp_server_session=smtp_session)
                results.append(res)
                sent_any = True
            except Exception as loop_err:
                print(f"Uncaught loop error for {city}: {traceback.format_exc()}")
                results.append({"status": "error", "city": city, "message": str(loop_err)})
    finally:
        if smtp_session:
            try:
                smtp_session.quit()
                print("SMTP session closed.")
            except Exception:
                pass
            
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
            
            inbox_uids = server.search(['ALL'])
            history_backfilled = (get_setting("imap_history_backfilled", "false") or "false").lower() == "true"
            last_scanned_uid_raw = get_setting("imap_last_scanned_uid", "0") or "0"
            try:
                last_scanned_uid = int(last_scanned_uid_raw)
            except (TypeError, ValueError):
                last_scanned_uid = 0

            if history_backfilled:
                new_message_uids = [uid for uid in inbox_uids if int(uid) > last_scanned_uid]
                # Re-scan a recent window to backfill bodies that were previously stored empty.
                recent_window_uids = (
                    inbox_uids[-RECENT_INBOX_BACKFILL_WINDOW:]
                    if len(inbox_uids) > RECENT_INBOX_BACKFILL_WINDOW
                    else inbox_uids
                )
                message_uids = sorted(set(new_message_uids + recent_window_uids), key=int)
            else:
                message_uids = inbox_uids
            
            logs = []
            refreshed = 0
            for uid in reversed(message_uids):
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
                attachment_file = ""
                body_text = ""
                html_body = ""
                
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        content_disposition = part.get('Content-Disposition')
                        disposition = (content_disposition or "").lower()
                        content_type = part.get_content_type()
                        filename = part.get_filename()
                        is_text_part = content_type in ('text/plain', 'text/html')
                        has_attachment_marker = bool(filename) or ("attachment" in disposition)

                        if is_text_part and not has_attachment_marker:
                            if content_type == 'text/plain' and not body_text:
                                body_text = _decode_message_part(part)
                            elif content_type == 'text/html' and not html_body:
                                html_body = _decode_message_part(part)
                            continue

                        if has_attachment_marker:
                            has_attachment = True
                            if not filename:
                                filename = f"attachment_{uid}.bin"
                            else:
                                decoded_fn = decode_header(filename)
                                fn_part, fn_enc = decoded_fn[0]
                                if isinstance(fn_part, bytes):
                                    filename = fn_part.decode(fn_enc if fn_enc else "utf-8", errors="ignore")
                            if not attachment_name:
                                attachment_name = filename
                                
                            try:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    clean_fn = "".join(c for c in filename if c.isalnum() or c in "._- ")
                                    safe_fn = f"{uid}_{clean_fn}"
                                    dest_path = os.path.join(ATTACHMENTS_DIR, safe_fn)
                                    with open(dest_path, "wb") as f:
                                        f.write(payload)
                                    attachment_file = safe_fn
                            except Exception as save_err:
                                print(f"Error saving attachment for uid {uid}: {save_err}")
                elif email_message.get_content_type() == 'text/plain':
                    body_text = _decode_message_part(email_message)
                elif email_message.get_content_type() == 'text/html':
                    html_body = _decode_message_part(email_message)

                if not body_text and html_body:
                    body_text = _extract_text_from_html(html_body)
                body_text = (body_text or "").strip()
                
                # Match sender against target emails/domains
                is_target_sender = any(em in sender for em in target_emails) or any(dom in sender for dom in target_domains)
                is_foia_related = "foia" in subject.lower() or "public record" in subject.lower() or "code" in subject.lower()
                is_new_uid = int(uid) > last_scanned_uid
                
                if is_target_sender or has_attachment or is_foia_related:
                    response_result = log_response(
                        subject,
                        sender,
                        has_attachment,
                        attachment_name,
                        body_text,
                        imap_uid=uid,
                        include_metadata=True,
                        attachment_file=attachment_file
                    )
                    if response_result.get("body_filled") and not is_new_uid:
                        refreshed += 1
                    if is_new_uid:
                        logs.append({"subject": subject, "sender": sender, "attachment": attachment_name})
                        
                        # Notify via Telegram
                        attach_msg = f"\nAttachment: {attachment_name}" if has_attachment else ""
                        send_telegram_notification(f"<b>New Inbox Activity Detected</b>\nFrom: {sender}\nSubject: {subject}{attach_msg}")

            if inbox_uids:
                set_setting("imap_last_scanned_uid", str(max(int(uid) for uid in inbox_uids)))
            if not history_backfilled:
                set_setting("imap_history_backfilled", "true")
                
        return {"status": "success", "count": len(logs), "refreshed": refreshed, "logs": logs}
        
    except Exception as e:
        print(f"IMAP Error: {e}")
        return {"status": "error", "message": str(e)}

def sync_all_past_attachments():
    """
    Retroactively scans all emails in the IMAP mailbox, downloads all attachments to disk,
    and updates/inserts records into the database.
    """
    print("Starting retroactive sync of all past attachments from IMAP...")
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    email_user = os.getenv("SENDER_EMAIL")
    email_pass = os.getenv("SENDER_PASSWORD")
    
    if not email_user or not email_pass:
        return {"status": "error", "message": "IMAP credentials not configured"}
        
    try:
        with IMAPClient(imap_server, use_uid=True) as server:
            server.login(email_user, email_pass)
            server.select_folder('INBOX')
            inbox_uids = server.search(['ALL'])
            print(f"Retroactive sync scanning {len(inbox_uids)} total emails in inbox...")
            
            target_domains = ["myboca.us", "mydelraybeach.com", "coconutcreek.net", "cityofparkland.org", "townofhillsborobeach.com"]
            target_emails = [t["email"].lower() for t in TARGET_MUNICIPALITIES]
            
            synced_count = 0
            for uid in reversed(inbox_uids):
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
                attachment_file = ""
                body_text = ""
                html_body = ""
                
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        content_disposition = part.get('Content-Disposition')
                        disposition = (content_disposition or "").lower()
                        content_type = part.get_content_type()
                        filename = part.get_filename()
                        is_text_part = content_type in ('text/plain', 'text/html')
                        has_attachment_marker = bool(filename) or ("attachment" in disposition)
                        
                        if is_text_part and not has_attachment_marker:
                            if content_type == 'text/plain' and not body_text:
                                body_text = _decode_message_part(part)
                            elif content_type == 'text/html' and not html_body:
                                html_body = _decode_message_part(part)
                            continue
                            
                        if has_attachment_marker:
                            has_attachment = True
                            if not filename:
                                filename = f"attachment_{uid}.bin"
                            else:
                                decoded_fn = decode_header(filename)
                                fn_part, fn_enc = decoded_fn[0]
                                if isinstance(fn_part, bytes):
                                    filename = fn_part.decode(fn_enc if fn_enc else "utf-8", errors="ignore")
                            if not attachment_name:
                                attachment_name = filename
                            try:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    clean_fn = "".join(c for c in filename if c.isalnum() or c in "._- ")
                                    safe_fn = f"{uid}_{clean_fn}"
                                    dest_path = os.path.join(ATTACHMENTS_DIR, safe_fn)
                                    with open(dest_path, "wb") as f:
                                        f.write(payload)
                                    attachment_file = safe_fn
                            except Exception as save_err:
                                print(f"Error saving attachment in sync for uid {uid}: {save_err}")
                elif email_message.get_content_type() == 'text/plain':
                    body_text = _decode_message_part(email_message)
                elif email_message.get_content_type() == 'text/html':
                    html_body = _decode_message_part(email_message)
                    
                if not body_text and html_body:
                    body_text = _extract_text_from_html(html_body)
                body_text = (body_text or "").strip()
                
                is_target_sender = any(em in sender for em in target_emails) or any(dom in sender for dom in target_domains)
                is_foia_related = "foia" in subject.lower() or "public record" in subject.lower() or "code" in subject.lower()
                
                if is_target_sender or has_attachment or is_foia_related:
                    log_response(
                        subject=subject,
                        sender=sender,
                        has_attachment=has_attachment,
                        attachment_name=attachment_name,
                        body=body_text,
                        imap_uid=uid,
                        include_metadata=False,
                        attachment_file=attachment_file
                    )
                    if has_attachment:
                        synced_count += 1
                        
            print(f"Retroactive sync complete. Synced {synced_count} attachments.")
            return {"status": "success", "synced_attachments": synced_count}
    except Exception as e:
        print(f"Retroactive sync error: {e}")
        return {"status": "error", "message": str(e)}

def retroactive_sync_bodies():
    """
    Connects via IMAP, finds all responses in the database with missing or empty bodies,
    and searches the mailbox for matching messages to sync their bodies.
    """
    from database import get_connection
    import sqlite3
    
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, subject, sender FROM responses WHERE COALESCE(body, '') = ''")
        empty_rows = cursor.fetchall()
    except sqlite3.OperationalError:
        empty_rows = []
    conn.close()
    
    if not empty_rows:
        print("No empty response bodies found to sync.")
        return {"status": "success", "message": "No empty response bodies found to sync."}
        
    print(f"Found {len(empty_rows)} responses with empty bodies to sync.")
    
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    email_user = os.getenv("SENDER_EMAIL")
    email_pass = os.getenv("SENDER_PASSWORD")
    
    if not email_user or not email_pass:
        return {"status": "error", "message": "IMAP credentials not configured"}
        
    updated_count = 0
    try:
        with IMAPClient(imap_server, use_uid=True) as server:
            server.login(email_user, email_pass)
            server.select_folder('INBOX')
            
            inbox_uids = server.search(['ALL'])
            print(f"Scanning {len(inbox_uids)} total emails for matching subjects...")
            
            chunk_size = 100
            uid_chunks = [inbox_uids[i:i + chunk_size] for i in range(0, len(inbox_uids), chunk_size)]
            
            subject_map = {}
            
            for chunk in uid_chunks:
                fetch_data = server.fetch(chunk, ['ENVELOPE'])
                for uid, msg_data in fetch_data.items():
                    envelope = msg_data.get(b'ENVELOPE')
                    if not envelope:
                        continue
                    
                    subj_bytes = envelope.subject
                    subj = ""
                    if subj_bytes:
                        decoded_list = decode_header(subj_bytes.decode('utf-8', errors='ignore'))
                        subj_part, enc = decoded_list[0]
                        if isinstance(subj_part, bytes):
                            subj = subj_part.decode(enc if enc else 'utf-8', errors='ignore')
                        else:
                            subj = subj_part
                    
                    subj_clean = subj.lower().strip()
                    subject_map[subj_clean] = uid
            
            for row in empty_rows:
                row_id = row['id']
                row_subj = row['subject'].lower().strip()
                
                matched_uid = subject_map.get(row_subj)
                if matched_uid:
                    fetch_msg = server.fetch([matched_uid], 'RFC822')
                    if fetched_data := fetch_msg.get(matched_uid):
                        email_message = email.message_from_bytes(fetched_data[b'RFC822'])
                        body_text = ""
                        html_body = ""
                        
                        if email_message.is_multipart():
                            for part in email_message.walk():
                                if part.get_content_maintype() == 'multipart':
                                    continue
                                content_type = part.get_content_type()
                                if content_type == 'text/plain' and not body_text:
                                    body_text = _decode_message_part(part)
                                elif content_type == 'text/html' and not html_body:
                                    html_body = _decode_message_part(part)
                        else:
                            if email_message.get_content_type() == 'text/plain':
                                body_text = _decode_message_part(email_message)
                            elif email_message.get_content_type() == 'text/html':
                                html_body = _decode_message_part(email_message)
                                
                        if not body_text and html_body:
                            body_text = _extract_text_from_html(html_body)
                        body_text = (body_text or "").strip()
                        
                        if body_text:
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE responses SET body = ?, imap_uid = ? WHERE id = ?",
                                (body_text, str(matched_uid), row_id)
                            )
                            conn.commit()
                            conn.close()
                            updated_count += 1
                            print(f"Successfully backfilled body for response ID {row_id} using IMAP UID {matched_uid}.")
                            
    except Exception as e:
        import traceback
        print(f"Error in retroactive body sync: {traceback.format_exc()}")
        
    print(f"Retroactive body sync completed. Updated {updated_count} responses.")
    return {"status": "success", "updated_count": updated_count}

def generate_lis_pendens_content(county_name):
    """
    Generates Lis Pendens email copy using dynamic variables:
    {county_name}, {start_date} (last 30 days), and {end_date} (current date).
    """
    from database import get_setting
    import datetime
    
    end_dt = datetime.datetime.now()
    days_offset = int(get_setting("start_date_days_ago", "30") or "30")
    start_dt = end_dt - datetime.timedelta(days=days_offset)
    
    start_date_str = start_dt.strftime("%B %d, %Y")
    end_date_str = end_dt.strftime("%B %d, %Y")
    
    custom_template = get_setting("lis_pendens_template")
    if not custom_template:
        from database import DEFAULT_LIS_PENDENS_TEMPLATE
        custom_template = DEFAULT_LIS_PENDENS_TEMPLATE
        
    clean_name = county_name.replace(" County", "").strip()
    
    body = custom_template.replace("{county_name}", clean_name)
    body = body.replace("{start_date}", start_date_str)
    body = body.replace("{end_date}", end_date_str)
    
    subject = f"Florida Chapter 119 Public Records Request - Lis Pendens & Foreclosures - {county_name}"
    return subject, body

def send_single_county_request(county_name):
    """
    Sends the Lis Pendens public records request to a single county target.
    """
    county = next((c for c in TARGET_COUNTIES if c["name"] == county_name), None)
    if not county:
        return {"status": "error", "message": f"County {county_name} not found"}
        
    recipient = county["email"]
    subject, body = generate_lis_pendens_content(county_name)
    
    return send_single_foia_email(
        city_name=county_name,
        target_email=recipient,
        custom_subject=subject,
        custom_body=body,
        record_type="County Lis Pendens Email"
    )

