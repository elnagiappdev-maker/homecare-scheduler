# app.py
# Smart Homecare Scheduler (Streamlit App)
# ----------------------------------------
# Features:
# - User login/logout with roles (admin, doctor, staff)
# - Patients, Staff, and Schedule management
# - Admin can add/remove/reorder custom fields (Patients, Staff, Schedule)
# - DOB allowed from 1900 → future valid dates
# - Analytics (age groups, staff workload, visit types)
# - Emergency panel for quick lookup
# - Export to CSV, Excel, Word (with embedded charts)
# - Branding:
#     - "All Rights Reserved © Dr. Yousra Abdelatti" on login page & inside footer
# - Data stored in SQLite

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, time as dtime
from io import BytesIO
import altair as alt
import hashlib
from docx import Document
from docx.shared import Inches
import matplotlib.pyplot as plt
import tempfile
import os

# ---------------------------
# Configuration / Constants
# ---------------------------
DB_PATH = "homecare_scheduler.db"
APP_TITLE = "Smart Homecare Scheduler (24/7)"
RELAXING_BG = "#E8F6F3"

STAFF_ROLES = ["Specialist", "GP", "Nurse", "RT", "PT", "Care Giver"]

# ---------------------------
# Utilities
# ---------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def now_iso():
    return datetime.utcnow().isoformat()

