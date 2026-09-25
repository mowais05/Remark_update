import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from github import Github
import io
import time
import streamlit.components.v1 as components

# --- CONFIGURATION (SECURE) ---
APP_PASSWORD = "vddf2jjwm3"

# Direct Token Set for Local Testing
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = "mowais05/Remark_update" 

FILE_PATH = "database.xlsx"
DELIVERED_FILE_PATH = "delivered_database.xlsx"  # Delivered Database File Path

# Page Config
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
    limit = 2  # Smart Cooldown Limiter
    return int(limit - elapsed) if elapsed < limit else 0

# --- CUSTOM CSS ---
st.markdown("""
    
    """, unsafe_allow_html=True)

# --- GITHUB CORE ---
@st.cache_resource
def get_github_repo():
    try:
        g = Github(GITHUB_TOKEN)
        return g.get_repo(REPO_NAME)
    except Exception as e:
        st.error(f"GitHub Connection Error: {e}")
        return None

@st.cache_data(ttl=600)
def load_data_from_github():
    cols = ["RO_No", "In_Date", "Int_Date", "Sur_Date", "App_Date", "Dis_Date", 
            "Den_Date", "Pnt_Date", "Fit_Date", "RBND_Date", "Smart_Status", "Final_Remark"]
    try:
        repo = get_github_repo()
        if not repo:
            return pd.DataFrame(columns=cols)
        file_content = repo.get_contents(FILE_PATH, ref="main")
        df = pd.read_excel(io.BytesIO(file_content.decoded_content))
        df.columns = df.columns.str.strip()
        if 'RO_No' in df.columns:
            df['RO_No'] = df['RO_No'].astype(str).str.strip().str.upper()
        return df
    except Exception:
        return pd.DataFrame(columns=cols)

# --- MOVE SINGLE RO TO ARCHIVE ON GITHUB ---
def move_to_delivered_github(row_data):
    try:
        repo = get_github_repo()
        if not repo:
            return False
            
        try:
            file_content = repo.get_contents(DELIVERED_FILE_PATH, ref="main")
            delivered_df = pd.read_excel(io.BytesIO(file_content.decoded_content))
            sha = file_content.sha
        except Exception:
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
    except Exception:
        return False

# --- 🚀 NEW FEATURE: BULK MOVE TO DELIVERED WITH 1-100% PROGRESS BAR ---
def bulk_move_to_delivered_github(ro_list_to_move, current_df):
    try:
        repo = get_github_repo()
        if not repo:
            return False, "GitHub Connection Failed"
            
        # Get Delivered DB
        try:
            file_content = repo.get_contents(DELIVERED_FILE_PATH, ref="main")
            delivered_df = pd.read_excel(io.BytesIO(file_content.decoded_content))
            delivered_sha = file_content.sha
        except Exception:
            cols = ["RO_No", "In_Date", "Int_Date", "Sur_Date", "App_Date", "Dis_Date", 
                    "Den_Date", "Pnt_Date", "Fit_Date", "RBND_Date", "Smart_Status", "Final_Remark", "Delivered_At"]
            delivered_df = pd.DataFrame(columns=cols)
            delivered_sha = None

        matching_rows = current_df[current_df['RO_No'].isin(ro_list_to_move)].copy()
        if matching_rows.empty:
            return False, "Uploaded Excel ka koi bhi RO main database me nahi mila!"

        total_items = len(matching_rows)
        progress_bar = st.sidebar.progress(0)
        status_text = st.sidebar.empty()

        new_delivered_rows = []
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Step-by-step progress tracking
        for idx, (_, row) in enumerate(matching_rows.iterrows()):
            row_dict = row.to_dict()
            row_dict["Delivered_At"] = now_str
            new_delivered_rows.append(row_dict)
            
            # Progress update (1% to 100%)
            prog = int(((idx + 1) / total_items) * 100)
            progress_bar.progress(prog)
            status_text.text(f"Processing: {idx+1}/{total_items} ({prog}%)")
            time.sleep(0.02)  # Smooth UI feedback

        # Combine into Delivered DF
        delivered_df = pd.concat([delivered_df, pd.DataFrame(new_delivered_rows)], ignore_index=True)

        # Save Delivered DB to GitHub (Single Batch Request)
        out_del = io.BytesIO()
        with pd.ExcelWriter(out_del, engine='openpyxl') as writer:
            delivered_df.to_excel(writer, index=False)
        
        if delivered_sha:
            repo.update_file(DELIVERED_FILE_PATH, f"Bulk Archived {total_items} ROs", out_del.getvalue(), delivered_sha)
        else:
            repo.create_file(DELIVERED_FILE_PATH, "Initial Delivered DB Creation", out_del.getvalue(), branch="main")

        # Update Main DB (Remove delivered ROs)
        updated_main_df = current_df[~current_df['RO_No'].isin(ro_list_to_move)]
        save_to_github(updated_main_df, f"Bulk Delivered {total_items} ROs")

        status_text.success(f"✅ Successfully Moved {total_items} ROs!")
        return True, f"{total_items} ROs Moved successfully!"
    except Exception as e:
        return False, str(e)

