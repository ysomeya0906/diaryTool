import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- Configuration ---
PAGE_TITLE = "Daily Journal"
PAGE_ICON = "📔"
DATA_FILE = "diary.csv"
CSS_FILE = "style.css"

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="centered")

# --- Helper Functions ---
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

def load_data():
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame(columns=["Date", "Item 1", "Item 2", "Item 3", "Item 4", "Timestamp"])
    try:
        df = pd.read_csv(DATA_FILE)
        # Ensure 'Date' is datetime for sorting if needed, but string is okay for display
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame(columns=["Date", "Item 1", "Item 2", "Item 3", "Item 4", "Timestamp"])

def save_data(date, item1, item2, item3, item4):
    df = load_data()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_entry = pd.DataFrame([{
        "Date": str(date),
        "Item 1": item1,
        "Item 2": item2,
        "Item 3": item3,
        "Item 4": item4,
        "Timestamp": timestamp
    }])
    
    # Optional: Check if entry for date exists and overwrite? 
    # For now, just append. User can delete later if needed.
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)
    return True

# --- Main App ---
def main():
    try:
        load_css(CSS_FILE)
    except FileNotFoundError:
        st.warning("style.css not found. Running with default styles.")

    st.title("✨ Daily Journal")

    # --- Sidebar ---
    st.sidebar.header("Navigation")
    page = st.sidebar.radio("Go to", ["✍️ Input (入力)", "📖 Output (閲覧)"])

    st.sidebar.markdown("---")
    st.sidebar.markdown("© 2025 Diary App")

    # --- Input Page ---
    if page == "✍️ Input (入力)":
        st.header("Create New Entry")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            date_input = st.date_input("Date", datetime.now())
        
        with st.form("diary_form"):
            item1 = st.text_area("1. 出来事 (Events)", height=100, placeholder="What happened today?")
            item2 = st.text_area("2. 気づき (Insights)", height=100, placeholder="What did you learn?")
            item3 = st.text_area("3. 感謝 (Gratitude)", height=100, placeholder="What are you thankful for?")
            item4 = st.text_area("4. 明日の目標 (Tomorrow's Goal)", height=100, placeholder="What is your focus for tomorrow?")
            
            submitted = st.form_submit_button("Save Entry")
            
            if submitted:
                if item1 or item2 or item3 or item4:
                    if save_data(date_input, item1, item2, item3, item4):
                        st.success("Entry saved successfully!")
                        st.balloons()
                else:
                    st.warning("Please fill in at least one item.")

    # --- Output Page ---
    elif page == "📖 Output (閲覧)":
        st.header("Journal History")
        
        df = load_data()
        
        if not df.empty:
            # Sort by Date descending
            if 'Date' in df.columns:
                df = df.sort_values(by='Date', ascending=False)
            
            st.dataframe(
                df, 
                use_container_width=True,
                column_config={
                    "Date": st.column_config.TextColumn("Date", width="medium"),
                    "Item 1": st.column_config.TextColumn("Events", width="large"),
                    "Item 2": st.column_config.TextColumn("Insights", width="large"),
                    "Item 3": st.column_config.TextColumn("Gratitude", width="large"),
                    "Item 4": st.column_config.TextColumn("Goals", width="large"),
                    "Timestamp": st.column_config.TextColumn("Recorded At", width="small"),
                }
            )
            
            st.markdown("### Export")
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"diary_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
            )
        else:
            st.info("No entries found. Go to the Input page to start writing!")

if __name__ == "__main__":
    main()
