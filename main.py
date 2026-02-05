import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import altair as alt
import html

# --- Config & Setup ---
load_dotenv()
st.set_page_config(page_title="Bricks", page_icon="🧱", layout="wide")

# --- Custom CSS ---
st.markdown("""
<style>
    /* Global */
    .stApp { background-color: #0d1117; color: #ffffff; }
    p, h1, h2, h3, h4, h5, h6, li, span { color: #ffffff !important; }
    
    /* Popovers (Dropdowns, Tooltips) - FORCE READABILITY */
    div[data-baseweb="popover"], div[data-baseweb="popover"] > div, div[data-baseweb="menu"], div[role="listbox"] {
        background-color: #ffffff !important;
    }
    li[role="option"], li[data-baseweb="option"], div[data-baseweb="popover"] span, div[data-baseweb="popover"] div {
        color: #000000 !important;
        background-color: #ffffff !important;
    }
    li[role="option"]:hover, li[data-baseweb="option"]:hover, li[role="option"]:focus, li[data-baseweb="option"]:focus {
        background-color: #e2e8f0 !important;
        color: #000000 !important;
    }
    li[role="option"] svg, li[data-baseweb="option"] svg { fill: #000000 !important; }

    /* Inputs */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div>div, .stNumberInput>div>div>input {
        background-color: #161b22 !important; color: #ffffff !important; border: 1px solid #30363d;
    }
    .stSelectbox svg { fill: white !important; }
    
    /* Buttons */
    div.stButton > button {
        background-color: #21262d !important; color: #ffffff !important; border: 1px solid #30363d !important;
    }
    div.stButton > button:hover {
        background-color: #30363d !important;
    }

    /* Expander */
    details > summary {
        background-color: #21262d !important; color: #ffffff !important; border: 1px solid #30363d !important; border-radius: 8px; margin-bottom: 10px;
    }
    details > summary:hover { background-color: #30363d !important; }
    details > summary svg { fill: #ffffff !important; }

    /* Bricks & Visuals */
    .block-container-list { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 5px; }
    
    .brick {
        border-radius: 3px;
        color: #000000 !important;
        font-size: 11px !important; /* Smaller text as requested */
        padding: 2px 6px;
        display: inline-flex; /* Changed to inline-flex to fit content */
        align-items: center;
        justify-content: center;
        font-weight: 700;
        cursor: help;
        border: 1px solid rgba(0,0,0,0.1);
        box-shadow: 0 1px 2px rgba(0,0,0,0.2);
        white-space: nowrap; /* Prevent text wrapping */
        overflow: hidden;
        text-overflow: ellipsis;
        min-width: 50px; /* Minimum width */
    }
    
    /* Category Colors - Adjusted for Black Text */
    .cat-science { background-color: #60a5fa; } /* Blue */
    .cat-art { background-color: #a78bfa; } /* Purple */
    .cat-play { background-color: #fb923c; } /* Orange */
    .cat-create { background-color: #34d399; } /* Green */
    .cat-house { background-color: #facc15; } /* Yellow */
    .cat-other { background-color: #9ca3af; } /* Gray */
    .cat-empty { background-color: #30363d; border: 1px dashed #4b5563; } /* Empty slot */

    /* Progress Bar Container */
    .visual-progress {
        display: flex;
        gap: 2px;
        background-color: #21262d;
        padding: 4px;
        border-radius: 6px;
        margin-bottom: 10px;
        border: 1px solid #30363d;
        overflow-x: auto; /* Allow scrolling */
    }
    .prog-brick {
        flex: 0 0 auto; /* Don't shrink */
        min-width: 4%; /* Approx 24 items fit, then scroll */
        height: 20px; /* Slightly smaller */
        border-radius: 2px;
    }
</style>
""", unsafe_allow_html=True)

# --- Category Config ---
CATEGORIES = {
    "勉強・研究": "cat-science",
    "作品鑑賞・体験": "cat-art",
    "遊び": "cat-play",
    "コンテンツ作成": "cat-create",
    "家事": "cat-house",
    "その他": "cat-other"
}

def get_cat_color(cat_name):
    # Legacy support
    if cat_name == "理工学": return "cat-science"
    return CATEGORIES.get(cat_name, 'cat-other')

# --- Helpers ---
def get_config(key, default=None):
    if key in st.secrets: return st.secrets[key]
    return os.getenv(key, default)

GOOGLE_SHEET_NAME = get_config("GOOGLE_SHEET_NAME", "DiaryData")