def save_to_github(df, message="Update Database"):
    try:
        repo = get_github_repo()
        if not repo:
            return False
        
        try:
            sha = repo.get_contents(FILE_PATH, ref="main").sha
        except Exception:
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
        st.session_state.lock_until = None
        return True
    except Exception:
        st.session_state.lock_until = datetime.now() + timedelta(minutes=2)
        return False

# --- AUTH ---
if "authenticated" not in st.session_state: 
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🛡️ Secure Access")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Unlock System"):
        if pwd == APP_PASSWORD: 
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Incorrect Password")
    st.stop()

# --- MAIN APP ---
df = load_data_from_github()

# --- 🚀 RO INPUT & NOTIFICATION ON MAIN PAGE ---
st.header("🔍 RO Data Entry")
ro_input = st.text_input("Enter RO Number", key="search_input").strip()
full_ro = ro_input.upper()

# Main Screen Notification
existing_data = None
if full_ro and not df.empty:
    res = df[df['RO_No'] == full_ro]
    if not res.empty:
        existing_data = res.iloc[0]
        st.success(f"✅ Loaded: {full_ro}")
    else:
        st.info(f"🆕 New Entry: {full_ro}")

# --- STRICT DATE PICKER KEYBOARD POPUP BLOCKER ---
components.html(
    """
    
    """,
    height=0,
    width=0
)

# --- SIDEBAR & OPTIONS ---
st.sidebar.header("Data Actions")

if existing_data is not None:
    st.sidebar.subheader("Action Center")
    if st.sidebar.button("🚚 MOVE TO DELIVERY EXCEL"):
        with st.sidebar.spinner("Moving to delivered database..."):
            if move_to_delivered_github(existing_data):
                new_df = df[df['RO_No'] != full_ro]
                if save_to_github(new_df, f"Archived {full_ro}"):
                    st.sidebar.success("RO Sent to Delivery!")
                    time.sleep(1)
                    st.rerun()
            else:
                st.sidebar.error("❌ Archive failed! Main database safe.")
    
    if st.sidebar.button("❌ PERMANENT DELETE (NO ARCHIVE)"):
        with st.sidebar.spinner("Deleting permanently..."):
            new_df = df[df['RO_No'] != full_ro]
            if save_to_github(new_df, f"Permanently Deleted {full_ro}"):
                st.sidebar.error("RO Deleted Permanently!")
                time.sleep(1)
                st.rerun()

st.sidebar.divider()

# --- 🚀 NEW FEATURE: BULK DELIVERY EXCEL UPLOAD ---
st.sidebar.subheader("📦 Bulk Delivery Upload")
bulk_file = st.sidebar.file_uploader("Upload Excel with ROs", type=["xlsx", "xls"], key="bulk_ro_uploader")

