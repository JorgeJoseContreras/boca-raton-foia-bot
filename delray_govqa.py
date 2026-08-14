import asyncio
import os
import datetime
from playwright.async_api import async_playwright
from database import log_request, get_setting

def run_delray_govqa_submission_sync(custom_text=None):
    try:
        return asyncio.run(submit_delray_govqa_request(custom_text))
    except Exception as e:
        print(f"Error in sync delray submission: {e}")
        return {"status": "error", "message": str(e)}

async def submit_delray_govqa_request(custom_text=None):
    email = "Jorge.properties.123@gmail.com"
    password = "koolkidkluB1!"
    
    dept = get_setting("delray_dept", "Code Enforcement")
    rtype = get_setting("delray_record_type", "Code Violations")
    template = custom_text or get_setting("foia_template")
    
    days_ago = int(get_setting("start_date_days_ago", "30"))
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days_ago)).strftime("%m/%d/%Y")
    
    print(f"Starting Delray Beach GovQA Playwright submission... Dept: {dept}, Type: {rtype}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto("https://city-delraybeach.govqa.us/WEBAPP/_rs/supporthome.aspx", wait_until="networkidle")
            
            # Click Submit a Request
            await page.get_by_role("link", name="Submit a Request").click()
            await page.wait_for_load_state("networkidle")
            
            # Check login
            email_field = page.locator("input[name*='Email'], input[id*='Email']")
            if await email_field.count() > 0 and await email_field.first.is_visible():
                print("Logging in to GovQA...")
                await email_field.first.fill(email)
                await page.locator("input[type='password']").first.fill(password)
                await page.locator("input[value='Submit'], button:has-text('Submit')").first.click()
                await page.wait_for_load_state("networkidle")
                
            print(f"Post-login URL: {page.url}")
            
            # Select Department
            selects = await page.locator("select").all()
            if len(selects) >= 1:
                await selects[0].select_option(label=dept)
                await page.wait_for_timeout(1000)
                
            # Select Record Type
            if len(selects) >= 2:
                await selects[1].select_option(label=rtype)
                await page.wait_for_timeout(1000)
                
            # Fill description text
            textareas = await page.locator("textarea").all()
            if len(textareas) > 0:
                await textareas[0].fill(template)
                
            # Select preferred method radio if present
            radios = await page.locator("input[type='radio']").all()
            if len(radios) > 0:
                await radios[0].check()
                
            print("Form successfully filled via Playwright!")
            
            # Submit form
            submit_btn = page.locator("input[value='Submit'], button:has-text('Submit')").last
            await submit_btn.click()
            await page.wait_for_load_state("networkidle")
            
            ref_num = "Submitted (GovQA Portal)"
            log_request("Sent (GovQA Portal)", "Web Form", "city-delraybeach.govqa.us", f"GovQA Request - {dept}", template[:150], city_name="City of Delray Beach")
            
            await browser.close()
            return {"status": "success", "city": "City of Delray Beach", "method": "GovQA Portal", "reference": ref_num}
            
        except Exception as e:
            print(f"Delray GovQA error: {e}")
            await browser.close()
            return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    res = run_delray_govqa_submission_sync()
    print("Test Result:", res)