@st.cache_resource
def get_gspread_client():
    creds_json = get_config("GOOGLE_CREDENTIALS_JSON")
    creds_dict = None
    if creds_json:
        try: creds_dict = json.loads(creds_json)
        except: pass
    elif "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])

    if not creds_dict:
        st.error("❌ Credentials Error")
        return None

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Auth Error: {e}")
        return None

def get_sheet():
    client = get_gspread_client()
    if not client: return None
    try:
        try:
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        except gspread.SpreadsheetNotFound:
            sh = client.create(GOOGLE_SHEET_NAME)
            sh.share(json.loads(get_config("GOOGLE_CREDENTIALS_JSON"))['client_email'], perm_type='user', role='writer')
            sheet = sh.sheet1
        
        # Schema Definition
        EXPECTED_HEADERS = [
            "Date", "BlocksJSON", "NewIdeas", "FunnyEpisodes", "NextAction", 
            "TotalBlocks", "Timestamp", "DailyReflection", "ImprovementPlan", "DailyLesson"
        ]
        
        # 1. Check if sheet is empty
        if not sheet.get_all_values():
            sheet.append_row(EXPECTED_HEADERS)
            return sheet
            
        # 2. Auto-Migration: Resize columns if needed
        # If we added new fields in code, the sheet might be too narrow.
        current_col_count = sheet.col_count
        required_col_count = len(EXPECTED_HEADERS)
        
        if current_col_count < required_col_count:
            # Resize sheet to fit new columns
            sheet.resize(cols=required_col_count)
            
        # 3. Update Headers (add missing ones)
        current_headers = sheet.row_values(1)
        if len(current_headers) < required_col_count:
            # We have blank columns now (due to resize). Let's fill the headers.
            # We assume the order is appended. Re-writing the whole header row is safest.
            # Note: This overwrites custom header names if user changed them, but ensures consistency.
            date_cell = sheet.cell(1, 1).value
            if date_cell == "Date": # Simple safety check
                # Update header row to match code
                for i, header in enumerate(EXPECTED_HEADERS):
                    # +1 because gspread is 1-indexed
                    if i < len(current_headers):
                        if current_headers[i] != header:
                            # Header mismatch - Optional: Log or overwrite. 
                            # Let's overwrite to ensure matching schema for index-based writes.
                            sheet.update_cell(1, i+1, header)
                    else:
                        # New column header
                        sheet.update_cell(1, i+1, header)
                        
        return sheet
    except Exception as e:
        st.error(f"Sheet Error: {e}")
        return None

@st.cache_data(ttl=60)
def load_all_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame()
    try:
        rows = sheet.get_all_values()
        if not rows: return pd.DataFrame()
        # Handle potential column mismatch by strictly picking generic indices or mapping
        headers = rows[0]
        # Ensure we have a DF even if headers changed
        return pd.DataFrame(rows[1:], columns=headers)
    except Exception as e:
        return pd.DataFrame()

def save_daily_record(date, blocks, new_ideas, funny_ep, next_action, daily_reflection, improvement_plan, daily_lesson):
    sheet = get_sheet()
    if not sheet: return False
    try:
        blocks_json = json.dumps(blocks, ensure_ascii=False)
        total_blocks = sum(b['count'] for b in blocks)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Use findall to safely check existence without worrying about explicit Exception classes
        cells = sheet.findall(str(date), in_column=1)
        
        if cells:
            row_idx = cells[0].row
            # Update
            sheet.update_cell(row_idx, 2, blocks_json)
            sheet.update_cell(row_idx, 3, new_ideas)
            sheet.update_cell(row_idx, 4, funny_ep)
            sheet.update_cell(row_idx, 5, next_action)
            sheet.update_cell(row_idx, 6, total_blocks)
            sheet.update_cell(row_idx, 7, timestamp)
            sheet.update_cell(row_idx, 8, daily_reflection)
            sheet.update_cell(row_idx, 9, improvement_plan)
            sheet.update_cell(row_idx, 10, daily_lesson)
        else:
            # Append
            sheet.append_row([
                str(date), blocks_json, new_ideas, funny_ep, next_action, 
                total_blocks, timestamp, daily_reflection, improvement_plan, daily_lesson
            ])
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False

# --- Session State Logic ---
if 'temp_blocks' not in st.session_state:
    st.session_state.temp_blocks = []
if 'loaded_date' not in st.session_state:
    st.session_state.loaded_date = None
if 'form_ideas' not in st.session_state: st.session_state.form_ideas = ""
if 'form_funny' not in st.session_state: st.session_state.form_funny = ""
if 'form_next' not in st.session_state: st.session_state.form_next = ""
if 'form_reflection' not in st.session_state: st.session_state.form_reflection = ""
if 'form_improvement' not in st.session_state: st.session_state.form_improvement = ""
if 'form_lesson' not in st.session_state: st.session_state.form_lesson = ""