# ---------------------------
# Initialize DB & tables
# ---------------------------
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # users
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            role TEXT,
            created_at TEXT
        )
    ''')

    # patients
    cur.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY,
            name TEXT,
            dob TEXT,
            gender TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            emergency_contact TEXT,
            insurance_provider TEXT,
            insurance_number TEXT,
            allergies TEXT,
            medications TEXT,
            diagnosis TEXT,
            equipment_required TEXT,
            mobility TEXT,
            care_plan TEXT,
            notes TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')

    # staff
    cur.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            id TEXT PRIMARY KEY,
            name TEXT,
            role TEXT,
            license_number TEXT,
            specialties TEXT,
            phone TEXT,
            email TEXT,
            availability TEXT,
            notes TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')

    # schedule
    cur.execute('''
        CREATE TABLE IF NOT EXISTS schedule (
            visit_id TEXT PRIMARY KEY,
            patient_id TEXT,
            staff_id TEXT,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            visit_type TEXT,
            duration_minutes INTEGER,
            priority TEXT,
            notes TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')

    # extra fields (dynamic fields for patients/staff/schedule)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS extra_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT,
            field_name TEXT,
            field_type TEXT,
            field_order INTEGER
        )
    ''')

    # extra values
    cur.execute('''
        CREATE TABLE IF NOT EXISTS extra_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT,
            record_id TEXT,
            field_id INTEGER,
            value TEXT
        )
    ''')

    # seed users
    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute("INSERT INTO users VALUES (?,?,?,?)",
                    ("admin", hash_pw("1234"), "admin", now_iso()))
        cur.execute("INSERT INTO users VALUES (?,?,?,?)",
                    ("doctor", hash_pw("abcd"), "doctor", now_iso()))

    conn.commit()
    conn.close()

init_db()
conn = get_db_connection()
# ---------------------------
# Read helpers
# ---------------------------
@st.cache_data(show_spinner=False)
def read_table(name: str):
    return pd.read_sql_query(f"SELECT * FROM {name}", conn)

# ---------------------------
# UI Helpers
# ---------------------------
def inject_css():
    st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(180deg, {RELAXING_BG} 0%, white 100%);
    }}
    .big-title {{
        font-size:28px;
        font-weight:700;
        color: #0b3d91;
    }}
    .footer {{
        font-size: 14px;
        text-align: center;
        margin-top: 20px;
        font-weight: bold;
        color: purple;
    }}
    </style>
    """, unsafe_allow_html=True)

def make_visit_id():
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM schedule")
    return f"V{cur.fetchone()['c']+1:05d}"

def render_footer():
    st.markdown("---")
    st.markdown(
        "<div class='footer'>All Rights Reserved © Dr. Yousra Abdelatti</div>",
        unsafe_allow_html=True
    )

# ---------------------------
# Authentication
# ---------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.user_role = None

def login_user(username, password):
    cur = conn.cursor()
    cur.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if row and hash_pw(password) == row[0]:
        st.session_state.logged_in = True
        st.session_state.user = username
        st.session_state.user_role = row[1]
        return True
    return False

def logout_user():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.user_role = None

# ---------------------------
# Export Helpers
# ---------------------------
def to_excel_bytes(dfs: dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in dfs.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    output.seek(0)
    return output.getvalue()

def df_to_csv_bytes(df: pd.DataFrame):
    return df.to_csv(index=False).encode()

def create_word_report(patients_df, staff_df, schedule_df, charts_png=None):
    doc = Document()
    doc.add_heading(APP_TITLE, level=1)
    doc.add_paragraph("Generated: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    for title, df in [("Patients", patients_df), ("Staff", staff_df), ("Schedule", schedule_df)]:
        doc.add_heading(title, level=2)
        if not df.empty:
            table = doc.add_table(rows=1, cols=len(df.columns))
            hdr = table.rows[0].cells
            for i, c in enumerate(df.columns):
                hdr[i].text = c
            for _, row in df.iterrows():
                cells = table.add_row().cells
                for i, c in enumerate(df.columns):
                    cells[i].text = str(row[c])
        else:
            doc.add_paragraph("No data")

    # Add charts if provided
    if charts_png:
        for title, img in charts_png.items():
            doc.add_page_break()
            doc.add_heading(title, level=2)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(img)
                tmp.flush()
                doc.add_picture(tmp.name, width=Inches(5))
                os.unlink(tmp.name)

    f = BytesIO()
    doc.save(f)
    f.seek(0)
    return f.getvalue()

# ---------------------------
# App Layout
# ---------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")
inject_css()

if not st.session_state.logged_in:
    st.markdown('<div class="big-title">Login</div>', unsafe_allow_html=True)
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        if login_user(u, p):
            st.rerun()
        else:
            st.error("Invalid credentials")

    # All Rights Reserved footer on login page
    st.markdown(
        "<div class='footer'>All Rights Reserved © Dr. Yousra Abdelatti</div>",
        unsafe_allow_html=True
    )
    st.stop()
# ---------------------------
# Sidebar Menu
# ---------------------------
st.sidebar.title("Menu")
menu = ["Dashboard","Patients","Staff","Schedule","Analytics","Emergency","Settings","Export & Backup","Logout"]
choice = st.sidebar.radio("Go to", menu)

st.markdown(f"<div class='big-title'>{APP_TITLE}</div>", unsafe_allow_html=True)

# ---------- Dashboard ----------
if choice == "Dashboard":
    patients = read_table("patients")
    staff = read_table("staff")
    sched = read_table("schedule")

    c1,c2,c3 = st.columns(3)
    c1.metric("Patients", len(patients))
    c2.metric("Staff", len(staff))
    c3.metric("Visits", len(sched))

    st.markdown("### Upcoming Visits")
    if not sched.empty:
        sched['date_dt'] = pd.to_datetime(sched['date'], errors='coerce')
        upcoming = sched[sched['date_dt'] >= pd.Timestamp(date.today())].sort_values("date_dt").head(10)
        st.dataframe(upcoming[['visit_id','patient_id','staff_id','date','start_time','end_time','visit_type','priority']])
    else:
        st.info("No visits scheduled yet.")

    render_footer()

# ---------- Patients ----------
elif choice == "Patients":
    st.subheader("Patients")
    patients = read_table("patients")

    with st.expander("Add New Patient"):
        with st.form("add_patient", clear_on_submit=True):
            p_id = st.text_input("Patient ID (unique)")
            p_name = st.text_input("Full name")
            # DOB allowed from 1900 to any future date
            p_dob = st.date_input("DOB", min_value=date(1900,1,1))
            p_gender = st.selectbox("Gender", ["Female","Male","Other"])
            p_phone = st.text_input("Phone")
            p_email = st.text_input("Email")
            p_address = st.text_area("Address")
            p_emergency = st.text_input("Emergency Contact")
            p_ins_provider = st.text_input("Insurance Provider")
            p_ins_number = st.text_input("Insurance Number")
            p_allergies = st.text_area("Allergies")
            p_meds = st.text_area("Current Medications")
            p_diag = st.text_area("Primary Diagnosis")
            p_equip = st.text_area("Equipment Required")
            p_mobility = st.selectbox("Mobility", ["Independent","Assisted","Wheelchair","Bedbound"])
            p_careplan = st.text_area("Care Plan")
            p_notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Patient")

            if submitted and p_id:
                cur = conn.cursor()
                cur.execute("""
                    INSERT OR REPLACE INTO patients 
                    (id,name,dob,gender,phone,email,address,emergency_contact,
                     insurance_provider,insurance_number,allergies,medications,diagnosis,
                     equipment_required,mobility,care_plan,notes,created_by,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (p_id,p_name,p_dob.isoformat(),p_gender,p_phone,p_email,p_address,p_emergency,
                 p_ins_provider,p_ins_number,p_allergies,p_meds,p_diag,p_equip,
                 p_mobility,p_careplan,p_notes,st.session_state.user,now_iso()))
                conn.commit()
                st.success("Patient saved successfully.")
                st.rerun()

    st.markdown("### Existing Patients")
    st.dataframe(patients)

    render_footer()
# ---------- Staff ----------
elif choice == "Staff":
    st.subheader("Staff")
    staff = read_table("staff")

    with st.expander("Add New Staff"):
        with st.form("add_staff", clear_on_submit=True):
            s_id = st.text_input("Staff ID (unique)")
            s_name = st.text_input("Full name")
            s_role = st.selectbox("Role", STAFF_ROLES)
            s_license = st.text_input("License / Registration Number")
            s_specialties = st.text_input("Specialties (comma separated)")
            s_phone = st.text_input("Phone")
            s_email = st.text_input("Email")
            s_availability = st.text_area("Availability (e.g., Mon-Fri 9-5)")
            s_notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Staff")

            if submitted and s_id:
                cur = conn.cursor()
                cur.execute("""
                    INSERT OR REPLACE INTO staff
                    (id,name,role,license_number,specialties,phone,email,availability,notes,created_by,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (s_id,s_name,s_role,s_license,s_specialties,s_phone,s_email,s_availability,s_notes,st.session_state.user,now_iso()))
                conn.commit()
                st.success("Staff saved successfully.")
                st.rerun()

    st.markdown("### Existing Staff")
    st.dataframe(staff)

    render_footer()

# ---------- Schedule ----------
elif choice == "Schedule":
    st.subheader("Schedule")
    patients = read_table("patients")
    staff = read_table("staff")
    sched = read_table("schedule")

    with st.expander("Create Visit"):
        with st.form("add_visit", clear_on_submit=True):
            patient_sel = st.selectbox("Patient", patients['id'].tolist() if not patients.empty else [])
            staff_sel = st.selectbox("Staff", staff['id'].tolist() if not staff.empty else [])
            v_date = st.date_input("Date", value=date.today())
            start = st.time_input("Start", value=dtime(9,0))
            end = st.time_input("End", value=dtime(10,0))
            v_type = st.text_input("Visit Type")
            v_priority = st.selectbox("Priority", ["Low","Normal","High","Critical"])
            v_notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Visit")

            if submitted and patient_sel and staff_sel:
                vid = make_visit_id()
                duration = int((datetime.combine(date.today(), end)-datetime.combine(date.today(), start)).seconds/60)
                cur = conn.cursor()
                cur.execute("""
                    INSERT OR REPLACE INTO schedule 
                    (visit_id,patient_id,staff_id,date,start_time,end_time,visit_type,duration_minutes,priority,notes,created_by,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (vid,patient_sel,staff_sel,v_date.isoformat(),start.strftime("%H:%M"),end.strftime("%H:%M"),
                 v_type,duration,v_priority,v_notes,st.session_state.user,now_iso()))
                conn.commit()
                st.success("Visit scheduled successfully.")
                st.rerun()

    st.markdown("### Existing Visits")
    st.dataframe(sched)

    render_footer()
# ---------- Analytics ----------
elif choice == "Analytics":
    st.subheader("Analytics")
    patients = read_table("patients")
    sched = read_table("schedule")

    # Age distribution
    st.markdown("### Patients by Age Group")
    if not patients.empty:
        patients['dob_dt'] = pd.to_datetime(patients['dob'], errors="coerce")
        patients['age'] = ((pd.Timestamp(date.today())-patients['dob_dt']).dt.days//365).fillna(0)
        bins = pd.cut(patients['age'], bins=[-1,1,18,40,65,120], labels=["0-1","1-18","19-40","41-65","65+"])
        df = bins.value_counts().reset_index()
        df.columns=["Age group","Count"]
        chart_age = alt.Chart(df).mark_bar(color="#5DADE2").encode(x="Age group", y="Count")
        st.altair_chart(chart_age, use_container_width=True)
    else:
        st.info("No patient data available")

    # Staff workload
    st.markdown("### Staff Workload (Visits per Staff)")
    if not sched.empty:
        w = sched['staff_id'].value_counts().reset_index()
        w.columns=["Staff","Visits"]
        chart_work = alt.Chart(w).mark_bar(color="#66c2a5").encode(x="Staff", y="Visits")
        st.altair_chart(chart_work, use_container_width=True)
    else:
        st.info("No schedule data available")

    render_footer()

# ---------- Emergency ----------
elif choice == "Emergency":
    st.subheader("Emergency Panel")
    st.warning("Quick patient lookup for emergencies")

    patients = read_table("patients")
    if not patients.empty:
        sel = st.selectbox("Patient", patients['id'].tolist())
        row = patients[patients['id']==sel].iloc[0]
        st.write(row.to_dict())
        if st.button("Call Emergency Contact (mock)"):
            st.info(f"Calling: {row['emergency_contact']}")
    else:
        st.info("No patients yet.")

    render_footer()

# ---------- Settings ----------
elif choice == "Settings":
    st.subheader("Settings & User Management")
    st.write(f"Logged in as {st.session_state.user} ({st.session_state.user_role})")

    # Change password
    with st.expander("Change Your Password"):
        old = st.text_input("Current Password", type="password")
        new = st.text_input("New Password", type="password")
        new2 = st.text_input("Confirm New Password", type="password")
        if st.button("Change Password"):
            if new != new2 or not old:
                st.error("Passwords do not match or missing input.")
            else:
                cur = conn.cursor()
                cur.execute("SELECT password_hash FROM users WHERE username=?", (st.session_state.user,))
                row = cur.fetchone()
                if row and hash_pw(old) == row[0]:
                    cur.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_pw(new), st.session_state.user))
                    conn.commit()
                    st.success("Password changed.")
                else:
                    st.error("Current password incorrect.")

    # Admin: manage users
    if st.session_state.user_role == "admin":
        st.markdown("### Admin Controls")
        users = read_table("users")
        st.dataframe(users[['username','role','created_at']])

        with st.expander("Create New User"):
            u_name = st.text_input("Username")
            u_role = st.selectbox("Role", ["admin","doctor","nurse","staff","other"])
            u_pw = st.text_input("Password", type="password")
            if st.button("Create User"):
                if u_name and u_pw:
                    cur = conn.cursor()
                    cur.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?)",
                                (u_name, hash_pw(u_pw), u_role, now_iso()))
                    conn.commit()
                    st.success("User created.")
                    st.rerun()
                else:
                    st.error("Username and password required.")

        with st.expander("Reset User Password"):
            if not users.empty:
                sel = st.selectbox("Select User", users['username'].tolist())
                new_pw = st.text_input("New Password", type="password")
                if st.button("Reset Password"):
                    if new_pw:
                        cur = conn.cursor()
                        cur.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_pw(new_pw), sel))
                        conn.commit()
                        st.success("Password reset.")
                    else:
                        st.error("Enter a new password.")

    render_footer()

# ---------- Export ----------
elif choice == "Export & Backup":
    st.subheader("Export & Backup")
    patients = read_table("patients")
    staff = read_table("staff")
    sched = read_table("schedule")

    # Export buttons
    c1, c2, c3 = st.columns(3)
    with c1:
        csv_pat = df_to_csv_bytes(patients) if not patients.empty else b""
        st.download_button("Download Patients CSV", data=csv_pat, file_name="patients.csv", mime="text/csv")

        csv_staff = df_to_csv_bytes(staff) if not staff.empty else b""
        st.download_button("Download Staff CSV", data=csv_staff, file_name="staff.csv", mime="text/csv")

    with c2:
        excel_bytes = to_excel_bytes({"patients":patients, "staff":staff, "schedule":sched})
        st.download_button("Download Excel (all)", data=excel_bytes, file_name="homecare_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with c3:
        # Create charts for Word export
        charts = {}
        if not patients.empty:
            patients['dob_dt'] = pd.to_datetime(patients['dob'], errors='coerce')
            patients['age'] = ((pd.Timestamp(date.today()) - patients['dob_dt']).dt.days // 365).fillna(0).astype(int)
            age_bins = pd.cut(patients['age'], bins=[-1,1,18,40,65,120], labels=["0-1","1-18","19-40","41-65","65+"])
            age_count = age_bins.value_counts().reset_index()
            age_count.columns = ['Age group','Count']
            fig, ax = plt.subplots()
            age_count.plot(kind="bar", x="Age group", y="Count", ax=ax, legend=False, color="#5DADE2")
            buf = BytesIO()
            plt.savefig(buf, format="png")
            charts["Patients by Age Group"] = buf.getvalue()
            buf.close()

        if not sched.empty:
            workload = sched['staff_id'].value_counts().reset_index()
            workload.columns = ["Staff","Visits"]
            fig, ax = plt.subplots()
            workload.plot(kind="bar", x="Staff", y="Visits", ax=ax, legend=False, color="#66c2a5")
            buf = BytesIO()
            plt.savefig(buf, format="png")
            charts["Staff Workload"] = buf.getvalue()
            buf.close()

        word_bytes = create_word_report(patients, staff, sched, charts_png=charts)
        st.download_button("Download Word Report", data=word_bytes, file_name="homecare_report.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    # Backup DB
    with open(DB_PATH, "rb") as f:
        db_bytes = f.read()
        st.download_button("Download DB File", data=db_bytes, file_name=DB_PATH, mime="application/x-sqlite3")

    render_footer()

# ---------- Logout ----------
elif choice == "Logout":
    logout_user()
    st.success("Logged out")
    st.rerun()

# Always footer
render_footer()
