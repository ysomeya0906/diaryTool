import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "DiaryData")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

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
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
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
            return row.iloc[0].get('TomorrowPlan', None)
    except Exception as e:
        print(f"Error getting yesterday plan: {e}")
    return None

def get_ai_advice(experience, feelings, ideas, tomorrow_plan):
    if not GEMINI_API_KEY:
        return "AI API Key not found. Please configure GEMINI_API_KEY."
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        あなたは就職活動中の学生をサポートするメンターAIです。
        以下の日記の内容を分析し、明日以降の生活や就活に活かせるアドバイス、成長の可視化、励ましの言葉をください。
        
        【日記内容】
        1. 経験したこと: {experience}
        2. 感じたこと・気づいたこと: {feelings}
        3. 新しいアイデア: {ideas}
        4. 明日の予定: {tomorrow_plan}
        
        【指示】
        - 簡潔に300文字以内でまとめてください。
        - 成長している点、身につけつつある能力を具体的に指摘してください。
        - もし改善点や「ノイズ」（無駄な悩みなど）があれば、ポジティブに評価・指摘してください。
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Error: {str(e)}"

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
    
    # Check duplicate? GSpread doesn't have PK. 
    # Logic: Delete existing row with same date, then append new.
    # But filtering and deleting in GSpread is slow.
    # For simplicity: Just append. User can clean up or we can add logic later.
    
    experience = data.get('experience')
    feelings = data.get('feelings')
    ideas = data.get('ideas')
    tomorrow_plan = data.get('tomorrow_plan')
    
    advice = get_ai_advice(experience, feelings, ideas, tomorrow_plan)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    sheet = get_sheet()
    if sheet:
        # Check if date exists and update?
        # Implementing simple visual check: just list all.
        try:
            # Find cell with date?
            # cells = sheet.findall(date)
            # if cells: ... too complex for now to robustly handle row deletion without ID.
            # Just append.
            row = [date, experience, feelings, ideas, tomorrow_plan, advice, timestamp]
            sheet.append_row(row)
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
    else:
        return jsonify({"status": "error", "message": "Database (Sheet) unavailable"})
    
    return jsonify({"status": "success", "advice": advice})

@app.route('/api/history')
def get_history():
    df = load_data_df()
    if not df.empty:
        df = df.sort_values(by='Date', ascending=False)
        return df.to_json(orient='records')
    return jsonify([])

if __name__ == '__main__':
    app.run(debug=True, port=5000)
