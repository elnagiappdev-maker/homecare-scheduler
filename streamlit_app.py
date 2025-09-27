# -*- coding: utf-8 -*-
# app.py
# Smart Homecare Scheduler (full restored version, deployment-ready)
# Footer / branding:
#   Login page:  All Rights Reserved © Dr. Yousra Abdelatti (purple)
#   In-app footer: Developed By Dr. Mohammedelnagi Mohammed (small blue)
#
# NOTE: create requirements.txt (provided below) in the same repo before deploying.

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, time as dtime, timedelta
from io import BytesIO
import hashlib
import os
import tempfile
import matplotlib.pyplot as plt
import altair as alt
from docx import Document
from docx.shared import Inches

# ---------------------------
# Configuration / Constants
# ---------------------------
DB_PATH = "homecare_scheduler.db"
APP_TITLE = "Smart Homecare Scheduler (24/7)"
RELAXING_BG = "#E8F6F3"
ACCENT = "#5DADE2"
SMALL_FOOTER_STYLE = "font-size:12px; color:blue;"

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
    # patients (full fields)
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
    # staff (full fields)
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
    # schedule (full fields)
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
            recurring_rule TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')
    # seed admin & doctor users if none
    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                    ("admin", hash_pw("1234"), "admin", now_iso()))
        cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                    ("doctor", hash_pw("abcd"), "doctor", now_iso()))
    conn.commit()
    conn.close()

init_db()
conn = get_db_connection()

# ---------------------------
# Cached reads
# ---------------------------
@st.cache_data(show_spinner=False)
def read_table(name: str):
    return pd.read_sql_query(f"SELECT * FROM {name}", conn)

