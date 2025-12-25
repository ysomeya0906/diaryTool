import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import altair as alt

# --- Config & Setup ---
load_dotenv()
st.set_page_config(page_title="Bricks - Daily Life Blocks", page_icon="🧱", layout="wide")

# --- Custom CSS ---
st.markdown("""
<style>
    /* Global */
    .stApp { background-color: #0d1117; color: #ffffff; }
    p, h1, h2, h3, h4, h5, h6, li, span { color: #ffffff !important; }
    
    /* Popovers (Dropdowns, Tooltips) - Force Black Text */
    div[data-baseweb="popover"], div[data-baseweb="popover"] div, div[data-baseweb="popover"] span, div[data-baseweb="popover"] li, div[data-baseweb="popover"] p {
        color: #000000 !important;
    }
    
    /* Inputs */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div>div, .stNumberInput>div>div>input {
        background-color: #161b22 !important; 
        color: #ffffff !important; 
        border: 1px solid #30363d;
    }
    .stSelectbox svg { fill: white !important; }
    
    /* Block Visuals */
    .block-container {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-bottom: 10px;
    }
    .brick {
        height: 40px;
        border-radius: 4px;
        color: #000000 !important; /* Black Text as requested */
        font-size: 0.85em;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        cursor: help;
        border: 1px solid rgba(0,0,0,0.1);
        text-shadow: none; /* Remove shadow for clean black text */
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .brick:hover { opacity: 0.9; transform: translateY(-1px); }
    
    /* Expander Header - Make Black Text (requires light background) */
    .streamlit-expanderHeader {
        background-color: #f0f6fc !important;
        color: #000000 !important;
        border-radius: 8px;
    }
    .streamlit-expanderHeader p { color: #000000 !important; }
    
    /* Colors - Brightened for black text contrast */
    .cat-science { background-color: #60a5fa; } /* Lighter Blue */
    .cat-art { background-color: #a78bfa; } /* Lighter Purple */
    .cat-play { background-color: #fb923c; } /* Lighter Orange */
    .cat-create { background-color: #34d399; } /* Lighter Green */
    .cat-other { background-color: #9ca3af; } /* Lighter Gray */
    
    /* Buttons - Consistent Dark Theme */
    div.stButton > button {
        background-color: #21262d !important;
        color: #ffffff !important;
        border: 1px solid #30363d !important;
        transition: background-color 0.2s;
    }
    div.stButton > button:hover {
        background-color: #30363d !important; /* Slightly lighter on hover */
        border-color: #8b949e !important;
        color: #ffffff !important;
    }
    
    /* Progress Bar */
    .progress-wrapper {
        background-color: #21262d;
        border-radius: 10px;
        height: 24px;
        width: 100%;
        overflow: hidden;
        margin: 10px 0;
        border: 1px solid #30363d;
    }
</style>
""", unsafe_allow_html=True)

# --- Category Config ---
CATEGORIES = {
    "理工学": "cat-science",
    "作品鑑賞・体験": "cat-art",
    "遊び": "cat-play",
    "コンテンツ作成": "cat-create",
    "その他": "cat-other"
}

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
        st.error("❌ GSpread Credentials not found. Check Secrets/Env.")
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
        
        # New Schema Headers
        headers = ["Date", "BlocksJSON", "NewIdeas", "FunnyEpisodes", "TotalBlocks", "Timestamp"]
        if not sheet.get_all_values():
            sheet.append_row(headers)
        elif sheet.row_values(1) != headers:
            # If headers mismatch, we assume migration needed or specific user action reset
            pass
            
        return sheet
    except Exception as e:
        st.error(f"Sheet Error: {e}")
        return None

@st.cache_data(ttl=60)
def load_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame()
    try:
        rows = sheet.get_all_values()
        if not rows: return pd.DataFrame()
        return pd.DataFrame(rows[1:], columns=rows[0])
    except Exception as e:
        st.error(f"Read Error: {e}")
        return pd.DataFrame()

