# Bank Transfer Receipt Automation Pipeline

An automated data pipeline designed for a swimming coaching business that scans incoming bank transfer receipts, extracts transaction metadata using Generative AI, validates against duplicates, archives the documents to Google Drive, and appends the structured records to a centralized Google Sheet.

## 🚀 System Architecture & Workflow

1. **Ingestion:** Scans the localized `Incoming_Receipts/` directory for raw PDF bank receipts.
2. **AI Data Extraction:** Uploads each document via the Google GenAI SDK to a `gemini-2.5-flash` model, using structured prompting to enforce strict JSON extraction (Date, Payer Name, Amount, Reference Numbers).
3. **Idempotency & Duplicate Check:** Fetches historical reference numbers from Google Sheets to screen incoming receipts, discarding duplicate entries to ensure exact once-processing.
4. **Cloud Storage Archival:** Uploads verified receipts to a specific Google Drive directory and generates a `webViewLink`.
5. **Optimized Batch Writes:** Stages valid data in memory and updates Google Sheets via a single bulk-append operations network call to prevent API rate-limiting.
6. **Local State Management:** Automatically handles file routing by moving processed documents to `Processed_Receipts/` or flagging unparseable receipts into `Manual_Review_Receipts/`.

---

## 🛠️ Tech Stack

* **Language:** Python 3.x
* **AI Core:** Google Gemini API (`google-generativeai`)
* **Cloud Storage:** Google Drive API (`googleapi-client`)
* **Database / Ledger:** Google Sheets API (`gspread`)
* **Environment Management:** `python-dotenv`

---

## 📋 Prerequisites & Credentials Setup

To run this pipeline locally, you must configure authentication with Google Cloud Platform (GCP) and Google AI Studio.

### 1. Google Workspace API Credentials
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project and enable both the **Google Drive API** and **Google Sheets API**.
3. Configure the **OAuth Consent Screen** and create an **OAuth 2.0 Client ID** (Application type: *Desktop App*).
4. Download the client secrets JSON file, rename it to `client_secret.json`, and place it in the root directory of this project.

### 2. Gemini API Key
1. Obtain an API key from [Google AI Studio](https://aistudio.google.com/).
2. Keep this key handy for your environment file configuration.

---

## ⚙️ Installation & Configuration

### 1. Clone the Repository:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git)
   cd YOUR_REPOSITORY_NAME
```

### 2. Install Dependencies:
   ```bash
   pip install -r requirements.txt
   (Note: Ensure your requirements.txt includes: google-generativeai, google-api-python-client, google-auth-oauthlib, gspread, and python-dotenv)
```
### 3. Configure Environment Variables:
Create a .env file in the root directory:
   ```bash
   GEMINI_API_KEY=your_gemini_api_key_here
   DRIVE_FOLDER_ID=your_google_drive_folder_id_here
   SPREADSHEET_ID=your_google_spreadsheet_id_here
```
### 4. Directory Preparation:
The script automatically initializes the following directory structure upon execution:

```
├── Incoming_Receipts/       # Drop new raw PDF receipts here
├── Processed_Receipts/      # Successfully processed and archived receipts
├── Manual_Review_Receipts/  # Receipts missing reference IDs or failing parsing
├── main.py
├── client_secret.json
└── .env
```
---

## 🏃‍♂️ Usage
Place your target bank receipt PDFs into the Incoming_Receipts/ directory.

Execute the runner script:

```
python main.py
```
On the first run, your browser will automatically open a window requesting you to authenticate your Google account. A token.json file will be generated locally to handle subsequent seamless executions.

---
## 🔮 Future Roadmap & Engineering Backlog
While the current production script successfully handles core automation, the following architectural upgrades are planned to improve pipeline maturity and scalability:

1. Observability: Transition from standard standard stdout print() statements to Python's robust logging module to generate persistent operational audit trails.

2. Metadata Ingestion & Reference Mapping: Implement an upstream string-sanitization pipeline to extract unique parent identifiers from filenames, mapping them against a reference data sheet to automate student assignment dynamically.

3. Defensive Testing: Introduce automated unit testing via pytest and utilize network mocking to validate API state handlers safely.

4. Orchestration: Containerize the execution environment using Docker and migrate scheduling logic to Dagster for visual asset lineage and fault-tolerant retry logic.