# ---------------------------
# UI helpers & CSS
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
        margin-bottom: 0.2rem;
    }}
    .small-footer {{
        {SMALL_FOOTER_STYLE}
    }}
    </style>
    """, unsafe_allow_html=True)

def make_visit_id():
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM schedule")
    count = cur.fetchone()["c"] + 1
    return f"V{count:05d}"

def render_footer():
    st.markdown("---")
    st.markdown(f"<div style='text-align:center;'><span style='font-weight:bold; color:purple;'>All Rights Reserved © Dr. Yousra Abdelatti</span></div>", unsafe_allow_html=True)
    st.markdown(f"<div style='text-align:center;'><span class='small-footer'>Developed By Dr. Mohammedelnagi Mohammed</span></div>", unsafe_allow_html=True)

# ---------------------------
# Authentication & session
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
    keys = list(st.session_state.keys())
    for k in keys:
        if k.startswith("theme"):
            continue
        try:
            del st.session_state[k]
        except Exception:
            pass
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.user_role = None

# ---------------------------
# Export helpers (Excel/CSV/Word)
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

def _save_png_from_matplotlib(fig):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    fig.savefig(tmp.name, bbox_inches='tight')
    tmp.close()
    with open(tmp.name, "rb") as f:
        data = f.read()
    try:
        os.unlink(tmp.name)
    except Exception:
        pass
    return data

def create_word_report(patients_df, staff_df, schedule_df, charts=None):
    doc = Document()
    doc.add_heading(APP_TITLE, level=1)
    doc.add_paragraph("Report generated: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    # patients
    doc.add_heading("Patients", level=2)
    if not patients_df.empty:
        table = doc.add_table(rows=1, cols=len(patients_df.columns))
        hdr = table.rows[0].cells
        for i, c in enumerate(patients_df.columns):
            hdr[i].text = str(c)
        for _, r in patients_df.iterrows():
            row_cells = table.add_row().cells
            for i, c in enumerate(patients_df.columns):
                val = r[c]
                row_cells[i].text = "" if pd.isna(val) else str(val)
    else:
        doc.add_paragraph("No patients data.")
    # staff
    doc.add_heading("Staff", level=2)
    if not staff_df.empty:
        table = doc.add_table(rows=1, cols=len(staff_df.columns))
        hdr = table.rows[0].cells
        for i, c in enumerate(staff_df.columns):
            hdr[i].text = str(c)
        for _, r in staff_df.iterrows():
            row_cells = table.add_row().cells
            for i, c in enumerate(staff_df.columns):
                val = r[c]
                row_cells[i].text = "" if pd.isna(val) else str(val)
    else:
        doc.add_paragraph("No staff data.")
    # schedule
    doc.add_heading("Schedule", level=2)
    if not schedule_df.empty:
        table = doc.add_table(rows=1, cols=len(schedule_df.columns))
        hdr = table.rows[0].cells
        for i, c in enumerate(schedule_df.columns):
            hdr[i].text = str(c)
        for _, r in schedule_df.iterrows():
            row_cells = table.add_row().cells
            for i, c in enumerate(schedule_df.columns):
                val = r[c]
                row_cells[i].text = "" if pd.isna(val) else str(val)
    else:
        doc.add_paragraph("No schedule data.")
    # embed charts
    if charts:
        for title, png in charts.items():
            doc.add_page_break()
            doc.add_heading(title, level=2)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(png)
                tmp.flush()
                doc.add_picture(tmp.name, width=Inches(6))
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
    f = BytesIO()
    doc.save(f)
    f.seek(0)
    return f.getvalue()

# ---------------------------
# App layout & logic
# ---------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
inject_css()

# --- Login page (All Rights Reserved shown here) ---
if not st.session_state.logged_in:
    st.markdown('<div class="big-title">Smart Homecare Scheduler Login</div>', unsafe_allow_html=True)
    st.markdown("<div style='text-align:center;'><span style='font-weight:bold; color:purple;'>All Rights Reserved © Dr. Yousra Abdelatti</span></div>", unsafe_allow_html=True)
    st.write("")
    col1, col2 = st.columns([1,1])
    with col1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pw")
        if st.button("Login"):
            if login_user(username, password):
                st.success(f"Welcome back, {st.session_state.user} ({st.session_state.user_role})")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    with col2:
        st.write("Demo accounts: admin / 1234  •  doctor / abcd")
        st.write("If you don't have an account ask the admin to create one (Settings > Create user).")
    st.stop()

# --- Main app when logged in ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/8/88/Patient_icon.svg", width=96)
st.sidebar.title("Menu")
menu = ["Dashboard","Patients","Staff","Schedule","Analytics","Emergency","Settings","Export & Backup","Logout"]
choice = st.sidebar.selectbox("Go to", menu)

st.markdown(f"<div class='big-title'>{APP_TITLE}</div>", unsafe_allow_html=True)

# ---------- Dashboard ----------
if choice == "Dashboard":
    st.subheader("Dashboard")
    patients_df = read_table("patients")
    staff_df = read_table("staff")
    schedule_df = read_table("schedule")

    c1, c2, c3 = st.columns(3)
    c1.metric("Patients", len(patients_df))
    c2.metric("Staff", len(staff_df))
    c3.metric("Scheduled Visits", len(schedule_df))

    st.markdown("---")
    st.write("Upcoming visits (next 30 days):")
    if len(schedule_df) > 0:
        schedule_df['date_dt'] = pd.to_datetime(schedule_df['date'], errors='coerce')
        upcoming = schedule_df[(schedule_df['date_dt'] >= pd.Timestamp(date.today())) & (schedule_df['date_dt'] <= pd.Timestamp(date.today()+timedelta(days=30)))]
        upcoming = upcoming.sort_values(['date','start_time']).head(100)
        st.dataframe(upcoming[['visit_id','patient_id','staff_id','date','start_time','end_time','visit_type','priority']])
    else:
        st.info("No visits scheduled yet.")

    # quick analytics previews
    st.markdown("### Quick analytics")
    col1, col2 = st.columns(2)
    with col1:
        if not patients_df.empty:
            dfp = patients_df.copy()
            dfp['dob_dt'] = pd.to_datetime(dfp['dob'], errors='coerce')
            dfp['age'] = ((pd.Timestamp(date.today()) - dfp['dob_dt']).dt.days // 365).fillna(0).astype(int)
            age_bins = pd.cut(dfp['age'], bins=[-1,0,1,5,12,18,40,65,200],
                              labels=["<1","1-5","6-12","13-18","19-40","41-65","66-200"])
            age_count = age_bins.value_counts().sort_index().reset_index()
            age_count.columns = ['age_group','count']
            st.altair_chart((alt.Chart(age_count).mark_bar(color=ACCENT).encode(x='age_group', y='count')).properties(height=240), use_container_width=True)
        else:
            st.info("Add patients to see age distribution.")
    with col2:
        if not schedule_df.empty:
            vtypes = schedule_df['visit_type'].fillna("Unknown").value_counts().reset_index()
            vtypes.columns = ['visit_type','count']
            st.altair_chart((alt.Chart(vtypes).mark_arc().encode(theta='count', color='visit_type')).properties(height=240), use_container_width=True)
        else:
            st.info("No visits to show distribution.")
    render_footer()

# ---------- Patients ----------
elif choice == "Patients":
    st.subheader("Manage Patients")
    patients_df = read_table("patients")

    # Add patient form
    with st.expander("Add new patient (full details)"):
        with st.form("add_patient_form", clear_on_submit=True):
            p_id = st.text_input("Patient ID (unique)", help="Unique ID e.g. P0001")
            p_name = st.text_input("Full name")
            # DOB allowed from 1900-01-01 to any future date
            p_dob = st.date_input("Date of birth", value=date(1950,1,1), min_value=date(1900,1,1))
            p_gender = st.selectbox("Gender", ["Female","Male","Other","Prefer not to say"])
            p_phone = st.text_input("Phone")
            p_email = st.text_input("Email")
            p_address = st.text_area("Address")
            p_emergency = st.text_input("Emergency contact (name & phone)")
            p_ins_provider = st.text_input("Insurance provider")
            p_ins_number = st.text_input("Insurance number")
            p_allergies = st.text_area("Allergies")
            p_meds = st.text_area("Current medications")
            p_diag = st.text_area("Primary diagnosis")
            p_equip = st.text_area("Equipment required")
            p_mobility = st.selectbox("Mobility level", ["Independent","Assisted","Wheelchair","Bedbound"])
            p_careplan = st.text_area("Care plan summary")
            p_notes = st.text_area("Notes / social history")
            submitted = st.form_submit_button("Add patient")
            if submitted:
                if not p_id.strip():
                    st.error("Patient ID required.")
                else:
                    cur = conn.cursor()
                    cur.execute("""INSERT OR REPLACE INTO patients
                                   (id,name,dob,gender,phone,email,address,emergency_contact,insurance_provider,insurance_number,allergies,medications,diagnosis,equipment_required,mobility,care_plan,notes,created_by,created_at)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (p_id,p_name,p_dob.isoformat(),p_gender,p_phone,p_email,p_address,p_emergency,p_ins_provider,p_ins_number,p_allergies,p_meds,p_diag,p_equip,p_mobility,p_careplan,p_notes,st.session_state.user, now_iso()))
                    conn.commit()
                    st.success("Patient saved")
                    st.experimental_rerun()

    st.markdown("---")
    st.write("Existing patients:")
    st.dataframe(patients_df)

    # Edit / delete
    with st.expander("Edit / Delete patient"):
        if patients_df.empty:
            st.info("No patients")
        else:
            sel = st.selectbox("Select patient", patients_df['id'].tolist())
            row = patients_df[patients_df['id']==sel].iloc[0]
            can_edit = (st.session_state.user_role == "admin") or (row.get("created_by") == st.session_state.user)
            if not can_edit:
                st.warning("Only admin or the creator can edit/delete this patient.")
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name", value=row['name'])
                dob_val = pd.to_datetime(row['dob'], errors='coerce')
                dob = st.date_input("DOB", value=dob_val.date() if pd.notna(dob_val) else date(1950,1,1), min_value=date(1900,1,1))
                gender = st.selectbox("Gender", ["Female","Male","Other","Prefer not to say"], index=0)
                phone = st.text_input("Phone", value=row['phone'])
            with col2:
                email = st.text_input("Email", value=row['email'])
                address = st.text_area("Address", value=row['address'])
                emergency = st.text_input("Emergency contact", value=row['emergency_contact'])
            meds = st.text_area("Medications", value=row['medications'])
            allergies = st.text_area("Allergies", value=row['allergies'])
            diagnosis = st.text_area("Diagnosis", value=row['diagnosis'])
            equipment = st.text_area("Equipment", value=row['equipment_required'])
            mobility = st.selectbox("Mobility", ["Independent","Assisted","Wheelchair","Bedbound"], index=0)
            careplan = st.text_area("Care plan", value=row['care_plan'])
            notes = st.text_area("Notes", value=row['notes'])
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save changes") and can_edit:
                    cur = conn.cursor()
                    cur.execute("""UPDATE patients SET name=?,dob=?,gender=?,phone=?,email=?,address=?,emergency_contact=?,insurance_provider=?,insurance_number=?,allergies=?,medications=?,diagnosis=?,equipment_required=?,mobility=?,care_plan=?,notes=? WHERE id=?""",
                                (name,dob.isoformat(),gender,phone,email,address,emergency,row.get('insurance_provider'),row.get('insurance_number'),allergies,meds,diagnosis,equipment,mobility,careplan,notes,sel))
                    conn.commit()
                    st.success("Patient updated")
                    st.experimental_rerun()
            with col2:
                if st.button("Delete patient") and can_edit:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM patients WHERE id=?", (sel,))
                    conn.commit()
                    st.success("Patient deleted")
                    st.experimental_rerun()

    render_footer()

