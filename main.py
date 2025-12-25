import os
import csv
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DATA_FILE = "diary.csv"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- Helpers ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame(columns=["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"])
    try:
        df = pd.read_csv(DATA_FILE)
        return ensure_columns(df)
    except Exception:
        return pd.DataFrame(columns=["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"])

def get_yesterday_plan(today_date_str):
    df = load_data()
    if df.empty:
        return None
    
    try:
        today = datetime.strptime(today_date_str, "%Y-%m-%d")
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        
        row = df[df['Date'] == yesterday_str]
        if not row.empty:
            # Safe access in case column doesn't exist yet
            return row.iloc[0].get('TomorrowPlan', None)
    except Exception as e:
        print(f"Error getting yesterday plan: {e}")
    return None

def ensure_columns(df):
    required = ["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"]
    for col in required:
        if col not in df.columns:
            df[col] = None
    return df

def get_ai_advice(experience, feelings, ideas, tomorrow_plan):
    if not GEMINI_API_KEY:
        return "AI API Key not found. Please configure GEMINI_API_KEY."
    
    try:
        model = genai.GenerativeModel('gemini-pro')
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
    date_str = request.args.get('date') # YYYY-MM-DD
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
    
    # Generate AI Advice
    advice = get_ai_advice(experience, feelings, ideas, tomorrow_plan)
    
    df = load_data()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    new_entry = {
        "Date": date,
        "Experience": experience,
        "Feelings": feelings,
        "Ideas": ideas,
        "TomorrowPlan": tomorrow_plan,
        "Advice": advice,
        "Timestamp": timestamp
    }
    
    # Remove existing entry for same date if exists (overwrite)
    df = df[df['Date'] != date]
    
    new_df = pd.DataFrame([new_entry])
    df = pd.concat([df, new_df], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)
    
    return jsonify({"status": "success", "advice": advice})

@app.route('/api/history')
def get_history():
    df = load_data()
    if not df.empty:
        df = df.sort_values(by='Date', ascending=False)
        return df.to_json(orient='records')
    return jsonify([])

if __name__ == '__main__':
    app.run(debug=True, port=5000)