# Block editing state
if 'edit_target_idx' not in st.session_state: st.session_state.edit_target_idx = None
if 'form_title' not in st.session_state: st.session_state.form_title = ""
if 'form_count' not in st.session_state: st.session_state.form_count = 1
if 'form_cat' not in st.session_state: st.session_state.form_cat = list(CATEGORIES.keys())[0]
if 'form_challenge' not in st.session_state: st.session_state.form_challenge = ""
if 'form_thoughts' not in st.session_state: st.session_state.form_thoughts = ""
if 'form_action' not in st.session_state: st.session_state.form_action = ""
if 'form_lesson_block' not in st.session_state: st.session_state.form_lesson_block = ""
if 'form_tags' not in st.session_state: st.session_state.form_tags = []
if 'form_rating' not in st.session_state: st.session_state.form_rating = 3
if 'quick_mode' not in st.session_state: st.session_state.quick_mode = False

# --- App ---
tab_record, tab_list, tab_class = st.tabs(["📝 記録", "🧱 一覧", "📊 分類"])

# === TAB 1: RECORD ===
with tab_record:
    st.markdown("### Bricks")
    col_date, col_dummy = st.columns([1, 2])
    with col_date:
        rec_date = st.date_input("日付選択", datetime.now())
    
    # Auto-Load Data on Date Change
    if st.session_state.loaded_date != rec_date:
        df = load_all_data()
        date_str = str(rec_date)
        if not df.empty and date_str in df['Date'].values:
            row = df[df['Date'] == date_str].iloc[0]
            try:
                st.session_state.temp_blocks = json.loads(row['BlocksJSON'])
                st.session_state.form_ideas = row.get('NewIdeas', "")
                st.session_state.form_funny = row.get('FunnyEpisodes', "")
                st.session_state.form_next = row.get('NextAction', "")
                st.session_state.form_reflection = row.get('DailyReflection', "")
                st.session_state.form_improvement = row.get('ImprovementPlan', "")
                st.session_state.form_lesson = row.get('DailyLesson', "")
            except:
                st.session_state.temp_blocks = []
                st.session_state.form_ideas = ""
                st.session_state.form_funny = ""
                st.session_state.form_next = ""
                st.session_state.form_reflection = ""
                st.session_state.form_improvement = ""
                st.session_state.form_lesson = ""
        else:
            # Clear if new date
            st.session_state.temp_blocks = []
            st.session_state.form_ideas = ""
            st.session_state.form_funny = ""
            st.session_state.form_next = ""
            st.session_state.form_reflection = ""
            st.session_state.form_improvement = ""
            st.session_state.form_lesson = ""
        st.session_state.loaded_date = rec_date

    # Visual Progress Bar
    current_total = sum(b['count'] for b in st.session_state.temp_blocks)
    target = 24
    
    html_prog = '<div class="visual-progress">'
    # Render actual blocks
    # Add colored blocks based on actual data
    for b in st.session_state.temp_blocks:
        css = get_cat_color(b['category'])
        for _ in range(b['count']):
            html_prog += f'<div class="prog-brick {css}"></div>'
    
    # Fill remaining with empty if less than target
    if current_total < target:
        for _ in range(target - current_total):
            html_prog += '<div class="prog-brick cat-empty"></div>'
            
    html_prog += '</div>'
    
    st.caption(f"Progress: {current_total} / {target} (+{max(0, current_total-24)} Over)")
    st.markdown(html_prog, unsafe_allow_html=True)

    # Input Form
    st.markdown("---")
    
    col_head_1, col_head_2 = st.columns([3, 1])
    with col_head_1:
         st.subheader("🧱 ブロックを追加")
    with col_head_2:
        # Quick Mode Toggle
        is_quick = st.toggle("⚡ Quick Mode", value=st.session_state.quick_mode, key="quick_mode_toggle")
        st.session_state.quick_mode = is_quick

    c1, c2, c3 = st.columns([2, 1, 3])
    with c1:
        cat = st.selectbox("分類", list(CATEGORIES.keys()), key="input_cat", index=list(CATEGORIES.keys()).index(st.session_state.form_cat) if st.session_state.form_cat in CATEGORIES else 0)
    with c2:
        count = st.number_input("ブロック数 (1=30分)", min_value=1, value=st.session_state.form_count, key="input_count")
    with c3:
        title = st.text_input("したこと (タイトル)", value=st.session_state.form_title, key="input_title")
    
    # Detailed inputs for STAR method - Hide in Quick Mode
    if not is_quick:
        with st.expander("詳細入力（課題・思考・行動）", expanded=True):
            # 2-Column Smart Layout
            col_L, col_R = st.columns(2)
            
            with col_L:
                challenge = st.text_area("直面した課題 (Challenge)", height=70, placeholder="どんな難しさに直面した？", value=st.session_state.form_challenge, key="input_challenge")
                thoughts = st.text_area("その時考えたこと (Thoughts)", height=70, placeholder="どう考えた？", value=st.session_state.form_thoughts, key="input_thoughts")
            
            with col_R:
                action = st.text_area(
                    "とった行動 (Action)", height=70, 
                    placeholder="具体的に何をした？\n※具体的な数字(時間・金額・回数・人数)を添えるようにしてください。",
                    help="※具体的な数字(時間・金額・回数・人数)を添えるようにしてください。",
                    value=st.session_state.form_action,
                    key="input_action"
                )
                lesson = st.text_area("この経験から得た教訓・学び (Lesson)", height=70, placeholder="一言でまとめると？", value=st.session_state.form_lesson_block, key="input_lesson_block")
                
            # Tags & Rating on one row below
            c_tag, c_rate = st.columns([3, 1])
            with c_tag:
                tags = st.multiselect("感情タグ", ["楽しい", "悔しい", "感動", "イライラ","虚無"], default=st.session_state.form_tags, key="input_tags")
            with c_rate:
                rating = st.selectbox("満足度", [1, 2, 3, 4, 5], index=st.session_state.form_rating-1, format_func=lambda x: "⭐" * x, key="input_rating")
    else:
        # Defaults for Quick Mode
        challenge = ""
        thoughts = ""
        action = ""
        lesson = ""
        tags = []
        rating = 3
    
    btn_label = "＋ 追加" if st.session_state.edit_target_idx is None else "🔄 更新"
    
    if st.button(btn_label, type="primary"):
        if title:
            new_block = {
                "category": cat, 
                "title": title, 
                "count": count, 
                "challenge": challenge,
                "thoughts": thoughts,
                "action": action,
                "lesson": lesson,
                "tags": tags,
                "rating": rating
            }
            
            if st.session_state.edit_target_idx is not None:
                # Update existing
                idx = st.session_state.edit_target_idx
                if 0 <= idx < len(st.session_state.temp_blocks):
                    st.session_state.temp_blocks[idx] = new_block
                    st.toast(f" Updated: {title}")
                # Reset edit state
                st.session_state.edit_target_idx = None
            else:
                # Add new
                st.session_state.temp_blocks.append(new_block)
                st.toast(f" Added: {title}")
            
            # Reset Form
            st.session_state.form_title = ""
            st.session_state.form_count = 1
            st.session_state.form_challenge = ""
            st.session_state.form_thoughts = ""
            st.session_state.form_action = ""
            st.session_state.form_lesson_block = ""
            st.session_state.form_tags = []
            st.session_state.form_rating = 3
            
            st.rerun()
        else:
            st.error("タイトルを入力してください")

    if st.session_state.temp_blocks:
        st.markdown(f"#### 積まれたブロック ({len(st.session_state.temp_blocks)})")
        
        # Scrollable container for blocks
        with st.container(height=250, border=True):
            for i, b in enumerate(reversed(st.session_state.temp_blocks)):
                # Reverse index for display, but need real index for deletion
                real_idx = len(st.session_state.temp_blocks) - 1 - i
                
                css_class = get_cat_color(b['category'])
                # Adjusted column ratio to give more space for buttons
                col_b1, col_b2 = st.columns([3, 1])
                with col_b1:
                    # Compact view, removed fixed width
                    st.markdown(f"""
                        <div style="background-color:#1e293b; border-radius:8px; padding:12px; margin-bottom:8px; border:1px solid #334155;">
                            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
                                <div style="display:flex; align-items:center; gap:8px;">
                                    <span class="brick {css_class}">{b['category']}</span>
                                    <span style="font-size:1.0em; font-weight:bold; color:#f8fafc;">{b['title']}</span>
                                    <span style="font-size:0.8em; color:#94a3b8;">({b['count']} block{'s' if b['count'] > 1 else ''})</span>
                                </div>
                                <span style="color:#fbbf24; font-size:1.1em; letter-spacing:2px;">{'★' * b.get('rating', 3)}</span>
                            </div>
                            
                            <div style="margin-bottom:8px;">
                                {' '.join([f'<span style="background:#334155; color:#cbd5e1; padding:2px 8px; border-radius:4px; font-size:0.75em; border:1px solid #475569;">{t}</span>' for t in b.get('tags', [])])}
                            </div>
                            
                            <div style="display:grid; grid-template-columns: 1fr; gap:6px; font-size:0.9em; color:#e2e8f0;">
                                <div style="display:flex; align-items:baseline;">
                                    <span style="min-width:60px; color:#94a3b8; font-weight:bold; font-size:0.85em;">プラン</span>
                                    <span style="flex:1;">{html.escape(b.get('challenge') or 'ー')}</span>
                                </div>
                                <div style="display:flex; align-items:baseline;">
                                    <span style="min-width:60px; color:#94a3b8; font-weight:bold; font-size:0.85em;">ドゥ</span>
                                    <span style="flex:1;">{html.escape(b.get('action') or 'ー')}</span>
                                </div>
                                <div style="display:flex; align-items:baseline;">
                                    <span style="min-width:60px; color:#94a3b8; font-weight:bold; font-size:0.85em;">チェック</span>
                                    <span style="flex:1;">{html.escape(b.get('thoughts') or 'ー')}</span>
                                </div>
                                <div style="display:flex; align-items:baseline;">
                                    <span style="min-width:60px; color:#fbbf24; font-weight:bold; font-size:0.85em;">マナビ</span>
                                    <span style="flex:1; color:#fcd34d; font-weight:500;">{html.escape(b.get('lesson') or 'ー')}</span>
                                </div>
                            </div>
                        </div>
                    """.replace('\n', '').replace('    ', ''), unsafe_allow_html=True)
                with col_b2:
                    col_act1, col_act2 = st.columns(2)
                    with col_act1:
                         # Changed to explicit "Edit" text/icon for clarity
                         if st.button("🖊", key=f"edit_{real_idx}", help="編集"):
                            # Load into form
                            b_target = st.session_state.temp_blocks[real_idx]
                            st.session_state.form_cat = b_target.get('category', list(CATEGORIES.keys())[0])
                            st.session_state.form_count = b_target.get('count', 1)
                            st.session_state.form_title = b_target.get('title', '')
                            st.session_state.form_challenge = b_target.get('challenge', '')
                            st.session_state.form_thoughts = b_target.get('thoughts', '')
                            st.session_state.form_action = b_target.get('action', '')
                            st.session_state.form_lesson_block = b_target.get('lesson', '')
                            st.session_state.form_tags = b_target.get('tags', [])
                            st.session_state.form_rating = b_target.get('rating', 3)
                            
                            st.session_state.edit_target_idx = real_idx
                            st.session_state.quick_mode = False 
                            st.rerun()
                            
                    with col_act2:
                        # Changed to trash icon for clarity
                        if st.button("🗑", key=f"del_{real_idx}", help="削除"):
                            st.session_state.temp_blocks.pop(real_idx)
                            if st.session_state.edit_target_idx == real_idx:
                                st.session_state.edit_target_idx = None
                            st.rerun()

    st.markdown("---")
    st.subheader("1日のまとめ")
    
    # Primary Reflection Fields
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        daily_reflection = st.text_area("今日の反省", value=st.session_state.form_reflection, key="input_reflection", height=150)
    with col_d2:
        improvement_plan = st.text_area("明日以降の改善案", value=st.session_state.form_improvement, key="input_improvement", height=150)

    # daily_lesson moved to block level

    with st.expander("その他メモ (アイデア・面白エピソード)"):
        new_ideas = st.text_area("💡 新しいアイデア", value=st.session_state.form_ideas, key="input_ideas")
        funny_ep = st.text_area("🤣 面白エピソード", value=st.session_state.form_funny, key="input_funny")
        next_action = st.text_area("🚀 (旧) 明日以降活かしたいこと", value=st.session_state.form_next, key="input_next")
    
    if st.button("✅ 完了 (保存)", type="primary", use_container_width=True):
        if st.session_state.temp_blocks:
            # Pass empty string for daily_lesson to maintain schema compatibility
            if save_daily_record(rec_date, st.session_state.temp_blocks, new_ideas, funny_ep, next_action, daily_reflection, improvement_plan, ""):
                st.success("Saved!")
                st.balloons()
            else:
                st.error("Save Failed")
        else:
            st.warning("No blocks to save")