# ---------- Staff ----------
elif choice == "Staff":
    st.subheader("Manage Staff")
    staff_df = read_table("staff")

    with st.expander("Add staff member"):
        with st.form("add_staff_form", clear_on_submit=True):
            s_id = st.text_input("Staff ID (unique)")
            s_name = st.text_input("Full name")
            s_role = st.selectbox("Role", STAFF_ROLES)
            s_license = st.text_input("License / registration number")
            s_specialties = st.text_input("Specialties (comma separated)")
            s_phone = st.text_input("Phone")
            s_email = st.text_input("Email")
            s_availability = st.text_area("Availability (e.g. Mon-Fri 08:00-16:00; Weekends off)")
            s_notes = st.text_area("Notes")
            submitted = st.form_submit_button("Add staff")
            if submitted:
                if not s_id.strip():
                    st.error("Staff ID required")
                else:
                    cur = conn.cursor()
                    cur.execute("""INSERT OR REPLACE INTO staff (id,name,role,license_number,specialties,phone,email,availability,notes,created_by,created_at)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                (s_id,s_name,s_role,s_license,s_specialties,s_phone,s_email,s_availability,s_notes,st.session_state.user, now_iso()))
                    conn.commit()
                    st.success("Staff saved")
                    st.experimental_rerun()

    st.markdown("---")
    st.dataframe(staff_df)

    with st.expander("Edit / Delete staff"):
        if staff_df.empty:
            st.info("No staff yet")
        else:
            sel = st.selectbox("Select staff", staff_df['id'].tolist())
            row = staff_df[staff_df['id']==sel].iloc[0]
            can_edit = (st.session_state.user_role == "admin") or (row.get("created_by") == st.session_state.user)
            if not can_edit:
                st.warning("Only admin or creator can edit/delete this staff record.")
            name = st.text_input("Name", value=row['name'])
            role = st.selectbox("Role", STAFF_ROLES, index=STAFF_ROLES.index(row['role']) if row['role'] in STAFF_ROLES else 0)
            license_num = st.text_input("License", value=row['license_number'])
            specialties = st.text_input("Specialties", value=row['specialties'])
            phone = st.text_input("Phone", value=row['phone'])
            email = st.text_input("Email", value=row['email'])
            availability = st.text_area("Availability", value=row['availability'])
            notes = st.text_area("Notes", value=row['notes'])
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save staff") and can_edit:
                    cur = conn.cursor()
                    cur.execute("""UPDATE staff SET name=?,role=?,license_number=?,specialties=?,phone=?,email=?,availability=?,notes=? WHERE id=?""",
                                (name,role,license_num,specialties,phone,email,availability,notes,sel))
                    conn.commit()
                    st.success("Saved")
                    st.experimental_rerun()
            with col2:
                if st.button("Delete staff") and can_edit:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM staff WHERE id=?", (sel,))
                    conn.commit()
                    st.success("Deleted")
                    st.experimental_rerun()

    render_footer()

# ---------- Schedule ----------
elif choice == "Schedule":
    st.subheader("Scheduling & Visits")
    patients_df = read_table("patients")
    staff_df = read_table("staff")
    schedule_df = read_table("schedule")

    col1, col2 = st.columns([2,1])
    with col1:
        st.markdown("### Create visit")
        if patients_df.empty:
            st.warning("Add patients first")
        if staff_df.empty:
            st.warning("Add staff first")

        with st.form("create_visit_form", clear_on_submit=True):
            patient_sel = st.selectbox("Patient", patients_df['id'].tolist() if len(patients_df)>0 else [], key="visit_patient")
            staff_sel = st.selectbox("Assign staff", staff_df['id'].tolist() if len(staff_df)>0 else [], key="visit_staff")
            visit_date = st.date_input("Date", value=date.today())
            start = st.time_input("Start", value=dtime(hour=9,minute=0))
            end = st.time_input("End", value=(datetime.combine(date.today(), start) + timedelta(minutes=60)).time())
            visit_type = st.selectbox("Visit type", ["Home visit","Telehealth","Wound care","Medication administration","Physiotherapy","Respiratory therapy","Assessment","Other"]) 
            priority = st.selectbox("Priority", ["Low","Normal","High","Critical"])
            notes = st.text_area("Notes / visit plan")
            submitted = st.form_submit_button("Create visit")
            if submitted:
                if not patient_sel or not staff_sel:
                    st.error("Select patient and staff")
                else:
                    visit_id = make_visit_id()
                    duration = int((datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).seconds / 60)
                    cur = conn.cursor()
                    cur.execute("""INSERT OR REPLACE INTO schedule (visit_id,patient_id,staff_id,date,start_time,end_time,visit_type,duration_minutes,priority,notes,created_by,created_at) 
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (visit_id,patient_sel,staff_sel,visit_date.isoformat(),start.strftime("%H:%M"),end.strftime("%H:%M"),visit_type,duration,priority,notes,st.session_state.user, now_iso()))
                    conn.commit()
                    st.success(f"Visit {visit_id} created")
                    st.experimental_rerun()

    with col2:
        st.markdown("### View / Manage visits")
        if schedule_df.empty:
            st.info("No visits scheduled yet.")
        else:
            sel_visit = st.selectbox("Select visit", schedule_df['visit_id'].tolist())
            row = schedule_df[schedule_df['visit_id']==sel_visit].iloc[0]
            st.write(row.to_dict())
            can_edit = (st.session_state.user_role == "admin") or (row.get("created_by") == st.session_state.user)
            if can_edit:
                if st.button("Delete visit"):
                    cur = conn.cursor()
                    cur.execute("DELETE FROM schedule WHERE visit_id=?", (sel_visit,))
                    conn.commit()
                    st.success("Visit deleted")
                    st.experimental_rerun()
            else:
                st.info("Only admin or creator can delete this visit.")

    render_footer()