def save_daily_record(date, blocks, new_ideas, funny_episodes):
    sheet = get_sheet()
    if not sheet: return False
    try:
        # Serialize blocks to JSON
        blocks_json = json.dumps(blocks, ensure_ascii=False)
        total_blocks = sum(b['count'] for b in blocks)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Check if date exists (Update logic)
        try:
            cell = sheet.find(str(date), in_column=1)
            if cell:
                # Update existing row
                sheet.update_cell(cell.row, 2, blocks_json)
                sheet.update_cell(cell.row, 3, new_ideas)
                sheet.update_cell(cell.row, 4, funny_episodes)
                sheet.update_cell(cell.row, 5, total_blocks)
                sheet.update_cell(cell.row, 6, timestamp)
            else:
                # Append new
                sheet.append_row([str(date), blocks_json, new_ideas, funny_episodes, total_blocks, timestamp])
        except gspread.CellNotFound:
             sheet.append_row([str(date), blocks_json, new_ideas, funny_episodes, total_blocks, timestamp])
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False

# --- Session State ---
if 'temp_blocks' not in st.session_state:
    st.session_state.temp_blocks = []

# --- Apps ---
tab_record, tab_list, tab_class = st.tabs(["📝 記録 (Record)", "🧱 一覧 (List)", "📊 分類 (Stats)"])

# === TAB 1: RECORD ===
with tab_record:
    st.header("今日のブロックを積み上げる")
    
    col_date, col_prog = st.columns([1, 2])
    with col_date:
        rec_date = st.date_input("日付選択", datetime.now())
    
    # Progress Calculation
    current_total = sum(b['count'] for b in st.session_state.temp_blocks)
    target = 24
    progress_pct = min(current_total / target, 1.0) * 100
    
    with col_prog:
        st.write(f"**Progress:** {current_total} / {target} Blocks")
        st.markdown(f"""
        <div class="progress-wrapper">
            <div class="progress-fill" style="width: {progress_pct}%;"></div>
        </div>
        """, unsafe_allow_html=True)
        if current_total < target:
            st.caption(f"あと {target - current_total} ブロック！ (約 {(target - current_total)*30/60:.1f} 時間)")
        else:
            st.success("🎉 目標達成！素晴らしいです！")

    st.markdown("---")
    
    # Block Input Form
    with st.expander("🧱 ブロックを追加", expanded=True):
        c1, c2 = st.columns([1, 1])
        with c1:
            cat = st.selectbox("分類", list(CATEGORIES.keys()))
            count = st.number_input("ブロック数 (1ブロック=30分)", min_value=1, value=1)
        with c2:
            title = st.text_input("したこと (タイトル)")
            reflection = st.text_area("感想・気づき", height=100)
            
        if st.button("＋ 追加", type="primary"):
            if title:
                st.session_state.temp_blocks.append({
                    "category": cat,
                    "title": title,
                    "count": count,
                    "reflection": reflection
                })
                st.toast(f"「{title}」を追加しました")
                st.rerun()
            else:
                st.error("タイトルを入力してください")

    # Current List Display
    if st.session_state.temp_blocks:
        st.subheader("積まれたブロック")
        for i, b in enumerate(st.session_state.temp_blocks):
            css_class = CATEGORIES.get(b['category'], 'cat-other')
            col_b1, col_b2 = st.columns([4, 1])
            with col_b1:
                st.markdown(f"""
                <div style="border-left: 5px solid #ccc; padding-left: 10px; margin-bottom: 5px;">
                    <span class="brick {css_class}" style="display:inline-block; width:100px; height:20px; font-size:0.7em;">{b['category']}</span>
                    <strong>{b['title']}</strong> ({b['count']} blocks) <br>
                    <small style="color:#aaa;">{b['reflection']}</small>
                </div>
                """, unsafe_allow_html=True)
            with col_b2:
                if st.button("削除", key=f"del_{i}"):
                    st.session_state.temp_blocks.pop(i)
                    st.rerun()

    st.markdown("---")
    
    # Final Reflections
    st.subheader("1日のまとめ")
    new_ideas = st.text_area("💡 新しいアイデア", placeholder="今日思いついたことは？")
    funny_ep = st.text_area("🤣 面白エピソード", placeholder="話のネタになりそうなことは？")
    
    if st.button("✅ 完了 (保存する)", type="primary", use_container_width=True):
        if st.session_state.temp_blocks:
            if save_daily_record(rec_date, st.session_state.temp_blocks, new_ideas, funny_ep):
                st.success("保存しました！")
                st.session_state.temp_blocks = [] # Clear only on success
                st.balloons()
            else:
                st.error("保存に失敗しました")
        else:
            st.warning("ブロックがありません")

