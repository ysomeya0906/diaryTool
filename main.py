import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- Configuration ---
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "DiaryData")

# --- Google Sheets Helper ---
def get_sheet():
    if not GOOGLE_CREDENTIALS_JSON:
        print("Error: GOOGLE_CREDENTIALS_JSON not found.")
        return None
    
    try:
        # Parse JSON from string (Render Env Var) or file
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Open sheet
        try:
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        except gspread.SpreadsheetNotFound:
            print(f"Sheet '{GOOGLE_SHEET_NAME}' not found. Creating...")
            sh = client.create(GOOGLE_SHEET_NAME)
            sh.share(creds_dict['client_email'], perm_type='user', role='writer')
            sheet = sh.sheet1

        # Ensure headers
        headers = ["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"]
        if not sheet.get_all_values():
            sheet.append_row(headers)
        elif sheet.row_values(1) != headers:
            # If headers are missing or wrong in row 1, maybe prepend? 
            # For safety, let's just assume if not empty, it's fine or user manages it.
            pass
            
        return sheet
    except Exception as e:
        print(f"GSpread Error: {e}")
        return None

def load_data_df():
    sheet = get_sheet()
    if not sheet:
        return pd.DataFrame(columns=["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"])
    
    try:
        # Use get_all_values to have full control over headers
        rows = sheet.get_all_values()
        if not rows:
             return pd.DataFrame(columns=["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"])
        
        # Assume first row is headers
        headers = rows[0]
        data = rows[1:]
        
        # Create DF with original headers
        df = pd.DataFrame(data, columns=headers)
        
        # Normalize headers: Strip whitespace and Title Case (e.g. "date " -> "Date", "experience" -> "Experience")
        # Mapping dict for specific known variations if needed
        normalized_map = {}
        for col in df.columns:
            clean_col = col.strip().title() # date -> Date, tomorrowplan -> Tomorrowplan (careful with CamelCase)
            
            # Manual fixups for specific columns if Title() isn't enough
            if clean_col == "Tomorrowplan": clean_col = "TomorrowPlan"
            
            normalized_map[col] = clean_col
            
        df.rename(columns=normalized_map, inplace=True)
        
        return ensure_columns(df)
    except Exception as e:
        print(f"Error reading sheet: {e}")
        return pd.DataFrame(columns=["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"])

def ensure_columns(df):
    required = ["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"]
    for col in required:
        if col not in df.columns:
            df[col] = None
    return df

def get_yesterday_plan(today_date_str):
    df = load_data_df()
    if df.empty:
        return None
    
    try:
        today = datetime.strptime(today_date_str, "%Y-%m-%d")
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        
        # Filter (Dataframe operation)
        row = df[df['Date'] == yesterday_str]
        if not row.empty:
            # Safe access in case column doesn't exist yet
            return row.iloc[0].get('TomorrowPlan', None)
    except Exception as e:
        print(f"Error getting yesterday plan: {e}")
    return None

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/yesterday_plan')
def api_yesterday_plan():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"plan": None})
    plan = get_yesterday_plan(date_str)
    return jsonify({"plan": plan})

@app.route('/api/save', methods=['POST'])
def save_entry():
    data = request.json
    date = data.get('date')
    
    experience = data.get('experience')
    feelings = data.get('feelings')
    ideas = data.get('ideas')
    tomorrow_plan = data.get('tomorrow_plan')
    
    advice = "" # AI removed
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    sheet = get_sheet()
    if sheet:
        try:
            row = [date, experience, feelings, ideas, tomorrow_plan, advice, timestamp]
            sheet.append_row(row)
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
    else:
        return jsonify({"status": "error", "message": "Database (Sheet) unavailable"})
    
    return jsonify({"status": "success"})

@app.route('/api/history')
def get_history():
    df = load_data_df()
    if not df.empty:
        df = df.sort_values(by='Date', ascending=False)
        return df.to_json(orient='records')
    return jsonify([])

if __name__ == '__main__':
    app.run(debug=True, port=5000)
