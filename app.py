import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from github import Github
import io
import time

# --- CONFIGURATION (SECURE) ---
APP_PASSWORD = "vddf2jjwm3"

try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = "mowais05/Remark_update" 
except:
    st.error("❌ Secrets not found! Please add GITHUB_TOKEN in Streamlit Settings.")
    st.stop()

FILE_PATH = "database.xlsx"
DELIVERED_FILE_PATH = "delivered_database.xlsx"  # Delivered Database File Path

# Page Config - Removed force layout="wide" to avoid horizontal stretching on tiny mobile screens
st.set_page_config(page_title="DYNAMO SMART PORTAL", initial_sidebar_state="expanded")

# --- COOLDOWN LOGIC ---
if "last_save_time" not in st.session_state:
    st.session_state.last_save_time = datetime.now() - timedelta(seconds=20)
if "lock_until" not in st.session_state:
    st.session_state.lock_until = None

def get_wait_time():
    if st.session_state.lock_until and datetime.now() < st.session_state.lock_until:
        return int((st.session_state.lock_until - datetime.now()).total_seconds())
    elapsed = (datetime.now() - st.session_state.last_save_time).total_seconds()
    limit = 2  # SMART UPDATE: 10s se kam karke 2s kiya (Sirf accidental double-click rokne ke liye)
    return int(limit - elapsed) if elapsed < limit else 0

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .stButton>button:disabled { background-color: #e9ecef !important; color: #adb5bd !important; border: 1px solid #dee2e6 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- GITHUB CORE ---
@st.cache_resource
def get_github_repo():
    try:
        g = Github(GITHUB_TOKEN)
        return g.get_repo(REPO_NAME)
    except: return None

@st.cache_data(ttl=600)
def load_data_from_github():
    try:
        repo = get_github_repo()
        file_content = repo.get_contents(FILE_PATH, ref="main")
        df = pd.read_excel(io.BytesIO(file_content.decoded_content))
        df.columns = df.columns.str.strip()
        if 'RO_No' in df.columns:
            df['RO_No'] = df['RO_No'].astype(str).str.strip().str.upper()
        return df
    except:
        cols = ["RO_No", "In_Date", "Int_Date", "Sur_Date", "App_Date", "Dis_Date", 
                "Den_Date", "Pnt_Date", "Fit_Date", "RBND_Date", "Smart_Status", "Final_Remark"]
        return pd.DataFrame(columns=cols)

# --- MOVE TO ARCHIVE ON GITHUB ---
def move_to_delivered_github(row_data):
    try:
        repo = get_github_repo()
        try:
            file_content = repo.get_contents(DELIVERED_FILE_PATH, ref="main")
            delivered_df = pd.read_excel(io.BytesIO(file_content.decoded_content))
            sha = file_content.sha
        except:
            cols = ["RO_No", "In_Date", "Int_Date", "Sur_Date", "App_Date", "Dis_Date", 
                    "Den_Date", "Pnt_Date", "Fit_Date", "RBND_Date", "Smart_Status", "Final_Remark", "Delivered_At"]
            delivered_df = pd.DataFrame(columns=cols)
            sha = None

        row_dict = row_data.to_dict()
        row_dict["Delivered_At"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        delivered_df = pd.concat([delivered_df, pd.DataFrame([row_dict])], ignore_index=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            delivered_df.to_excel(writer, index=False)
        content = output.getvalue()
        
        if sha:
            repo.update_file(DELIVERED_FILE_PATH, f"Archived RO {row_dict['RO_No']}", content, sha)
        else:
            repo.create_file(DELIVERED_FILE_PATH, "Initial Delivered DB Creation", content, branch="main")
        return True
    except:
        return False

# SMART UPDATE: Is function me ab SHA pass karne ki zaroorat nahi hai, ye khud GitHub se latest nikalega
def save_to_github(df, message="Update Database"):
    try:
        repo = get_github_repo()
        
        # Hamesha write karne se thik pehle fresh SHA fetch karo taaki ban ya conflict na ho
        try:
            sha = repo.get_contents(FILE_PATH, ref="main").sha
        except:
            sha = None
            
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        content = output.getvalue()
        
        if not sha:
            repo.create_file(FILE_PATH, "Initial DB Creation", content, branch="main")
        else:
            repo.update_file(FILE_PATH, message, content, sha)
            
        st.cache_data.clear()
        st.session_state.last_save_time = datetime.now()
        st.session_state.lock_until = None # Lock clear karein
        return True
    except:
        st.session_state.lock_until = datetime.now() + timedelta(minutes=2)
        return False

# --- AUTH ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if not st.session_state.authenticated:
    st.title("🛡️ Secure Access")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Unlock System"):
        if pwd == APP_PASSWORD: st.session_state.authenticated = True; st.rerun()
    st.stop()

# --- MAIN APP ---
df = load_data_from_github()

# --- SIDEBAR & OPTIONS ---
st.sidebar.header("RO Search")
ro_input = st.sidebar.text_input("Enter RO Number", key="search_input").strip()
full_ro = ro_input.upper() 

existing_data = None
if full_ro and not df.empty:
    res = df[df['RO_No'] == full_ro]
    if not res.empty:
        existing_data = res.iloc[0]
        st.sidebar.success(f"✅ Loaded: {full_ro}")
        st.sidebar.divider()
        
        st.sidebar.subheader("Action Center")
        # OPTION 1: MOVE TO DELIVERY
        if st.sidebar.button("🚚 MOVE TO DELIVERY EXCEL"):
            with st.sidebar.spinner("Moving to delivered database..."):
                if move_to_delivered_github(existing_data):
                    new_df = df[df['RO_No'] != full_ro]
                    if save_to_github(new_df, f"Archived {full_ro}"):
                        st.sidebar.success("RO Sent to Delivery!"); time.sleep(1); st.rerun()
                else:
                    st.sidebar.error("❌ Archive failed! Main database safe.")
        
        # OPTION 2: PERMANENT DELETE
        if st.sidebar.button("❌ PERMANENT DELETE (NO ARCHIVE)"):
            with st.sidebar.spinner("Deleting permanently..."):
                new_df = df[df['RO_No'] != full_ro]
                if save_to_github(new_df, f"Permanently Deleted {full_ro}"):
                    st.sidebar.error("RO Deleted Permanently!"); time.sleep(1); st.rerun()
    else:
        st.sidebar.info(f"🆕 New Entry: {full_ro}")

st.sidebar.divider()

# 1. Main Database Download Button
towais = io.BytesIO()
with pd.ExcelWriter(towais, engine='openpyxl') as writer: df.to_excel(writer, index=False)
st.sidebar.download_button("📊 Download Main Excel", towais.getvalue(), f"Database_{datetime.now().strftime('%d_%m')}.xlsx")

# 2. DELIVERED DATABASE DOWNLOAD BUTTON
try:
    repo = get_github_repo()
    delivered_file = repo.get_contents(DELIVERED_FILE_PATH, ref="main")
    delivered_data = delivered_file.decoded_content
    st.sidebar.download_button("📦 Download Delivered Excel", delivered_data, f"Delivered_Database_{datetime.now().strftime('%d_%m')}.xlsx")
except:
    st.sidebar.info("ℹ️ Delivered DB empty ya abhi tak bani nahi hai.")

# --- CASH WORK STATUS DETECTION ---
is_cash_saved = False
if existing_data is not None:
    if str(existing_data.get('Smart_Status', "")) == "CASH" or "(cashwork)" in str(existing_data.get('Final_Remark', "")).lower():
        is_cash_saved = True

# --- REPAIR TIMELINE (SMART HYBRID INPUT) ---
st.subheader("📅 Repair Timeline")

fields = [
    ("In_Date", "In"), ("Int_Date", "Int"), ("Sur_Date", "Sur"), 
    ("Dis_Date", "Dis"), ("App_Date", "App"), ("Den_Date", "Den"), 
    ("Pnt_Date", "Pnt"), ("Fit_Date", "Fit"), ("RBND_Date", "RDY")
]

# Checkboxes at Top Level UI
cols_top = st.columns(2)
with cols_top[0]:
    pna_check = st.checkbox("🚨 MARK AS PNA", value=False if existing_data is None else (str(existing_data.get('Smart_Status', "")) == "PNA"), key=f"pna_{full_ro}")
with cols_top[1]:
    cash_check = st.checkbox("💰 CASH WORK (No Insurance)", value=is_cash_saved, disabled=pna_check, key=f"cash_{full_ro}")

cols = st.columns(5)
input_dates = {}

for i, (key, short) in enumerate(fields):
    # CASH WORK me Int, Sur, aur App Dates hide rahengi
    if cash_check and key in ["Int_Date", "Sur_Date", "App_Date"]:
        input_dates[key] = None
        continue
        
    with cols[i % 5]:
        d_key = f"date_{key}_{full_ro}"
        default_val = None
        
        if existing_data is not None:
            val = existing_data.get(key)
            if pd.notnull(val) and str(val).strip() not in ["", "nat", "None", "NaN"]:
                try: default_val = pd.to_datetime(val).date()
                except: pass
        
        d_input = st.date_input(short, value=default_val, format="DD/MM/YYYY", key=d_key)
        input_dates[key] = d_input

st.divider()

# --- STATUS & NOTES ---
if cash_check:
    status_list = ["WIP - Dismantle", "WIP - Denting", "WIP - Painting", "WIP - Fitting", "RBND - Vehicle Ready"]
    status_to_field_idx = {"WIP - Dismantle": 3, "WIP - Denting": 5, "WIP - Painting": 6, "WIP - Fitting": 7, "RBND - Vehicle Ready": 8}
else:
    status_list = ["ISP - Claim Intimation Pending", "ISP - Survey Pending", "IAP - Approval Pending", "WIP - Dismantle", "WIP - Denting", "WIP - Painting", "WIP - Fitting", "RBND - Vehicle Ready", "WCA - Waiting for Approval"]
    status_to_field_idx = {"ISP - Claim Intimation Pending": 1, "ISP - Survey Pending": 2, "IAP - Approval Pending": 4, "WIP - Dismantle": 3, "WIP - Denting": 5, "WIP - Painting": 6, "WIP - Fitting": 7, "RBND - Vehicle Ready": 8, "WCA - Waiting for Approval": -1}

default_idx, default_note = 0, ""
if existing_data is not None:
    current_status = str(existing_data.get('Smart_Status', ""))
    if current_status in status_list: 
        default_idx = status_list.index(current_status)
    
    remark_orig = str(existing_data.get('Final_Remark', ""))
    if " - " in remark_orig:
        parts = remark_orig.split(" - ")
        if len(parts) >= 4:
            potential_note = parts[-1].replace("(cashwork)", "").strip()
            if potential_note not in [s.split(" - ")[1] for s in status_list]:
                default_note = potential_note

status = st.selectbox("Current Stage", status_list, index=default_idx, disabled=pna_check, key=f"status_{full_ro}")
extra_note = st.text_input("📝 Extra Note", value=default_note, disabled=pna_check, key=f"note_{full_ro}")

# --- REMARK GENERATOR ---
final_remark = ""
if full_ro:
    day_month = f"{datetime.now().day}/{datetime.now().month}"
    if pna_check:
        final_remark, status = f"{day_month} - PNA", "PNA"
    else:
        cat = status.split(" - ")[0]
        pos = extra_note if extra_note.strip() != "" else status.split(" - ")[1]
        stage_idx = status_to_field_idx.get(status, -1)
        
        t_parts = []
        for i, (key, short) in enumerate(fields):
            if cash_check and key in ["Int_Date", "Sur_Date", "App_Date"]:
                continue
                
            val = input_dates.get(key)
            
            if i < stage_idx or status == "WCA - Waiting for Approval":
                if val:
                    t_parts.append(f"{short}: {val.day}/{val.month}")
                else:
                    t_parts.append(f"{short}:  ")
        
        timeline_str = " ,".join(t_parts)
        timeline_prefix = f" - {timeline_str}" if timeline_str else ""
        
        if cash_check:
            final_remark = f"{day_month} - {cat}{timeline_prefix} - {pos} (cashwork)"
            status = "CASH"
        else:
            final_remark = f"{day_month} - {cat}{timeline_prefix} - {pos}"
    
    # SMART UPDATE: DMS 100 Character Limit Protection
    if len(final_remark) > 100:
        # Step 1: Extra formatting spaces ko squeeze karein (` - ` -> `-`)
        final_remark = final_remark.replace(" - ", "-").replace(" ,", ",").replace(", ", ",").replace(": ", ":")
        # Step 2: Agar ab bhi 100 characters se bada hai, toh bache huye single spaces bhi trim karein
        if len(final_remark) > 100:
            final_remark = final_remark.replace(" ", "")
        # Step 3: Hard limit safety fallback taaki DMS kabhi reject na kare
        if len(final_remark) > 100:
            final_remark = final_remark[:100]

    st.info(f"📋 Final Remark Preview (Length: {len(final_remark)}/100):")
    st.code(final_remark)

# --- SAVE BUTTON ---
wait = get_wait_time()
btn_label = f"⚡ SAVE TO CLOUD" if wait <= 0 else f"⏳ WAIT {wait}s..."

if st.button(btn_label, disabled=(wait > 0)):
    if not full_ro:
        st.warning("RO Number daalein.")
    else:
        new_row = {"RO_No": full_ro, "Smart_Status": status, "Final_Remark": final_remark}
        for k, v in input_dates.items(): 
            new_row[k] = str(v) if v else ""
        
        temp_df = df[df['RO_No'] != full_ro]
        temp_df = pd.concat([temp_df, pd.DataFrame([new_row])], ignore_index=True)
        
        with st.spinner("💾 Saving..."):
            if save_to_github(temp_df):
                st.success("✅ Saved!"); time.sleep(1); st.rerun()

if wait > 0:
    time.sleep(1); st.rerun()