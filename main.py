import re
import os
import time
# from google.genai.errors import ServerError
# from langchain_anthropic import ChatAnthropic
# from langchain_google_genai.chat_models import GoogleAPIError
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from model import DistrictOfficer, District, PoliceStation
from playwright.sync_api import sync_playwright
import json
from langchain_ollama import ChatOllama


load_dotenv()

OLLAMA_HOST_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL", "deepseek-v4-pro")
OLLAMA_API_KEY_VALUE = os.getenv("OLLAMA_API_KEY")

if not OLLAMA_API_KEY_VALUE:
    raise ValueError("Missing OLLAMA_API_KEY in environment or .env")

# Initialize the LLM
# NOTE: model names on Ollama Cloud are versioned (e.g. "deepseek-v4-pro:0813").
# "deepseek-v4-pro" alone resolves to the latest tag, and a 404 here means the
# client is pointing at the wrong host (localhost instead of ollama.com).
llm = ChatOllama(
    model=OLLAMA_MODEL_NAME,
    temperature=0,
    base_url=OLLAMA_HOST_URL,
    format="json",  # DeepSeek on Ollama Cloud ignores json-schema `format`, but honours "json"
    client_kwargs={
        "headers": {"Authorization": f"Bearer {OLLAMA_API_KEY_VALUE}"},
        "timeout": 300.0,
    },
)


def _invoke_structured(prompt: str) -> dict:
    """Call the LLM in JSON mode and validate the output against the District schema."""
    last_error: Exception | None = None

    # The model can still wrap the object in a list, so try both shapes before giving up.
    candidates = (
        f"{prompt}\n\nReturn ONLY a single JSON object (no markdown, no code fences, no commentary).",
        f"{prompt}\n\nReturn ONLY a JSON array containing exactly one object with this shape.",
    )

    for instruction in candidates:
        try:
            response = llm.invoke(instruction)
            return District.model_validate_json(response.content).model_dump()
        except Exception as e:  # noqa: BLE001 - retried below with a different instruction
            last_error = e

    raise RuntimeError(f"LLM returned data that did not match the District schema: {last_error}")


# Attach the Pydantic schema so the model knows the exact JSON shape it must produce
structured_llm = _invoke_structured

def extract_police_contacts(raw_website_text: str, max_retries: int = 3):
    prompt = f""" 
    You are an expert data extractor and fact-checker for a Tamil Nadu news portal.
    Extract the contact details of the Police Unit (District or City) from the following text.
    
    CRITICAL OVERRIDE INSTRUCTION: 
    The provided text may contain outdated IPS officer names. You must cross-reference and update 
    the 'officer_name' field for the District/City Heads to the current active officer for 2026. If the raw text says "Vacant", keep it as "Vacant".
    
    STRUCTURE RULES:
    The text might represent a "District" or a "City". Populate ONLY the officer categories that appear in the raw text. 
    - For Districts: Look for SP, ADSP, DSP.
    - For Cities: Look for COP, ACOP, JCP, DCP, ADC, ACP.
    
    Data to extract for EACH Officer type found:
            - Officer Name 
            - District Name
            - Contact Number
            - Email
    

    Data to extract for SUPERINTENDENT OF POLICE (SP):
            - Officer Name 
            - District Name
            - Contact Number
            - Email

    Data to extract for ADDITIONAL SUPERINTENDENT OF POLICE (ADSP):
            - Officer Name 
            - District Name
            - Contact Number
            - Email

    Data to extract for DEPUTY SUPERINTENDENT OF POLICE (DSP):
            - Officer Name 
            - District Name
            - Contact Number
            - Email

    
    Data to extract for COMMISSIONER OF POLICE - COP:
            - Officer Name 
            - District Name
            - Contact Number
            - Email
        
    Data to extract for ADDITIONAL COMMISSIONER OF POLICE - COP:
            - Officer Name 
            - District Name
            - Contact Number
            - Email
    
    Data to extract for JOINT COMMISSIONER OF POLICE - JCP:
            - Officer Name 
            - District Name
            - Contact Number
            - Email
    
    Data to extract for DEPUTY COMMISSIONER OF POLICE - DCP:
            - Officer Name 
            - District Name
            - Contact Number
            - Email

    Data to extract for ADDITIONAL DEPUTY COMMISSIONER OF POLICE - ADC:
            - Officer Name 
            - District Name
            - Contact Number
            - Email

    Data to extract for ASSISTANT COMMISSIONER OF POLICE - ACP:
            - Officer Name 
            - District Name
            - Contact Number
            - Email
    
    Data to extract for each Police Station under this unit:
        - station_name (Strictly use this key, do NOT use 'police_station_name')
        - officer_name
        - landline_number
        - mobile_number
        - email
    
    Keep all phone numbers and emails exactly as they appear in the raw text. Do not invent missing data.
    Return the data strictly in the requested schema.

    JSON SCHEMA (keys must match exactly; use empty lists for categories not present):
    {District.model_json_schema()}

    Raw Text:
    {raw_website_text}    
    """

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Calling LLM (Attempt {attempt}/{max_retries})...")
            return structured_llm(prompt)
        except Exception as e:
            print(f"Encountered error: {e}")
            wait_time = attempt * 2
            print(f"Retrying in {wait_time}s...")
            time.sleep(wait_time)
                
    raise RuntimeError("LLM failed to generate valid structured data after multiple retries.")