# ---------- Analytics ----------
elif choice == "Analytics":
    st.subheader("Analytics")
    patients_df = read_table("patients")
    schedule_df = read_table("schedule")

    st.markdown("### Patients by age group")
    if not patients_df.empty:
        dfp = patients_df.copy()
        dfp['dob_dt'] = pd.to_datetime(dfp['dob'], errors='coerce')
        dfp['age'] = ((pd.Timestamp(date.today()) - dfp['dob_dt']).dt.days // 365).fillna(0).astype(int)
        bins = pd.cut(dfp['age'], bins=[-1,0,1,5,12,18,40,65,200],
                      labels=["<1","1-5","6-12","13-18","19-40","41-65","66+"])
        age_count = bins.value_counts().sort_index().reset_index()
        age_count.columns = ['age_group','count']
        st.altair_chart(alt.Chart(age_count).mark_bar(color=ACCENT).encode(x='age_group', y='count'), use_container_width=True)
    else:
        st.info("Add patients to see analytics.")

    st.markdown("### Staff workload (visits per staff)")
    if not schedule_df.empty:
        w = schedule_df['staff_id'].value_counts().reset_index()
        w.columns = ['staff_id','visits']
        st.altair_chart(alt.Chart(w).mark_bar(color="#66c2a5").encode(x='staff_id', y='visits'), use_container_width=True)
    else:
        st.info("No schedule data")
    render_footer()

# ---------- Emergency ----------
elif choice == "Emergency":
    st.subheader("Emergency")
    patients_df = read_table("patients")
    if len(patients_df):
        sel = st.selectbox("Patient", patients_df['id'].tolist())
        row = patients_df[patients_df['id']==sel].iloc[0]
        st.write(row.to_dict())
        if st.button("Call emergency contact (mock)"):
            st.info("Calling: " + str(row['emergency_contact']))
    else:
        st.info("No patients yet.")
    render_footer()

# ---------- Settings & User management ----------
elif choice == "Settings":
    st.subheader("Settings & User Management")
    st.write(f"Logged in as **{st.session_state.user}** ({st.session_state.user_role})")

    # Change own password
    with st.expander("Change your password", expanded=True):
        old = st.text_input("Current password", type="password", key="old_pw")
        new = st.text_input("New password", type="password", key="new_pw")
        new2 = st.text_input("Confirm new password", type="password", key="new_pw2")
        if st.button("Change password"):
            if not old or not new or new != new2:
                st.error("Ensure fields are filled and new passwords match.")
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
        st.markdown("### Admin: User management")
        users_df = read_table("users")
        st.dataframe(users_df[['username','role','created_at']] if not users_df.empty else pd.DataFrame())
        with st.expander("Create new user"):
            u_name = st.text_input("Username")
            u_role = st.selectbox("Role", ["admin","doctor","nurse","staff","other"])
            u_pw = st.text_input("Password", type="password")
            if st.button("Create user"):
                if not u_name or not u_pw:
                    st.error("Username and password required")
                else:
                    cur = conn.cursor()
                    cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                                (u_name, hash_pw(u_pw), u_role, now_iso()))
                    conn.commit()
                    st.success("User created")
                    st.experimental_rerun()
        with st.expander("Reset user password"):
            users = read_table("users")
            if not users.empty:
                sel = st.selectbox("Select user", users['username'].tolist())
                new_pw = st.text_input("New password for selected user", type="password", key="reset_pw")
                if st.button("Reset password"):
                    if not new_pw:
                        st.error("Enter a password")
                    else:
                        cur = conn.cursor()
                        cur.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_pw(new_pw), sel))
                        conn.commit()
                        st.success("Password reset")
            else:
                st.info("No users found")

    render_footer()