# === TAB 2: LIST ===
with tab_list:
    st.header("積み上げの記録")
    if st.button("Reload Data"): st.cache_data.clear()
    
    df = load_data()
    if not df.empty:
        df = df.sort_values(by="Date", ascending=False)
        
        for index, row in df.iterrows():
            date_str = row['Date']
            try:
                blocks = json.loads(row['BlocksJSON'])
            except:
                blocks = []
            
            # Render Row
            st.markdown(f"### {date_str}")
            
            # Visual Stack
            html_blocks = '<div class="block-container">'
            for b in blocks:
                css = CATEGORIES.get(b['category'], 'cat-other')
                # Render width proportional to count? Or repeat blocks?
                # User asked for "stacked blocks". Let's show separate bricks for each count or one wide brick?
                # "積み上げて" -> Let's show 1 unit per count for visually stacking feeling
                for _ in range(int(b['count'])):
                    html_blocks += f'<div class="brick {css}" title="{b["title"]}: {b["reflection"]}" style="width:30px;"></div>'
            html_blocks += '</div>'
            st.markdown(html_blocks, unsafe_allow_html=True)
            
            # Details Expander
            with st.expander(f"詳細: {len(blocks)} Activities"):
                for b in blocks:
                    st.write(f"**[{b['category']}] {b['title']}** ({b['count']})")
                    st.caption(b['reflection'])
                if row.get('NewIdeas'):
                    st.info(f"💡 **Idea:** {row['NewIdeas']}")
                if row.get('FunnyEpisodes'):
                    st.success(f"🤣 **Episode:** {row['FunnyEpisodes']}")
            st.markdown("---")
    else:
        st.info("データがありません")

# === TAB 3: CLASSIFICATION ===
with tab_class:
    st.header("分類・分析")
    
    df_c = load_data()
    if not df_c.empty:
        # Process Data for Stats
        all_blocks = []
        for idx, row in df_c.iterrows():
            try:
                bs = json.loads(row['BlocksJSON'])
                for b in bs:
                    b['Date'] = row['Date']
                    all_blocks.append(b)
            except: pass
            
        if all_blocks:
            df_blocks = pd.DataFrame(all_blocks)
            
            # Filter
            selected_cat = st.selectbox("カテゴリを絞り込む", ["All"] + list(CATEGORIES.keys()) + ["新しいアイデア", "面白エピソード"])
            
            if selected_cat in list(CATEGORIES.keys()):
                filtered = df_blocks[df_blocks['category'] == selected_cat]
                st.metric(f"Total Blocks ({selected_cat})", filtered['count'].sum())
                st.dataframe(filtered[['Date', 'title', 'count', 'reflection']])
            
            elif selected_cat == "All":
                # Aggregate by Category
                stats = df_blocks.groupby("category")['count'].sum().reset_index()
                chart = alt.Chart(stats).mark_bar().encode(
                    x='category',
                    y='count',
                    color=alt.Color('category', scale=alt.Scale(
                        domain=list(CATEGORIES.keys()),
                        range=['#3b82f6', '#8b5cf6', '#f97316', '#10b981', '#6b7280']
                    ))
                )
                st.altair_chart(chart, use_container_width=True)
                st.dataframe(df_blocks)
            
            elif selected_cat in ["新しいアイデア", "面白エピソード"]:
                col_name = "NewIdeas" if selected_cat == "新しいアイデア" else "FunnyEpisodes"
                # Filter rows where col is not empty
                res = df_c[df_c[col_name] != ""][['Date', col_name]]
                st.table(res)

    else:
        st.warning("データ不足です")

# --- Sidebar Reset (Maintained) ---
with st.sidebar:
    st.markdown("---")
    if st.button("⚠️ DB Reset (Bricks Schema)"):
        s = get_sheet()
        if s:
            s.clear()
            s.append_row(["Date", "BlocksJSON", "NewIdeas", "FunnyEpisodes", "TotalBlocks", "Timestamp"])
            st.cache_data.clear()
            st.success("Reset Complete for Bricks!")
            st.rerun()
