import os
import time
from playwright.sync_api import sync_playwright
import traceback
from database import log_request

TARGET_URL = "https://bocaratonfl.justfoia.com/Forms/Launch/a30f7991-2d31-4550-baf7-888e0928ae17"

def run_foia_request():
    """
    Runs the Playwright automation to submit a FOIA request.
    Returns a dictionary with status and details.
    """
    first_name = os.getenv("REQUESTOR_FIRST_NAME", "Jorge")
    last_name = os.getenv("REQUESTOR_LAST_NAME", "Contreras")
    phone = os.getenv("REQUESTOR_PHONE", "555-555-5555")
    email = os.getenv("SENDER_EMAIL", "jorge.properties.123@gmail.com")
    address = os.getenv("REQUESTOR_ADDRESS", "123 Main St")
    city = os.getenv("REQUESTOR_CITY", "Miami")
    state = os.getenv("REQUESTOR_STATE", "FL")
    zip_code = os.getenv("REQUESTOR_ZIP", "33101")
    
    record_type = "Code Compliance"
    description = (
        "Requesting a digital CSV or Excel export of active code violation cases, "
        "condemned properties, and upcoming demolition lists within the City of Boca Raton, "
        "explicitly asking for the owner's mailing address column."
    )
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Go to the JustFOIA form
            page.goto(TARGET_URL, timeout=60000)
            
            # Wait for the form to load
            page.wait_for_selector('input, textarea', timeout=30000)
            
            # We use common label/placeholder heuristics since it's a dynamic form.
            # You may need to inspect the live DOM to adjust these locators if JustFOIA updates them.
            
            def fill_field(label_text, value):
                try:
                    # Try by label first
                    locator = page.get_by_label(label_text, exact=False)
                    if locator.count() > 0:
                        locator.first.fill(value)
                        return True
                    # Try placeholder
                    locator = page.get_by_placeholder(label_text, exact=False)
                    if locator.count() > 0:
                        locator.first.fill(value)
                        return True
                except Exception as e:
                    print(f"Warning: could not fill {label_text}: {e}")
                return False

            fill_field("First Name", first_name)
            fill_field("Last Name", last_name)
            fill_field("Phone", phone)
            fill_field("Email", email)
            fill_field("Address", address)
            fill_field("City", city)
            fill_field("State", state)
            fill_field("Zip", zip_code)
            
            # Text area for description
            try:
                desc_locator = page.locator('textarea')
                if desc_locator.count() > 0:
                    desc_locator.first.fill(description)
            except Exception as e:
                print(f"Warning: could not fill description: {e}")
            
            # Record Type Dropdown (Code Compliance)
            # This can be tricky; might be a select element or a custom dropdown.
            try:
                record_type_select = page.get_by_label("Record Type", exact=False)
                if record_type_select.count() > 0:
                    try:
                        record_type_select.first.select_option(label="Code Compliance")
                    except:
                        # Maybe it's a div dropdown, click it and click option
                        record_type_select.first.click()
                        page.get_by_text("Code Compliance", exact=False).first.click()
            except Exception as e:
                print(f"Warning: could not set Record Type: {e}")
                
            # Submit button
            try:
                submit_btn = page.get_by_role("button", name="Submit")
                if submit_btn.count() == 0:
                    submit_btn = page.locator('button[type="submit"]')
                if submit_btn.count() > 0:
                    submit_btn.first.click()
                    # Wait for network idle or success message
                    page.wait_for_timeout(5000) 
            except Exception as e:
                print(f"Warning: could not click submit: {e}")
            
            browser.close()
            
        # Log to DB
        log_request("Submitted", record_type, email, description)
        
        return {"status": "success", "message": "Automation script completed successfully."}
        
    except Exception as e:
        error_msg = str(e)
        print(f"Automation Error: {traceback.format_exc()}")
        log_request("Failed", record_type, email, f"Error: {error_msg}")
        return {"status": "error", "message": error_msg}

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print("Testing automation locally...")
    res = run_foia_request()
    print(res)