if bulk_file is not None:
    if st.sidebar.button("🚀 PROCESS BULK DELIVERY"):
        try:
            bulk_df = pd.read_excel(bulk_file)
            ro_col = None
            for c in bulk_df.columns:
                if "RO" in str(c).upper():
                    ro_col = c
                    break
            if ro_col is None:
                ro_col = bulk_df.columns[0]
            
            upload_ros = bulk_df[ro_col].astype(str).str.strip().str.upper().tolist()
            upload_ros = [r for r in upload_ros if r and r.lower() not in ["nan", "none", "nat"]]

            if not upload_ros:
                st.sidebar.error("❌ File me koi valid RO Number nahi mila!")
            else:
                success, msg = bulk_move_to_delivered_github(upload_ros, df)
                if success:
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error(f"❌ Error: {msg}")
        except Exception as e:
            st.sidebar.error(f"❌ File read error: {e}")

st.sidebar.divider()

# Download Buttons
towais = io.BytesIO()
with pd.ExcelWriter(towais, engine='openpyxl') as writer: 
    df.to_excel(writer, index=False)
st.sidebar.download_button("📊 Download Main Excel", towais.getvalue(), f"Database_{datetime.now().strftime('%d_%m')}.xlsx")

try:
    repo = get_github_repo()
    if repo:
        delivered_file = repo.get_contents(DELIVERED_FILE_PATH, ref="main")
        delivered_data = delivered_file.decoded_content
        st.sidebar.download_button("📦 Download Delivered Excel", delivered_data, f"Delivered_Database_{datetime.now().strftime('%d_%m')}.xlsx")
except Exception:
    st.sidebar.info("ℹ️ Delivered DB empty ya abhi tak bani nahi hai.")

# --- CASH WORK STATUS DETECTION ---
is_cash_saved = False
if existing_data is not None:
    if str(existing_data.get('Smart_Status', "")) == "CASH" or "(cashwork)" in str(existing_data.get('Final_Remark', "")).lower():
        is_cash_saved = True

# --- REPAIR TIMELINE ---
st.subheader("📅 Repair Timeline")

fields = [
    ("In_Date", "In"), ("Int_Date", "Int"), ("Sur_Date", "Sur"), 
    ("Dis_Date", "Dis"), ("App_Date", "App"), ("Den_Date", "Den"), 
    ("Pnt_Date", "Pnt"), ("Fit_Date", "Fit"), ("RBND_Date", "RDY")
]

cols_top = st.columns(2)
with cols_top[0]:
    pna_check = st.checkbox("🚨 MARK AS PNA", value=False if existing_data is None else (str(existing_data.get('Smart_Status', "")) == "PNA"), key=f"pna_{full_ro}")
with cols_top[1]:
    cash_check = st.checkbox("💰 CASH WORK (No Insurance)", value=is_cash_saved, disabled=pna_check, key=f"cash_{full_ro}")

input_dates = {}

# Row-by-Row rendering (3 fields per row) to ensure strict chronological order on mobile screens
for row_idx in range(0, len(fields), 3):
    row_fields = fields[row_idx:row_idx + 3]
    cols = st.columns(len(row_fields))
    for col_idx, (key, short) in enumerate(row_fields):
        if cash_check and key in ["Int_Date", "Sur_Date", "App_Date"]:
            input_dates[key] = None
            continue
            
        with cols[col_idx]:
            d_key = f"date_{key}_{full_ro}"
            default_val = None
            
            if existing_data is not None:
                val = existing_data.get(key)
                if pd.notnull(val) and str(val).strip().lower() not in ["", "nat", "none", "nan"]:
                    try: 
                        default_val = pd.to_datetime(val).date()
                    except Exception: 
                        pass
            
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
        # 🚀 UPDATED PNA REMARK FORMAT
        final_remark, status = f"{day_month} - PNA - Part not available", "PNA"
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
    
    if len(final_remark) > 100:
        final_remark = final_remark.replace(" - ", "-").replace(" ,", ",").replace(", ", ",").replace(": ", ":")
        if len(final_remark) > 100:
            final_remark = final_remark.replace(" ", "")
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
                st.success("✅ Saved!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Save failed! GitHub API rate limit ya error check karein.")

if wait > 0:
    time.sleep(1)
    st.rerun()