# === TAB 2: LIST ===
with tab_list:
    st.markdown("### 積み上げ記録")
    
    # Legend
    legend_html = '<div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px;">'
    for cat_name, css_class in CATEGORIES.items():
        legend_html += f'<span class="brick {css_class}" style="padding: 0 10px; height: 24px;">{cat_name}</span>'
    legend_html += '</div>'
    st.markdown(legend_html, unsafe_allow_html=True)

    if st.button("Reload"): st.cache_data.clear()
    
    df = load_all_data()
    if not df.empty:
        df = df.sort_values(by="Date", ascending=False)
        for _, row in df.iterrows():
            try: blocks = json.loads(row['BlocksJSON'])
            except: blocks = []
            
            st.markdown(f"**{row['Date']}**")
            
            # Visuals
            html_blocks = '<div class="block-container-list">'
            titles_html = '<ul style="margin-top:5px; padding-left:20px; color:#ddd; font-size:0.9em;">'
            
            for b in blocks:
                css = get_cat_color(b['category'])
                # Tooltip: Title + Reflection
                # Sanitize: Escape HTML chars AND remove newlines for valid title attribute
                title_esc = html.escape(b['title']).replace('\n', ' ')
                refl_esc = html.escape(b.get('reflection', '')).replace('\n', ' ')
                tooltip = f"{title_esc} ({b['count']}): {refl_esc}"
                
                # Render Bricks
                for _ in range(b['count']):
                     html_blocks += f'<div class="brick {css}" title="{tooltip}" style="width:30px; height:30px;"></div>'
                
                # Add to text list
                titles_html += f'<li>{b["title"]}</li>'
            
            html_blocks += '</div>'
            titles_html += '</ul>'
            
            st.markdown(html_blocks, unsafe_allow_html=True)
            
            # Dropdown for Details (Reflections)
            with st.expander("詳細・感想を見る"):
                for b in blocks:
                    css_color = get_cat_color(b['category'])
                    # FIX: Re-calculate escaped strings for the CURRENT block 'b'
                    # Reuse the same sanitization logic as above
                    t_esc = html.escape(b['title']).replace('\n', ' ')
                    r_esc = html.escape(b.get('reflection', '')).replace('\n', ' ')
                    
                    st.markdown(f"""
                        <div style="margin-bottom:8px;">
                            <span class="brick {css_color}" style="display:inline-block; width:12px; height:12px; margin-right:5px;"></span>
                            <strong>{t_esc}</strong> <small>({b['count']} blocks)</small><br>
                            <span style="color:#ccc; margin-left:20px;">{r_esc or 'No reflection'}</span>
                        </div>
                    """.replace('\n', '').replace('    ', ''), unsafe_allow_html=True)

                # Additional Info (merged into this expander or separate, user asked for reflections specifically)
                if row.get('NewIdeas'): st.info(f"💡 Ideas: {row['NewIdeas']}")
                if row.get('FunnyEpisodes'): st.success(f"🤣 Funny: {row['FunnyEpisodes']}")
                if row.get('DailyReflection'): st.warning(f"🤔 反省: {row['DailyReflection']}")
                if row.get('ImprovementPlan'): st.error(f"📈 改善: {row['ImprovementPlan']}")
                if row.get('DailyLesson'): st.success(f"🎓 教訓: {row['DailyLesson']}")
                if row.get('NextAction'): st.warning(f"🚀 Next: {row['NextAction']}")
            
            st.markdown("---")
    else:
        st.info("No Data")