# ---------- Export & Backup ----------
elif choice == "Export & Backup":
    st.subheader("Export & Backup")
    patients_df = read_table("patients")
    staff_df = read_table("staff")
    schedule_df = read_table("schedule")

    st.markdown("### Export data")
    c1, c2, c3 = st.columns(3)
    with c1:
        csv_pat = df_to_csv_bytes(patients_df) if not patients_df.empty else b""
        st.download_button("Download Patients CSV", data=csv_pat, file_name="patients.csv", mime="text/csv")
        csv_staff = df_to_csv_bytes(staff_df) if not staff_df.empty else b""
        st.download_button("Download Staff CSV", data=csv_staff, file_name="staff.csv", mime="text/csv")
        csv_sched = df_to_csv_bytes(schedule_df) if not schedule_df.empty else b""
        st.download_button("Download Schedule CSV", data=csv_sched, file_name="schedule.csv", mime="text/csv")
    with c2:
        excel_bytes = to_excel_bytes({"patients":patients_df, "staff":staff_df, "schedule":schedule_df})
        st.download_button("Download Excel (all)", data=excel_bytes, file_name="homecare_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c3:
        charts = {}
        try:
            if not patients_df.empty:
                dfp = patients_df.copy()
                dfp['dob_dt'] = pd.to_datetime(dfp['dob'], errors='coerce')
                dfp['age'] = ((pd.Timestamp(date.today()) - dfp['dob_dt']).dt.days // 365).fillna(0).astype(int)
                bins = pd.cut(dfp['age'], bins=[-1,0,1,5,12,18,40,65,200],
                              labels=["<1","1-5","6-12","13-18","19-40","41-65","66+"])
                age_count = bins.value_counts().sort_index()
                fig, ax = plt.subplots(figsize=(6,3))
                age_count.plot(kind='bar', color=ACCENT, ax=ax)
                ax.set_title("Patients by age group")
                ax.set_xlabel("")
                png = _save_png_from_matplotlib(fig)
                charts["Patients by age group"] = png
                plt.close(fig)
        except Exception:
            pass
        word_bytes = create_word_report(patients_df, staff_df, schedule_df, charts=charts if charts else None)
        st.download_button("Download Word report", data=word_bytes, file_name="homecare_report.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    st.markdown("---")
    st.write("Backup: download underlying SQLite DB")
    try:
        with open(DB_PATH, "rb") as f:
            db_bytes = f.read()
            st.download_button("Download DB file", data=db_bytes, file_name=DB_PATH, mime="application/x-sqlite3")
    except Exception as e:
        st.error("Could not read DB file: " + str(e))

    render_footer()

# ---------- Logout ----------
elif choice == "Logout":
    st.subheader("Logout")
    st.write(f"Logged in as **{st.session_state.user}** ({st.session_state.user_role})")
    if st.button("Logout"):
        logout_user()
        st.success("Logged out")
        st.experimental_rerun()

# End of file
