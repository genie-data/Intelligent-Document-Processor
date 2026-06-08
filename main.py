from google import genai
import os
import shutil
import json
import time
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.genai import errors
import gspread

# --- CONFIGURATION ---
load_dotenv()

CLIENT_SECRET_FILE = 'client_secret.json'
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INCOMING_DIR = os.path.join(BASE_DIR, 'Incoming_Receipts')
PROCESSED_DIR = os.path.join(BASE_DIR, 'Processed_Receipts')
MANUAL_REVIEW_DIR = os.path.join(BASE_DIR, 'Manual_Review_Receipts')

# Ensure directories exist
os.makedirs(INCOMING_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(MANUAL_REVIEW_DIR, exist_ok=True)

# --- SETUP APIs ---
client = genai.Client()

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

creds = None
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            print("Refresh token invalid. Re-authenticating...")
            if os.path.exists('token.json'):
                os.remove('token.json')
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token:
        token.write(creds.to_json())

# Drive Setup
drive_service = build('drive', 'v3', credentials=creds)

# Sheets Setup
gc = gspread.authorize(creds)
try:
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1  # Gets the first tab
except Exception as e:
    print(f"Error accessing Google Sheet: {repr(e)}")
    print("Ensure you have shared the sheet with the Service Account email!")
    exit()

def upload_to_drive(filepath):
    print(f"Uploading {filepath} to Drive...")
    file_metadata = {
        'name': os.path.basename(filepath),
        'parents': [DRIVE_FOLDER_ID]
    }
    media = MediaFileUpload(filepath, mimetype='application/pdf')
    
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    return file.get('webViewLink')

def extract_data_with_gemini(filepath):
    print("Extracting data using Gemini AI...")
    
    sample_file = client.files.upload(file=filepath, config={'display_name': os.path.basename(filepath)})
    
    prompt = """
    You are an automated assistant for a swimming coaching business. 
    Analyze this bank transfer receipt and extract the following information:
    1. The date of the transaction (format as YYYY-MM-DD).
    2. The name of the person who paid (the parent's name / payer's name).
    3. The amount paid (only the number, e.g., 150.00).
    4. ALL transaction reference numbers present (e.g., Bank Reference No, DuitNow Ref No). Extract them as a list of strings.
    
    Return ONLY a valid JSON dictionary exactly like this:
    {"date": "2024-05-16", "parent_name": "John Doe", "amount": "150.00", "references": ["REF12345", "DUITNOW6789"]}
    Do not add any formatting like ```json or newlines outside the brackets.
    """
    max_retries = 3
    delay = 5  # Start with a 5-second wait
    response = None
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[sample_file, prompt]
            )
            break  # If successful, break out of the retry loop
        except Exception as e:
            # Check if it looks like a server-side 503 or overload issue
            if "503" in str(e) or "UNAVAILABLE" in str(e).upper():
                if attempt < max_retries - 1:
                    print(f" Gemini Server overloaded (503). Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    delay *= 2  # Double the wait time for the next attempt (backoff)
                    continue
            
            # If it's a different error or we ran out of retries, log it and clean up
            print(f"Gemini Inference failed: {e}")
            try:
                client.files.delete(name=sample_file.name)
            except:
                pass
            return {"date": "Error", "parent_name": "Error", "amount": "Error", "references": "Error"}
    
    # Clean up the file from Google's servers
    try:
        client.files.delete(name=sample_file.name)
    except Exception as e:
        print(f"Temporary file deletion failed: {e}")
    
    # Parse the response text
    try:
        if not response:
            raise ValueError("No response received from Gemini.")
            
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        data = json.loads(raw_text.strip())
        return data
    except Exception as e:
        print(f"Error parsing Gemini response: {e}\nRaw Response: {response.text if response else 'None'}")
        return {"date": "Error", "parent_name": "Error", "amount": "Error", "references": "Error"}

def process_all_receipts():
    files = [f for f in os.listdir(INCOMING_DIR) if f.lower().endswith('.pdf')]
    if not files:
        print(f"No new PDFs found in '{INCOMING_DIR}'.")
        return
        
    print(f"Found {len(files)} new receipt(s) to process.")
    
    try:
        print("Fetching existing reference numbers from Google Sheets...")
        known_refs = set()
        col_values = sheet.col_values(5)  
        for val in col_values[1:]:
            if val:
                for r in str(val).split(','):
                    if r.strip():
                        known_refs.add(r.strip())
    except Exception as e:
        print(f"Error fetching existing references: {e}")
        known_refs = set()
    
    # List to collect rows to be written in a single batch operation
    rows_to_append = []
    # Track files successfully staged for moving/deleting after the final batch write succeeds
    files_to_move = []
    files_to_delete = []

    for filename in files:
        filepath = os.path.join(INCOMING_DIR, filename)
        print(f"\n--- Processing: {filename} ---")
        
        try:
            data = extract_data_with_gemini(filepath)
            
            raw_refs = data.get('references', [])
            if not isinstance(raw_refs, list):
                raw_refs = [data.get('references')] if data.get('references') else []
            elif not raw_refs and data.get('references'):
                raw_refs = [data.get('references')]
                
            refs = [str(r).strip() for r in raw_refs if r and str(r).strip().lower() != 'error' and str(r).strip() != '']
            
            if not refs:
                print(f"Missing or invalid references extracted for {filename}. Moving to Manual Review.")
                manual_path = os.path.join(MANUAL_REVIEW_DIR, filename)
                shutil.move(filepath, manual_path)
                continue
            
            is_duplicate = False
            for r in refs:
                if r in known_refs:
                    print(f"Duplicate references '{r}' found for {filename}. Staging for deletion.")
                    is_duplicate = True
                    break
            
            if is_duplicate:
                files_to_delete.append(filepath)
                continue
            
            # 2. Drive Upload (Still happens per file, which is normal)
            drive_link = upload_to_drive(filepath)
            print("Successfully uploaded to Drive.")
            
            ref_string = ", ".join(refs)
            
            # Stage row data into our memory list instead of updating the API immediately
            row_data = [data.get('date'), data.get('parent_name'), "", data.get('amount'), ref_string, drive_link]
            rows_to_append.append(row_data)
            
            # Stage local cleanup tracking
            processed_path = os.path.join(PROCESSED_DIR, filename)
            files_to_move.append((filepath, processed_path))
            
            for r in refs:
                known_refs.add(r)
            
            # Small delay to keep Gemini / Drive API healthy
            time.sleep(13)
            
        except Exception as e:
            print(f"Failed to process {filename}: {e}")

    # --- 3. BATCH WRITE TO GOOGLE SHEETS ---
    if rows_to_append:
        print(f"\n--- Batch appending {len(rows_to_append)} rows to Google Sheets ---")
        try:
            # append_rows performs a single API call for all rows
            sheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            print("Successfully updated Google Sheets.")
            
            # Commit local file moves only AFTER the sheet updates successfully
            for src, dest in files_to_move:
                shutil.move(src, dest)
                print(f"Moved {os.path.basename(src)} to Processed folder.")
                
        except Exception as e:
            print(f"Critical error writing batch to Google Sheets: {e}")
            print("Files have been kept in the incoming folder so you don't lose data.")
            return

    # Cleanup duplicates
    for filepath in files_to_delete:
        try:
            os.remove(filepath)
            print(f"Deleted duplicate file: {os.path.basename(filepath)}")
        except Exception as e:
            print(f"Failed to delete duplicate {filepath}: {e}")

if __name__ == '__main__':
    process_all_receipts()