# The Web Scraping Function
def fetch_and_extract():
    url = "https://www.police.tn.gov.in/citizenportal/contact-us/dist"
    print(f"Opening browser to interact with Angular dropdown at {url}...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Using a more generic ng-select locator for the district dropdown
            # If the specific ID is known, replace 'ng-select' with '#districtId' etc.
            dropdown_selector = "ng-select" 
            
            page.wait_for_selector(dropdown_selector, state="visible", timeout=60000)
            
            print("Page loaded. Waiting 5 seconds for Angular to fetch backend data...")
            page.wait_for_timeout(5000) 
            
            all_unit_texts = []
            
            print("Opening district dropdown...")
            page.locator(dropdown_selector).first.click(force=True)
            
            try:
                page.wait_for_selector(".ng-option", timeout=10000)
            except Exception:
                print("Dropdown didn't open. Retrying click...")
                page.locator(dropdown_selector).first.click(force=True)
                page.wait_for_selector(".ng-option", timeout=20000)
            
            num_options = page.locator(".ng-option").count()
            print(f"Found {num_options} districts.")
            
            for i in range(num_options):
                if i > 0:
                    page.locator(dropdown_selector).first.click(force=True)
                    page.wait_for_timeout(1000)
                
                option = page.locator(".ng-option").nth(i)
                district_name = option.inner_text().strip()
                
                print(f"[{i+1}/{num_options}] Extracting data for: {district_name}...")
                option.click(force=True)
                
                # Wait for the table data to load below the dropdown
                page.wait_for_timeout(3000)
                
                soup = BeautifulSoup(page.content(), 'html.parser')
                # Optional: You can target just the data table if there's a specific class (e.g., soup.find('table'))
                all_unit_texts.append(soup.get_text(separator=' ', strip=True))

            combined_text = "\n--- DISTRICT SEPARATOR ---\n".join(all_unit_texts)

        except Exception as e:
            print(f"Playwright interaction error: {e}")
            page.screenshot(path="error_state.png")
            print("Saved screenshot of the error state to error_state.png")
            combined_text = ""
        finally:
            browser.close()

        if not combined_text.strip():
            print("No text collected.")
            return ""

        print("All data collected.")
        return combined_text

if __name__ == "__main__":
    cache_file = "raw_district_police_data.txt"

    if os.path.exists(cache_file):
        print(f"Found cached data in {cache_file}. Skipping Playwright scrape...")
        with open(cache_file, "r", encoding="utf-8") as f:
            combined_text = f.read()
    else:
        print("No cached data found. Running Playwright scraper...")
        combined_text = fetch_and_extract()
        if combined_text:
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(combined_text)

    if combined_text:
        print("Processing text with DeepSeek v4 Pro in chunks...")
        
        district_chunks = [chunk.strip() for chunk in combined_text.split("--- DISTRICT SEPARATOR ---") if chunk.strip()]
        total_districts = len(district_chunks)
        
        # Create a directory to store all the individual files so they don't clutter your main folder
        output_dir = "district_json_files"
        os.makedirs(output_dir, exist_ok=True)

        for i, chunk in enumerate(district_chunks, start=1):
            print(f"\n[{i}/{total_districts}] Extracting structured data...")
            try:
                # This returns a single District dict
                district_dict = extract_police_contacts(chunk)
                
                if district_dict and "district_name" in district_dict:
                    raw_name = district_dict["district_name"]
                    
                    # Sanitize the district name to make it a safe valid filename 
                    # (e.g., "CHENNAI RAILWAYS" becomes "chennai_railways")
                    safe_name = re.sub(r'[\\/*?:"<>|]', "", raw_name).strip().replace(" ", "_").lower()
                    filename = os.path.join(output_dir, f"{safe_name}.json")
                    
                    # Write immediately to its own file
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(district_dict, f, indent=2, ensure_ascii=False)
                        
                    print(f"Successfully saved to -> {filename}")
                else:
                    print(f"Warning: LLM returned data without a 'district_name' for chunk {i}")
                
            except Exception as e:
                print(f"Failed to extract data for chunk {i}: {e}")

        print("\nAll district processing complete! Check the 'district_json_files' folder.")



#  Special units downloadable code

# import os
# import time
# from google.genai.errors import ServerError
# from langchain_anthropic import ChatAnthropic
# from langchain_google_genai.chat_models import GoogleAPIError
# import requests
# from bs4 import BeautifulSoup
# from dotenv import load_dotenv
# from model import SpecialUnitHead, PoliceContacts
# # from langchain_google_genai import ChatGoogleGenerativeAI
# from playwright.sync_api import sync_playwright

# load_dotenv()
# api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
# if not api_key:
#     raise ValueError("Missing CLAUDE_API_KEY or CLAUDE_API_KEY in environment or .env")

# # Initialize the Gemini LLM
# llm = ChatAnthropic(
#     model="claude-sonnet-4-6",
#     api_key=api_key,
#     temperature=0
# )

# # Bind the Pydantic schema to force JSON output
# structured_llm = llm.with_structured_output(PoliceContacts)


# # The Extraction Function
# def extract_police_contacts(raw_website_text:str, max_retries: int=3):
#     prompt=f""" 
#     You are an expert data extractor and fact-checker for a Tamil Nadu news portal.
#     Extract the contact details of the Special Unit heads from the following text.
    
#     CRITICAL OVERRIDE INSTRUCTION: 
#     The provided text contains outdated IPS officer names. You must cross-reference and update 
#     the 'officer_name' field to the current active officer for 2026.
#     Keep the mobile numbers, emails, and addresses exactly as they appear in the raw text.
#     Return the data strictly in the requested schema.

    
#     Raw Text:
#     {raw_website_text}    
#     """

#     for attempt in range(1, max_retries + 1):
#         try:
#             print(f"Calling Gemini API (Attempt {attempt}/{max_retries})...")
#             # Execute the Extraction
#             result = structured_llm.invoke(prompt)
#              # # Return as a standard Python dictionary ready to be sent to Django
#             return result.model_dump()
#         except (GoogleAPIError, ServerError, Exception) as e:
#             if "503" in str(e) or "UNAVAILABLE" in str(e):
#                 wait_time = attempt * 5  # Wait 5s, then 10s, then 15s
#                 print(f"Google servers busy (503). Retrying in {wait_time}s...")
#                 time.sleep(wait_time)
#             else:
#                 print(f"Encountered error: {e}")
#                 raise e
                
#     raise RuntimeError("Gemini API was unavailable after multiple retries. Please wait a minute and run again.")



# # The Web Scraping Function (WHERE YOUR URL GOES)
# def fetch_and_extract():
#     url = "https://www.police.tn.gov.in/citizenportal/contact-us/dist"
#     print(f"Opening browser to interact with Angular dropdown at {url}...")
    
#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=True)
#         context = browser.new_context(ignore_https_errors=True)
#         page = context.new_page()
        
#         try:
#             # 1. Wait for the page, but specifically wait for the input field to exist
#             page.goto(url, wait_until="domcontentloaded", timeout=60000)
#             page.wait_for_selector("#specialUnit", state="visible", timeout=60000)
            
#             print("Page loaded. Waiting 5 seconds for Angular to fetch backend data...")
#             page.wait_for_timeout(5000) 
            
#             all_unit_texts = []
            
#             # 2. Try to click and open the dropdown
#             print("Opening dropdown...")
#             page.locator("#specialUnit").click(force=True)
            
#             # 3. The Fallback Mechanism
#             try:
#                 page.wait_for_selector(".ng-option", timeout=10000)
#             except Exception:
#                 print("Dropdown didn't open. Retrying click...")
#                 page.locator("#specialUnit").click(force=True)
#                 page.wait_for_selector(".ng-option", timeout=20000)
            
#             num_options = page.locator(".ng-option").count()
#             print(f"Found {num_options} special units.")
            
#             for i in range(num_options):
#                 if i > 0:
#                     page.locator("#specialUnit").click(force=True)
#                     page.wait_for_timeout(1000)
                
#                 option = page.locator(".ng-option").nth(i)
#                 unit_name = option.inner_text().strip()
                
#                 print(f"[{i+1}/{num_options}] Extracting data for: {unit_name}...")
#                 option.click(force=True)
                
#                 page.wait_for_timeout(2000)
                
#                 soup = BeautifulSoup(page.content(), 'html.parser')
#                 all_unit_texts.append(soup.get_text(separator=' ', strip=True))

#             combined_text = "\n--- UNIT SEPARATOR ---\n".join(all_unit_texts)

#         except Exception as e:
#             print(f"Playwright interaction error: {e}")
#             # 4. If it fails again, take a picture of the screen so we can see why
#             page.screenshot(path="error_state.png")
#             print("Saved screenshot of the error state to error_state.png")
#             combined_text = ""
#         finally:
#             browser.close()

#         if not combined_text.strip():
#             print("No text collected.")
#             return {"contacts": []}

#         print("All data collected. Sending to Gemini 3.6 Flash...")
#         # extracted_data = extract_police_contacts(combined_text)
        
#         print("Extraction Complete!")
#         return combined_text


# # --- Run the Script ---
# if __name__ == "__main__":
#     cache_file = "raw_police_data.txt"

#     # Check if we already have the scraped text saved locally
#     if os.path.exists(cache_file):
#         print(f"Found cached data in {cache_file}. Skipping Playwright scrape...")
#         with open(cache_file, "r", encoding="utf-8") as f:
#             combined_text = f.read()
#     else:
#         print("No cached data found. Running Playwright scraper...")
#         # (Inside fetch_and_extract, make sure you save combined_text to cache_file)
#         combined_text = fetch_and_extract()
#         if combined_text:
#             with open(cache_file, "w", encoding="utf-8") as f:
#                 f.write(combined_text)

#     if combined_text:
#         print("Processing text with Gemini...")
#         final_json_data = extract_police_contacts(combined_text)
        
#         import json
#         with open("police_contacts.json", "w", encoding="utf-8") as f:
#             json.dump(final_json_data, f, indent=2, ensure_ascii=False)
#         print("Successfully saved structured data to police_contacts.json!")