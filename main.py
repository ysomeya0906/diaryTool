import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# --- Config & Setup ---
load_dotenv()
st.set_page_config(page_title="Daily Growth Journal", page_icon="📓", layout="centered")

# --- Custom CSS (Glassmorphism & Dark Mode) ---
st.markdown("""
<style>
    /* Global Style */
    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
    }
    
    /* Inputs */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stDateInput>div>div>input {
        background-color: #161b22;
        color: #e6edf3;
        border: 1px solid #30363d;
        border-radius: 8px;
    }
    
    /* Cards (Container simulation) */
    .css-1r6slb0, .css-12oz5g7 {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 12px;
    }
    
    /* Highlight Box (Yesterday's Plan) */
    .highlight-box {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.2);
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 4px solid #6c5ce7;
    }
    
    /* History Card */
    .history-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 12px;
    }
    .history-date {
        font-weight: bold;
        color: #a29bfe;
        font-size: 0.9em;
    }
    .history-time {
        float: right;
        color: #6e7681;
        font-size: 0.8em;
    }
</style>
""", unsafe_allow_html=True)

# --- Config & Setup ---
load_dotenv()
st.set_page_config(page_title="Daily Growth Journal", page_icon="📓", layout="centered")

# --- Helpers ---
def get_config(key, default=None):
    # Try st.secrets first
    if key in st.secrets:
        return st.secrets[key]
    # Fallback to os.getenv
    return os.getenv(key, default)

GOOGLE_SHEET_NAME = get_config("GOOGLE_SHEET_NAME", "DiaryData")

@st.cache_resource
def get_gspread_client():
    # Try getting JSON from secrets/env
    creds_json = get_config("GOOGLE_CREDENTIALS_JSON")
    
    # Special handling for Streamlit Secrets TOML format where it might be parsed already
    # If user puts [gcp_service_account] in secrets.toml, st.secrets["gcp_service_account"] is a dict.
    # But sticking to JSON string env var for compatibility is easier for migration.
    
    creds_dict = None
    
    if creds_json:
        try:
            creds_dict = json.loads(creds_json)
        except json.JSONDecodeError:
            st.error("Error decoding GOOGLE_CREDENTIALS_JSON. Make sure it is valid JSON.")
            return None
    elif "gcp_service_account" in st.secrets:
        # Support Streamlit's native dict support if they paste contents under [gcp_service_account]
        creds_dict = dict(st.secrets["gcp_service_account"])

    if not creds_dict:
        # Debugging Info
        debug_info = f"""
        **Debug Info:**
        - `st.secrets` keys found: `{list(st.secrets.keys())}`
        - `os.environ` has `GOOGLE_CREDENTIALS_JSON`: `{bool(os.getenv('GOOGLE_CREDENTIALS_JSON'))}`
        """
        
        st.error(f"""
        ❌ **GSpread Credentials not found.**
        
        {debug_info}
        
        **For Streamlit Cloud:**
        Go to App Settings > Secrets and add:
        ```toml
        GOOGLE_SHEET_NAME = "DiaryData"
        GOOGLE_CREDENTIALS_JSON = '''
        {{
          "type": "service_account",
          ... paste your JSON here ...
        }}
        '''
        ```
        """)
        return None

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        return None

def get_sheet():
    client = get_gspread_client()
    if not client: return None
    try:
        try:
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        except gspread.SpreadsheetNotFound:
            sh = client.create(GOOGLE_SHEET_NAME)
            sh.share(json.loads(GOOGLE_CREDENTIALS_JSON)['client_email'], perm_type='user', role='writer')
            sheet = sh.sheet1
        
        # Ensure Headers
        if not sheet.get_all_values():
            sheet.append_row(["Date", "Experience", "Feelings", "Ideas", "TomorrowPlan", "Advice", "Timestamp"])
            
        return sheet
    except Exception as e:
        st.error(f"Sheet Error: {e}")
        return None

def load_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame()
    try:
        rows = sheet.get_all_values()
        if not rows: return pd.DataFrame()
        headers = rows[0]
        data = rows[1:]
        df = pd.DataFrame(data, columns=headers)
        
        # Normalize Headers
        cleaned_map = {}
        for col in df.columns:
            cleaned = col.strip().title()
            if cleaned == "Tomorrowplan": cleaned = "TomorrowPlan"
            cleaned_map[col] = cleaned
        df.rename(columns=cleaned_map, inplace=True)
        
        return df
    except Exception as e:
        st.error(f"Read Error: {e}")
        return pd.DataFrame()

def get_yesterday_plan(date_obj):
    df = load_data()
    if df.empty: return None
    try:
        yesterday = date_obj - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        row = df[df['Date'] == yesterday_str]
        if not row.empty:
            return row.iloc[0].get('TomorrowPlan')
    except:
        pass
    return None

def save_entry(date, exp, feel, ideas, plan):
    sheet = get_sheet()
    if not sheet: return False
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # simple append
        sheet.append_row([str(date), exp, feel, ideas, plan, "", timestamp])
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False

# --- UI Layout ---
st.title("Daily Growth Journal")

tab1, tab2 = st.tabs(["📝 Input", "📚 History"])

with tab1:
    date_val = st.date_input("Date", datetime.now())
    
    # Yesterday's Plan
    y_plan = get_yesterday_plan(date_val)
    if y_plan:
        st.markdown(f"""
        <div class="highlight-box">
            <b><i class="fas fa-history"></i> 昨日の「明日の予定」</b><br>
            {y_plan}
        </div>
        """, unsafe_allow_html=True)
    
    with st.form("diary_form"):
        exp = st.text_area("1. 経験したこと", placeholder="今日あった出来事は？")
        feel = st.text_area("2. 感じたこと・気づいたこと", placeholder="どう感じましたか？")
        ideas = st.text_area("3. 新しいアイデア", placeholder="思いついたことは？")
        plan = st.text_area("4. 明日の予定", placeholder="明日は何をする？")
        
        submitted = st.form_submit_button("記録する")
        
        if submitted:
            if save_entry(date_val, exp, feel, ideas, plan):
                st.success("✅ 記録しました！")
                st.balloons()
            else:
                st.error("保存に失敗しました。")

with tab2:
    st.header("History")
    if st.button("Reload"):
        st.cache_data.clear()
        
    df = load_data()
    if not df.empty and 'Date' in df.columns:
        df = df.sort_values(by="Date", ascending=False)
        
        for index, row in df.iterrows():
            ts = row.get('Timestamp', '')
            time_only = ts.split(' ')[1][:5] if ' ' in ts else ''
            
            st.markdown(f"""
            <div class="history-card">
                <div style="margin-bottom:8px;">
                    <span class="history-date">{row.get('Date')}</span>
                    <span class="history-time">{time_only}</span>
                </div>
                <div style="font-size:0.95em;">
                    <strong>Exp:</strong> {str(row.get('Experience'))[:50]}...<br>
                    <strong>Plan:</strong> {row.get('TomorrowPlan')}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("詳細を見る"):
                st.write("**経験したこと:**", row.get('Experience'))
                st.write("**感じたこと:**", row.get('Feelings'))
                st.write("**アイデア:**", row.get('Ideas'))
                st.write("**明日の予定:**", row.get('TomorrowPlan'))
    else:
        st.info("データがありません。")