# === TAB 3: STATS ===
with tab_class:
    st.markdown("### 分類・分析")
    df_c = load_all_data()
    
    if not df_c.empty:
        # Pre-process block data
        all_blocks = []
        for _, row in df_c.iterrows():
            try:
                bs = json.loads(row['BlocksJSON'])
                # Convert row Date to datetime for filtering
                d = datetime.strptime(row['Date'], "%Y-%m-%d").date()
                for b in bs:
                    b['DateObj'] = d
                    b['Date'] = row['Date']
                    all_blocks.append(b)
            except: pass
        
        if all_blocks:
            df_b = pd.DataFrame(all_blocks)
            
            # --- Weekly Analysis ---
            st.subheader("週間レポート (直近7日間)")
            today = datetime.now().date()
            seven_days_ago = today - timedelta(days=7)
            
            # Filter current week
            df_week = df_b[(df_b['DateObj'] <= today) & (df_b['DateObj'] > seven_days_ago)]
            
            if not df_week.empty:
                col_w1, col_w2 = st.columns([2, 1])
                with col_w1:
                    # Bar Chart for the week
                    stats_w = df_week.groupby("category")['count'].sum().reset_index()
                    chart_w = alt.Chart(stats_w).mark_bar().encode(
                        x='category',
                        y=alt.Y('count', scale=alt.Scale(nice=True)),
                        color=alt.Color('category', scale=alt.Scale(
                            domain=list(CATEGORIES.keys()),
                            range=['#60a5fa', '#a78bfa', '#fb923c', '#34d399', '#facc15', '#9ca3af']
                        )),
                        tooltip=['category', 'count']
                    ).properties(height=300)
                    st.altair_chart(chart_w, use_container_width=True)
                
                with col_w2:
                    st.write("**カテゴリ別合計**")
                    st.dataframe(stats_w.set_index("category"), use_container_width=True)
            else:
                st.info("直近7日間のデータがありません。")

            st.markdown("---")
            
            st.subheader("全期間・詳細フィルタ")
            
            # Filters
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                cat_filter = st.selectbox("カテゴリ", ["All"] + list(CATEGORIES.keys()))
            with col_f2:
                # Filter by Tag (multiselect, logical OR or AND? User asked for "Happy only" etc. Usually OR within tags, AND across fields)
                # Let's simple check: if any selected tag is present.
                tag_filter = st.multiselect("タグ絞り込み", ["楽しい", "悔しい", "感動", "イライラ"])
            with col_f3:
                # Minimum Rating Filter
                rate_filter = st.slider("★ 以上の評価", 1, 5, 1)

            # Apply Filters
            filtered_df = df_b.copy()
            
            # 1. Category
            if cat_filter != "All":
                filtered_df = filtered_df[filtered_df['category'] == cat_filter]
                
            # 2. Rating (Assuming 'rating' key exists, default to 0 if not key present but we want to show all legacies? 
            # Legacy blocks don't have rating. Let's treat missing rating as 3 (neutral) or 0? 
            # If user filters for 5 stars, legacy shouldn't show. If 1 star, legacy (undef) might show?
            # Safer to treat None as 3 (average) or hide? Let's treat as 0 for strict filtering.)
            # Actually, let's fillna with 3 for display but 0 for filtering if strict. 
            # Let's iterate rows to filter since tags are list.
            
            final_rows = []
            for _, r in filtered_df.iterrows():
                # Rating Check
                r_val = r.get('rating') # None if missing (Legacy)
                
                if rate_filter == 1:
                    # Filter is 1 (default): Show all (Legacy + Rated>=1)
                    pass
                else:
                    # Filter > 1: Strict Check. MUST be rated and >= filter
                    if r_val is None or r_val < rate_filter:
                        continue
                
                # Tag Check (If tags selected)
                if tag_filter:
                    r_tags = r.get('tags', [])
                    # Check intersection. If any selected tag matches any row tag -> Keep.
                    # Or User wants "Only Fun", implies Exact Match? 
                    # Usually "Contains Fun" is best.
                    if not set(tag_filter).intersection(set(r_tags)):
                        continue
                
                final_rows.append(r)
            
            target_df = pd.DataFrame(final_rows)

            if cat_filter == "All" and not tag_filter and rate_filter == 1:
                # Show aggregate if no complex filter
                stats = df_b.groupby("category")['count'].sum().reset_index()
                chart = alt.Chart(stats).mark_bar().encode(
                    x='category',
                    y=alt.Y('count', scale=alt.Scale(nice=True)),
                    color=alt.Color('category', scale=alt.Scale(
                        domain=list(CATEGORIES.keys()),
                        range=['#60a5fa', '#a78bfa', '#fb923c', '#34d399', '#facc15', '#9ca3af']
                    ))
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                if target_df.empty:
                    st.info("条件に一致するブロックはありません。")
                else:
                    total_val = target_df['count'].sum() if 'count' in target_df.columns else 0
                    
                    # Independent, stylish card for Total
                    st.metric(label=f"Total Blocks (Filtered)", value=total_val)
                    
                    # Detailed Card View
                    for _, row in target_df.iterrows():
                        with st.container(border=True):
                            # Header: Date, Title, Rating
                            rating_stars = "⭐" * row.get('rating', 0)
                            st.markdown(f"**{row['Date']}** | {rating_stars} **{row['title']}** ({row['count']} blocks)")
                            
                            # Tags
                            tags = row.get('tags', [])
                            if tags:
                                tag_html = ' '.join([f'<span style="background:#334; color:#fff; padding:2px 6px; border-radius:4px; font-size:0.8em; margin-right:4px;">{t}</span>' for t in tags])
                                st.markdown(f'<div style="margin-bottom:8px;">{tag_html}</div>', unsafe_allow_html=True)
                            
                            # Details Grid
                            c = row.get('challenge')
                            t = row.get('thoughts')
                            a = row.get('action')
                            r = row.get('reflection')
                            
                            # Legacy Fallback
                            if not (c or t or a) and r:
                                st.info(f"📝 **Reflection (Legacy):** {r}")
                            else:
                                c_ch, c_th, c_ac = st.columns(3)
                                with c_ch:
                                    st.caption("Challenge")
                                    st.write(c or "(記述なし)")
                                with c_th:
                                    st.caption("Thoughts")
                                    st.write(t or "(記述なし)")
                                with c_ac:
                                    st.caption("Action")
                                    st.write(a or "(記述なし)")
                            
                            if row.get('lesson'):
                                st.info(f"🎓 **Lesson:** {row['lesson']}")

            st.markdown("---")
            st.subheader("1日のまとめ (全期間リスト)")
            
            summary_tab1, summary_tab2, summary_tab3 = st.tabs(["💡 アイデア", "🤣 面白エピソード", "🚀 明日以降"])
            
            with summary_tab1:
                df_ideas = df_c[df_c['NewIdeas'].notna() & (df_c['NewIdeas'] != "")].sort_values(by="Date", ascending=False)
                if not df_ideas.empty:
                    st.dataframe(
                        df_ideas[['Date', 'NewIdeas']],
                        use_container_width=True,
                        column_config={
                            "Date": st.column_config.TextColumn("日付", width="small"),
                            "NewIdeas": st.column_config.TextColumn("新しいアイデア", width="large")
                        },
                        hide_index=True
                    )
                else:
                    st.info("データがありません")

            with summary_tab2:
                df_funny = df_c[df_c['FunnyEpisodes'].notna() & (df_c['FunnyEpisodes'] != "")].sort_values(by="Date", ascending=False)
                if not df_funny.empty:
                    st.dataframe(
                        df_funny[['Date', 'FunnyEpisodes']],
                        use_container_width=True,
                        column_config={
                            "Date": st.column_config.TextColumn("日付", width="small"),
                            "FunnyEpisodes": st.column_config.TextColumn("面白エピソード", width="large")
                        },
                        hide_index=True
                    )
                else:
                    st.info("データがありません")

            with summary_tab3:
                df_next = df_c[df_c['NextAction'].notna() & (df_c['NextAction'] != "")].sort_values(by="Date", ascending=False)
                if not df_next.empty:
                    st.dataframe(
                        df_next[['Date', 'NextAction']],
                        use_container_width=True,
                        column_config={
                            "Date": st.column_config.TextColumn("日付", width="small"),
                            "NextAction": st.column_config.TextColumn("明日以降活かしたいこと", width="large")
                        },
                        hide_index=True
                    )
                else:
                    st.info("データがありません")

            st.markdown("---")
            st.subheader("🎓 就活・成長記録 (STAR分析)")
            st.caption("直面した課題(Challenge)、思考(Thoughts)、行動(Action)を振り返ります。")
            
            search_query = st.text_input("🔍 キーワード検索 (課題・思考・行動)", placeholder="例: チームワーク, 解決, 失敗")
            
            # Filter blocks with C/T/A data
            star_blocks = []
            for _, row in df_c.iterrows():
                try: blocks = json.loads(row['BlocksJSON'])
                except: continue
                d = row['Date']
                for b in blocks:
                    # Check if block has meaningful STAR content
                    c = b.get('challenge', '')
                    t = b.get('thoughts', '')
                    a = b.get('action', '')
                    if c or t or a:
                        # Search filter
                        full_text = f"{b['title']} {c} {t} {a}"
                        if search_query and search_query.lower() not in full_text.lower():
                            continue
                            
                        b['Date'] = d
                        star_blocks.append(b)
            
            if star_blocks:
                st.write(f"Found {len(star_blocks)} records")
                for sb in star_blocks:
                    with st.container(border=True):
                        st.markdown(f"**{sb['Date']}** - {sb['title']}")
                        col_s1, col_s2, col_s3 = st.columns(3)
                        with col_s1:
                            st.info(f"**Challenge**\n\n{sb.get('challenge','(なし)')}")
                        with col_s2:
                            st.warning(f"**Thoughts**\n\n{sb.get('thoughts','(なし)')}")
                        with col_s3:
                            st.success(f"**Action**\n\n{sb.get('action','(なし)')}")
                        
                        if sb.get('lesson'):
                            st.markdown(f"🎓 **Lesson:** {sb['lesson']}")
            else:
                st.info("条件に一致するSTAR記録が見つかりません。")

# --- Sidebar ---
with st.sidebar:
    st.markdown("---")
    if st.button("⚠️ DB Reset (New Schema)"):
        s = get_sheet()
        if s:
            s.clear()
            s.append_row([
                "Date", "BlocksJSON", "NewIdeas", "FunnyEpisodes", "NextAction", 
                "TotalBlocks", "Timestamp", "DailyReflection", "ImprovementPlan", "DailyLesson"
            ])
            st.cache_data.clear()
            st.success("Reset Done!")
            st.rerun()
