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
        EXPECTED_HEADERS = ["Date", "BlocksJSON", "NewIdeas", "FunnyEpisodes", "NextAction", "TotalBlocks", "Timestamp"]
        
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

def save_daily_record(date, blocks, new_ideas, funny_ep, next_action):
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
        else:
            # Append
            sheet.append_row([str(date), blocks_json, new_ideas, funny_ep, next_action, total_blocks, timestamp])
        
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

# --- App ---
tab_record, tab_list, tab_class = st.tabs(["📝 記録", "🧱 一覧", "📊 分類"])

# === TAB 1: RECORD ===
with tab_record:
    st.markdown("### 今日のブロックを積み上げる")
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
            except:
                st.session_state.temp_blocks = []
                st.session_state.form_ideas = ""
                st.session_state.form_funny = ""
                st.session_state.form_next = ""
        else:
            # Clear if new date
            st.session_state.temp_blocks = []
            st.session_state.form_ideas = ""
            st.session_state.form_funny = ""
            st.session_state.form_next = ""
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
    st.subheader("🧱 ブロックを追加")
    
    c1, c2 = st.columns([1, 1])
    with c1:
        cat = st.selectbox("分類", list(CATEGORIES.keys()))
        count = st.number_input("ブロック数 (1=30分)", min_value=1, value=1)
    with c2:
        title = st.text_input("したこと (タイトル)")
        reflection = st.text_area("感想・気づき", height=100)
        
    if st.button("＋ 追加", type="primary"):
        if title:
            st.session_state.temp_blocks.append({
                "category": cat, "title": title, "count": count, "reflection": reflection
            })
            st.toast(f" Added: {title}")
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
                col_b1, col_b2 = st.columns([4, 1])
                with col_b1:
                    # Compact view, removed fixed width
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:2px;">
                        <span class="brick {css_class}">{b['category']}</span>
                        <span style="font-size:0.9em;"><b>{b['title']}</b> <small>({b['count']})</small></span>
                    </div>
                    """, unsafe_allow_html=True)
                with col_b2:
                    if st.button("x", key=f"del_{real_idx}"):
                        st.session_state.temp_blocks.pop(real_idx)
                        st.rerun()

    st.markdown("---")
    st.subheader("1日のまとめ")
    # Use key to bind to session state for auto-load consistency
    new_ideas = st.text_area("💡 新しいアイデア", value=st.session_state.form_ideas, key="input_ideas")
    funny_ep = st.text_area("🤣 面白エピソード", value=st.session_state.form_funny, key="input_funny")
    next_action = st.text_area("🚀 明日以降活かしたいこと", value=st.session_state.form_next, key="input_next")
    
    if st.button("✅ 完了 (保存)", type="primary", use_container_width=True):
        if st.session_state.temp_blocks:
            if save_daily_record(rec_date, st.session_state.temp_blocks, new_ideas, funny_ep, next_action):
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
                    """, unsafe_allow_html=True)

                # Additional Info (merged into this expander or separate, user asked for reflections specifically)
                if row.get('NewIdeas'): st.info(f"💡 Ideas: {row['NewIdeas']}")
                if row.get('FunnyEpisodes'): st.success(f"🤣 Funny: {row['FunnyEpisodes']}")
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
            
            cat_filter = st.selectbox("カテゴリ絞り込み", ["All"] + list(CATEGORIES.keys()))
            
            if cat_filter == "All":
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
                target_df = df_b[df_b['category'] == cat_filter]
                total_val = target_df['count'].sum()
                
                # Independent, stylish card for Total
                st.metric(label=f"Total {cat_filter} Blocks", value=total_val)
                
                # Full width text for reflection
                st.dataframe(
                    target_df[['Date', 'title', 'count', 'reflection']], 
                    use_container_width=True,
                    column_config={
                        "reflection": st.column_config.TextColumn("Reflection", width="large")
                    }
                )

# --- Sidebar ---
with st.sidebar:
    st.markdown("---")
    if st.button("⚠️ DB Reset (New Schema)"):
        s = get_sheet()
        if s:
            s.clear()
            s.append_row(["Date", "BlocksJSON", "NewIdeas", "FunnyEpisodes", "NextAction", "TotalBlocks", "Timestamp"])
            st.cache_data.clear()
            st.success("Reset Done!")
            st.rerun()
