# app.py
# Smart Homecare Scheduler (Streamlit App) - Fixed save issues
# All Rights Reserved © Dr. Yousra Abdelatti

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, time as dtime, timedelta
from io import BytesIO
import altair as alt
import hashlib
from docx import Document
from docx.shared import Inches
import matplotlib.pyplot as plt
import tempfile
import os

# ---------------------------
# Configuration
# ---------------------------
DB_PATH = "homecare_scheduler.db"
APP_TITLE = "Smart Homecare Scheduler (24/7)"
RELAXING_BG = "#E8F6F3"
ACCENT = "#5DADE2"
STAFF_ROLES = ["Specialist", "GP", "Nurse", "RT", "PT", "Care Giver"]

# ---------------------------
# DB helpers (open/close per operation)
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def db_commit_and_close(conn):
    try:
        conn.commit()
    finally:
        conn.close()

# ---------------------------
# Hash & time helpers
# ---------------------------
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def now_iso() -> str:
    return datetime.utcnow().isoformat()

# ---------------------------
# Initialize DB (fresh mode)
# ---------------------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            role TEXT,
            created_at TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY,
            name TEXT,
            dob TEXT,
            gender TEXT,
            phone TEXT,
            address TEXT,
            emergency_contact TEXT,
            diagnosis TEXT,
            pmh TEXT,
            allergies TEXT,
            medications TEXT,
            physician TEXT,
            care_type TEXT,
            care_frequency TEXT,
            care_needs TEXT,
            mobility TEXT,
            cognition TEXT,
            nutrition TEXT,
            psychosocial TEXT,
            notes TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            id TEXT PRIMARY KEY,
            name TEXT,
            role TEXT,
            phone TEXT,
            email TEXT,
            availability TEXT,
            notes TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')

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

    cur.execute('''
        CREATE TABLE IF NOT EXISTS vitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            date TEXT,
            bp TEXT,
            hr TEXT,
            temp TEXT,
            resp TEXT,
            o2sat TEXT,
            weight TEXT,
            notes TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS visit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            date TEXT,
            caregiver TEXT,
            visit_type TEXT,
            services TEXT,
            response TEXT,
            signature TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS extra_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT,
            field_name TEXT,
            field_order INTEGER
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS extra_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT,
            record_id TEXT,
            field_id INTEGER,
            value TEXT
        )
    ''')

    # seed demo users if none
    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                    ("admin", hash_pw("1234"), "admin", now_iso()))
        cur.execute("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                    ("doctor", hash_pw("abcd"), "doctor", now_iso()))

    db_commit_and_close(conn)

# Initialize DB
init_db()

# ---------------------------
# Read helpers (no caching; always fresh)
# ---------------------------
def read_table(name: str) -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {name}", conn)
        return df
    finally:
        conn.close()

def make_visit_id() -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM schedule")
    c = cur.fetchone()["c"]
    conn.close()
    return f"V{c+1:05d}"

# ---------------------------
# CSS
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
    .login-bottom {{ text-align:center; margin-top: 1rem; }}
    .footer {{ padding:12px 0; text-align:center; font-weight:bold; color:purple; }}
    </style>
    """, unsafe_allow_html=True)

def render_footer():
    st.markdown("---")
    st.markdown("<div class='footer'>All Rights Reserved © Dr. Yousra Abdelatti</div>", unsafe_allow_html=True)

inject_css()

# ---------------------------
# Authentication & session init
# ---------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None

def login_user(username: str, password: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if row and hash_pw(password) == row[0]:
        st.session_state.logged_in = True
        st.session_state.user = username
        st.session_state.role = row[1]
        return True
    return False

def logout_user():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None

# ---------------------------
# Extra fields helpers (admin-managed)
# ---------------------------
def get_extra_fields(entity: str = "patients"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, field_name, field_order FROM extra_fields WHERE entity = ? ORDER BY field_order ASC, id ASC", (entity,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_extra_field(entity: str, field_name: str, order: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO extra_fields (entity, field_name, field_order) VALUES (?,?,?)", (entity, field_name, order))
    db_commit_and_close(conn)

def remove_extra_field(field_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM extra_values WHERE field_id = ?", (field_id,))
    cur.execute("DELETE FROM extra_fields WHERE id = ?", (field_id,))
    db_commit_and_close(conn)

def reorder_extra_fields(entity: str, ordered_ids: list):
    conn = get_conn()
    cur = conn.cursor()
    for idx, fid in enumerate(ordered_ids):
        cur.execute("UPDATE extra_fields SET field_order = ? WHERE id = ?", (idx, fid))
    db_commit_and_close(conn)

def upsert_extra_value(entity: str, record_id: str, field_id: int, value: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM extra_values WHERE entity=? AND record_id=? AND field_id=?", (entity, record_id, field_id))
    r = cur.fetchone()
    if r:
        cur.execute("UPDATE extra_values SET value=? WHERE id=?", (value, r["id"]))
    else:
        cur.execute("INSERT INTO extra_values (entity, record_id, field_id, value) VALUES (?,?,?,?)", (entity, record_id, field_id, value))
    db_commit_and_close(conn)

def get_extra_values_for_record(entity: str, record_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ef.id as field_id, ef.field_name, ev.value
        FROM extra_fields ef
        LEFT JOIN extra_values ev ON ev.field_id = ef.id AND ev.entity = ef.entity AND ev.record_id = ?
        WHERE ef.entity = ?
        ORDER BY ef.field_order ASC, ef.id ASC
    """, (record_id, entity))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------------------------
# Export helpers
# ---------------------------
def to_excel_bytes(dfs: dict) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in dfs.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    output.seek(0)
    return output.getvalue()

def create_word_report(patients_df, staff_df, schedule_df, charts_png: dict = None) -> bytes:
    doc = Document()
    doc.add_heading(APP_TITLE, level=1)
    doc.add_paragraph("Report generated: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    for title, df in [("Patients", patients_df), ("Staff", staff_df), ("Schedule", schedule_df)]:
        doc.add_heading(title, level=2)
        if not df.empty:
            table = doc.add_table(rows=1, cols=len(df.columns))
            hdr = table.rows[0].cells
            for i, col in enumerate(df.columns):
                hdr[i].text = str(col)
            for _, r in df.iterrows():
                cells = table.add_row().cells
                for i, col in enumerate(df.columns):
                    val = r[col]
                    cells[i].text = "" if pd.isna(val) else str(val)
        else:
            doc.add_paragraph("No data")

    if charts_png:
        for title, png in charts_png.items():
            doc.add_page_break()
            doc.add_heading(title, level=2)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(png)
                tmp.flush()
                doc.add_picture(tmp.name, width=Inches(6))
                tmp.close()
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass

    f = BytesIO()
    doc.save(f)
    f.seek(0)
    return f.getvalue()

# ---------------------------
# Page config + login UI
# ---------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")
if not st.session_state.get("logged_in", False):
    st.markdown('<div class="big-title">Smart Homecare Scheduler — Login</div>', unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1])
    with col1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pw")
        if st.button("Login"):
            ok = login_user(username, password)
            if ok:
                st.success(f"Welcome back, {st.session_state.user} ({st.session_state.role})")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    with col2:
        st.write("Demo accounts: admin / 1234  •  doctor / abcd")
        st.write("If you don't have an account ask the administrator to create one.")
    st.markdown("<div class='login-bottom'><span style='font-weight:bold; color:purple;'>All Rights Reserved © Dr. Yousra Abdelatti</span></div>", unsafe_allow_html=True)
    st.stop()

# ---------------------------
# Main menu
# ---------------------------
st.sidebar.title("Menu")
menu = ["Dashboard", "Patients", "Staff", "Schedule", "Analytics", "Emergency", "Settings", "Export & Backup", "Logout"]
choice = st.sidebar.selectbox("Go to", menu)

st.markdown(f"<div class='big-title'>{APP_TITLE}</div>", unsafe_allow_html=True)

# ---------- DASHBOARD ----------
if choice == "Dashboard":
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
        upcoming = schedule_df[(schedule_df['date_dt'] >= pd.Timestamp(date.today())) & (schedule_df['date_dt'] <= pd.Timestamp(date.today() + timedelta(days=30)))]
        upcoming = upcoming.sort_values(['date', 'start_time']).head(100)
        st.dataframe(upcoming[['visit_id', 'patient_id', 'staff_id', 'date', 'start_time', 'end_time', 'visit_type', 'priority']])
    else:
        st.info("No visits scheduled yet.")

    # Quick analytics
    st.markdown("### Quick analytics")
    col1, col2 = st.columns(2)
    with col1:
        if not patients_df.empty:
            dfp = patients_df.copy()
            dfp['dob_dt'] = pd.to_datetime(dfp['dob'], errors='coerce')
            dfp['age'] = ((pd.Timestamp(date.today()) - dfp['dob_dt']).dt.days // 365).fillna(0).astype(int)
            age_bins = pd.cut(dfp['age'], bins=[-1, 0, 1, 5, 12, 18, 40, 65, 200], labels=["<1", "1-5", "6-12", "13-18", "19-40", "41-65", "66-200"])
            age_count = age_bins.value_counts().sort_index().reset_index()
            age_count.columns = ['age_group', 'count']
            st.altair_chart(alt.Chart(age_count).mark_bar(color=ACCENT).encode(x='age_group', y='count').properties(height=240), use_container_width=True)
        else:
            st.info("Add patients to see age distribution.")
    with col2:
        if not schedule_df.empty:
            vtypes = schedule_df['visit_type'].fillna("Unknown").value_counts().reset_index()
            vtypes.columns = ['visit_type', 'count']
            st.altair_chart(alt.Chart(vtypes).mark_arc().encode(theta='count', color='visit_type').properties(height=240), use_container_width=True)
        else:
            st.info("No visits to show distribution.")
    render_footer()

# ---------- PATIENTS ----------
elif choice == "Patients":
    st.subheader("🏥 Home Care Patient File")

    patients_df = read_table("patients")
    custom_fields = get_extra_fields("patients")

    with st.expander("Add New Patient (full file)", expanded=True):
        with st.form("add_patient_form", clear_on_submit=True):
            p_id = st.text_input("Patient ID (unique)")
            p_name = st.text_input("Name")
            p_dob = st.date_input("Date of Birth", min_value=date(1900, 1, 1))
            p_gender = st.selectbox("Gender", ["Female", "Male", "Other", "Prefer not to say"])
            p_address = st.text_area("Address")
            p_phone = st.text_input("Contact Number")
            p_emergency = st.text_input("Emergency Contact")

            p_diagnosis = st.text_area("Primary Diagnosis")
            p_pmh = st.text_area("Past Medical History")
            p_allergies = st.text_area("Allergies")
            p_medications = st.text_area("Medications")
            p_physician = st.text_input("Physician")

            p_care_type = st.text_input("Type of Care")
            p_care_frequency = st.text_input("Frequency")
            p_care_needs = st.text_area("Specific Needs")

            p_mobility = st.selectbox("Mobility", ["Independent", "Assisted", "Wheelchair", "Bedbound"])
            p_cognition = st.text_area("Cognition")
            p_nutrition = st.text_area("Nutrition")
            p_psychosocial = st.text_area("Psychosocial")

            custom_values = {}
            if custom_fields:
                st.markdown("### Custom Sections (Admin)")
                for cf in custom_fields:
                    key = f"custom_{cf['id']}"
                    custom_values[key] = st.text_input(cf['field_name'], key=key)

            p_notes = st.text_area("Notes / Social History")
            submitted = st.form_submit_button("Save Patient")

            if submitted:
                if not p_id or not p_name:
                    st.error("Patient ID and Name are required.")
                else:
                    conn_write = get_conn()
                    cur = conn_write.cursor()
                    cur.execute("""
                        INSERT OR REPLACE INTO patients
                        (id,name,dob,gender,phone,address,emergency_contact,diagnosis,pmh,allergies,medications,physician,care_type,care_frequency,care_needs,mobility,cognition,nutrition,psychosocial,notes,created_by,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        p_id, p_name, p_dob.isoformat(), p_gender, p_phone, p_address, p_emergency,
                        p_diagnosis, p_pmh, p_allergies, p_medications, p_physician,
                        p_care_type, p_care_frequency, p_care_needs, p_mobility, p_cognition,
                        p_nutrition, p_psychosocial, p_notes, st.session_state.user, now_iso()
                    ))
                    db_commit_and_close(conn_write)

                    # Save custom fields values
                    for cf in custom_fields:
                        key = f"custom_{cf['id']}"
                        val = custom_values.get(key)
                        if val:
                            upsert_extra_value("patients", p_id, cf['id'], val)

                    st.success("Patient saved")
                    st.experimental_rerun()

    st.markdown("---")
    st.write("Existing patients (table):")
    st.dataframe(patients_df)

    # Vitals
    st.markdown("### Vital Signs Record (add / view)")
    vitals_df = read_table("vitals")
    if not patients_df.empty:
        with st.form("add_vital_form", clear_on_submit=True):
            sel_pid = st.selectbox("Patient", patients_df['id'].tolist(), key="vital_patient_select")
            vs_date = st.date_input("Date", value=date.today())
            vs_bp = st.text_input("BP")
            vs_hr = st.text_input("HR")
            vs_temp = st.text_input("Temp")
            vs_resp = st.text_input("Resp")
            vs_o2 = st.text_input("O2 Sat")
            vs_weight = st.text_input("Weight")
            vs_notes = st.text_area("Notes")
            if st.form_submit_button("Save vital"):
                conn_write = get_conn(); cur = conn_write.cursor()
                cur.execute("""
                    INSERT INTO vitals (patient_id,date,bp,hr,temp,resp,o2sat,weight,notes)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (sel_pid, vs_date.isoformat(), vs_bp, vs_hr, vs_temp, vs_resp, vs_o2, vs_weight, vs_notes))
                db_commit_and_close(conn_write)
                st.success("Vital saved")
                st.experimental_rerun()
        st.dataframe(vitals_df)
    else:
        st.info("Add patients first to create vitals records.")

    # Visit log
    st.markdown("### Visit Log (add / view)")
    visit_log_df = read_table("visit_log")
    if not patients_df.empty:
        with st.form("add_visitlog_form", clear_on_submit=True):
            sel_pid2 = st.selectbox("Patient", patients_df['id'].tolist(), key="log_patient_select")
            vl_date = st.date_input("Date", value=date.today())
            vl_caregiver = st.text_input("Caregiver")
            vl_type = st.text_input("Visit Type")
            vl_services = st.text_area("Services Provided")
            vl_response = st.text_area("Patient Response")
            vl_signature = st.text_input("Signature")
            if st.form_submit_button("Save visit log"):
                conn_write = get_conn(); cur = conn_write.cursor()
                cur.execute("""
                    INSERT INTO visit_log (patient_id,date,caregiver,visit_type,services,response,signature)
                    VALUES (?,?,?,?,?,?,?)
                """, (sel_pid2, vl_date.isoformat(), vl_caregiver, vl_type, vl_services, vl_response, vl_signature))
                db_commit_and_close(conn_write)
                st.success("Visit log saved")
                st.experimental_rerun()
        st.dataframe(visit_log_df)
    else:
        st.info("Add patients first to log visits.")

    render_footer()

# ---------- STAFF ----------
elif choice == "Staff":
    st.subheader("Manage Staff")
    staff_df = read_table("staff")

    with st.form("add_staff_form", clear_on_submit=True):
        s_id = st.text_input("Staff ID (unique)")
        s_name = st.text_input("Full name")
        s_role = st.selectbox("Role", STAFF_ROLES)
        s_phone = st.text_input("Phone")
        s_email = st.text_input("Email")
        s_availability = st.text_area("Availability (e.g. Mon-Fri 08:00-16:00)")
        s_notes = st.text_area("Notes")
        if st.form_submit_button("Save staff"):
            if not s_id or not s_name:
                st.error("Staff ID and name required")
            else:
                conn_write = get_conn(); cur = conn_write.cursor()
                cur.execute("""
                    INSERT OR REPLACE INTO staff (id,name,role,phone,email,availability,notes,created_by,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (s_id, s_name, s_role, s_phone, s_email, s_availability, s_notes, st.session_state.user, now_iso()))
                db_commit_and_close(conn_write)
                st.success("Staff saved")
                st.experimental_rerun()

    st.markdown("---")
    st.write("Existing staff:")
    st.dataframe(staff_df)
    render_footer()

# ---------- SCHEDULE ----------
elif choice == "Schedule":
    st.subheader("Scheduling & Visits")
    patients_df = read_table("patients")
    staff_df = read_table("staff")
    schedule_df = read_table("schedule")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("### Create visit")
        if patients_df.empty:
            st.warning("Add patients first")
        if staff_df.empty:
            st.warning("Add staff first")

        with st.form("create_visit_form", clear_on_submit=True):
            patient_sel = st.selectbox("Patient", patients_df['id'].tolist() if len(patients_df) > 0 else [], key="sch_patient")
            staff_sel = st.selectbox("Assign staff", staff_df['id'].tolist() if len(staff_df) > 0 else [], key="sch_staff")
            visit_date = st.date_input("Date", value=date.today())
            start = st.time_input("Start", value=dtime(hour=9, minute=0))
            end = st.time_input("End", value=dtime(hour=10, minute=0))
            visit_type = st.selectbox("Visit type", ["Home visit", "Telehealth", "Wound care", "Medication administration", "Physiotherapy", "Respiratory therapy", "Assessment", "Other"])
            priority = st.selectbox("Priority", ["Low", "Normal", "High", "Critical"])
            notes = st.text_area("Notes / visit plan")
            if st.form_submit_button("Create visit"):
                if not patient_sel or not staff_sel:
                    st.error("Select patient and staff")
                else:
                    visit_id = make_visit_id()
                    duration = int((datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).seconds / 60)
                    conn_write = get_conn(); cur = conn_write.cursor()
                    cur.execute("""
                        INSERT OR REPLACE INTO schedule (visit_id,patient_id,staff_id,date,start_time,end_time,visit_type,duration_minutes,priority,notes,created_by,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (visit_id, patient_sel, staff_sel, visit_date.isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M"), visit_type, duration, priority, notes, st.session_state.user, now_iso()))
                    db_commit_and_close(conn_write)
                    st.success(f"Visit {visit_id} created")
                    st.experimental_rerun()

    with col2:
        st.markdown("### View / Manage visits")
        if schedule_df.empty:
            st.info("No visits scheduled yet.")
        else:
            sel_visit = st.selectbox("Select visit", schedule_df['visit_id'].tolist())
            row = schedule_df[schedule_df['visit_id'] == sel_visit].iloc[0]
            st.write(row.to_dict())
            can_edit = (st.session_state.role == "admin") or (row.get("created_by") == st.session_state.user)
            if can_edit:
                if st.button("Delete visit"):
                    conn_write = get_conn(); cur = conn_write.cursor()
                    cur.execute("DELETE FROM schedule WHERE visit_id = ?", (sel_visit,))
                    db_commit_and_close(conn_write)
                    st.success("Visit deleted")
                    st.experimental_rerun()
            else:
                st.info("Only admin or creator can delete this visit.")
    render_footer()

# ---------- ANALYTICS ----------
elif choice == "Analytics":
    st.subheader("Analytics")
    patients_df = read_table("patients")
    schedule_df = read_table("schedule")

    st.markdown("### Patients by age group")
    if not patients_df.empty:
        patients_df['dob_dt'] = pd.to_datetime(patients_df['dob'], errors='coerce')
        patients_df['age'] = ((pd.Timestamp(date.today()) - patients_df['dob_dt']).dt.days // 365).fillna(0).astype(int)
        age_bins = pd.cut(patients_df['age'], bins=[-1, 0, 1, 18, 40, 65, 200], labels=["<1", "1-17", "18-39", "40-64", "65+"])
        age_count = age_bins.value_counts().sort_index().reset_index()
        age_count.columns = ['age_group', 'count']
        st.altair_chart(alt.Chart(age_count).mark_bar(color=ACCENT).encode(x='age_group', y='count'), use_container_width=True)
    else:
        st.info("No patient data")

    st.markdown("### Staff workload (visits per staff)")
    if not schedule_df.empty:
        w = schedule_df['staff_id'].value_counts().reset_index()
        w.columns = ['staff_id', 'visits']
        st.altair_chart(alt.Chart(w).mark_bar(color="#66c2a5").encode(x='staff_id', y='visits'), use_container_width=True)
    else:
        st.info("No schedule data")

    render_footer()

# ---------- EMERGENCY ----------
elif choice == "Emergency":
    st.subheader("Emergency")
    st.warning("This panel can be connected to SMS/Call systems in production.")
    patients_df = read_table("patients")
    if not patients_df.empty:
        sel = st.selectbox("Patient", patients_df['id'].tolist())
        row = patients_df[patients_df['id'] == sel].iloc[0]
        st.write(row.to_dict())
        if st.button("Show emergency contact"):
            st.info("Emergency contact: " + str(row['emergency_contact']))
    else:
        st.info("No patients yet.")
    render_footer()

# ---------- SETTINGS ----------
elif choice == "Settings":
    st.subheader("Settings & User Management")
    st.write(f"Logged in as **{st.session_state.user}** ({st.session_state.role})")

    # Change password
    with st.expander("Change your password", expanded=True):
        old = st.text_input("Current password", type="password", key="old_pw")
        new = st.text_input("New password", type="password", key="new_pw")
        new2 = st.text_input("Confirm new password", type="password", key="new_pw2")
        if st.button("Change password"):
            if not old or not new or new != new2:
                st.error("Ensure fields are filled and new passwords match.")
            else:
                conn_write = get_conn(); cur = conn_write.cursor()
                cur.execute("SELECT password_hash FROM users WHERE username = ?", (st.session_state.user,))
                row = cur.fetchone()
                if row and hash_pw(old) == row[0]:
                    cur.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hash_pw(new), st.session_state.user))
                    db_commit_and_close(conn_write)
                    st.success("Password changed.")
                else:
                    conn_write.close()
                    st.error("Current password incorrect.")

    # Admin panels
    if st.session_state.role == "admin":
        st.markdown("### Admin: Manage users")
        users_df = read_table("users")
        if not users_df.empty:
            st.dataframe(users_df[['username', 'role', 'created_at']])
        else:
            st.info("No users found")

        with st.expander("Create new user"):
            u_name = st.text_input("Username", key="new_user_name")
            u_role = st.selectbox("Role", ["admin", "doctor", "nurse", "staff", "other"], key="new_user_role")
            u_pw = st.text_input("Password", type="password", key="new_user_pw")
            if st.button("Create user"):
                if not u_name or not u_pw:
                    st.error("Username and password required")
                else:
                    conn_write = get_conn(); cur = conn_write.cursor()
                    cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                                (u_name, hash_pw(u_pw), u_role, now_iso()))
                    db_commit_and_close(conn_write)
                    st.success("User created")
                    st.experimental_rerun()

        with st.expander("Reset user password"):
            users_df2 = read_table("users")
            if not users_df2.empty:
                sel = st.selectbox("Select user", users_df2['username'].tolist(), key="reset_user_select")
                new_pw = st.text_input("New password for selected user", type="password", key="reset_pw")
                if st.button("Reset password for selected user"):
                    if new_pw:
                        conn_write = get_conn(); cur = conn_write.cursor()
                        cur.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_pw(new_pw), sel))
                        db_commit_and_close(conn_write)
                        st.success("Password reset")
                    else:
                        st.error("Enter a password")
            else:
                st.info("No users found")

        # Manage custom patient sections
        st.markdown("### Admin: Manage custom patient sections")
        cur_fields = get_extra_fields("patients")
        if cur_fields:
            st.write("Existing custom sections:")
            for cf in cur_fields:
                st.write(f"{cf['id']}: {cf['field_name']} (order {cf['field_order']})")
        else:
            st.info("No custom sections yet.")

        with st.expander("Add custom patient section"):
            new_field_name = st.text_input("Field label (e.g. Drug history)", key="cf_name")
            new_order = st.number_input("Order (0 = top)", min_value=0, step=1, value=len(cur_fields), key="cf_order")
            if st.button("Add section", key="add_cf"):
                if new_field_name.strip() == "":
                    st.error("Provide a field label")
                else:
                    add_extra_field("patients", new_field_name.strip(), int(new_order))
                    st.success("Added")
                    st.experimental_rerun()

        with st.expander("Remove custom patient section"):
            if cur_fields:
                remove_sel = st.selectbox("Select section to remove", [f"{cf['id']}|{cf['field_name']}" for cf in cur_fields], key="remove_cf_select")
                if st.button("Remove selected section", key="remove_cf"):
                    fid = int(remove_sel.split("|")[0])
                    remove_extra_field(fid)
                    st.success("Removed")
                    st.experimental_rerun()
            else:
                st.info("No custom sections to remove")

        with st.expander("Reorder custom patient sections"):
            if cur_fields:
                ordered_input = st.text_input("Enter field ids in desired order, comma-separated (e.g. 3,1,2)", value=",".join(str(cf['id']) for cf in cur_fields), key="reorder_cf_input")
                if st.button("Apply new order", key="apply_reorder_cf"):
                    try:
                        ids = [int(x.strip()) for x in ordered_input.split(",") if x.strip()]
                        reorder_extra_fields("patients", ids)
                        st.success("Order updated")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error("Invalid input: " + str(e))
            else:
                st.info("No fields to reorder")

    render_footer()

# ---------- EXPORT & BACKUP ----------
elif choice == "Export & Backup":
    st.subheader("Export & Backup")
    patients_df = read_table("patients")
    staff_df = read_table("staff")
    schedule_df = read_table("schedule")

    c1, c2, c3 = st.columns(3)
    with c1:
        csv_pat = patients_df.to_csv(index=False).encode() if not patients_df.empty else b""
        st.download_button("Download Patients CSV", data=csv_pat, file_name="patients.csv", mime="text/csv")
        csv_staff = staff_df.to_csv(index=False).encode() if not staff_df.empty else b""
        st.download_button("Download Staff CSV", data=csv_staff, file_name="staff.csv", mime="text/csv")
    with c2:
        excel_bytes = to_excel_bytes({"patients": patients_df, "staff": staff_df, "schedule": schedule_df})
        st.download_button("Download Excel (all)", data=excel_bytes, file_name="homecare_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c3:
        charts = {}
        if not patients_df.empty:
            try:
                patients_df['dob_dt'] = pd.to_datetime(patients_df['dob'], errors='coerce')
                patients_df['age'] = ((pd.Timestamp(date.today()) - patients_df['dob_dt']).dt.days // 365).fillna(0).astype(int)
                age_bins = pd.cut(patients_df['age'], bins=[-1, 1, 18, 40, 65, 120], labels=["<1", "1-17", "18-39", "40-64", "65+"])
                age_count = age_bins.value_counts().sort_index().reset_index()
                age_count.columns = ['Age group', 'Count']
                fig, ax = plt.subplots()
                age_count.plot(kind="bar", x="Age group", y="Count", ax=ax, legend=False, color=ACCENT)
                buf = BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); charts["Patients by age group"] = buf.getvalue(); plt.close(fig)
            except Exception:
                pass
        if not schedule_df.empty:
            try:
                workload = schedule_df['staff_id'].value_counts().reset_index()
                workload.columns = ['Staff', 'Visits']
                fig, ax = plt.subplots()
                workload.plot(kind="bar", x="Staff", y="Visits", ax=ax, legend=False, color="#66c2a5")
                buf = BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); charts["Staff workload"] = buf.getvalue(); plt.close(fig)
            except Exception:
                pass

        word_bytes = create_word_report(patients_df, staff_df, schedule_df, charts_png=charts if charts else None)
        st.download_button("Download Word report (with charts)", data=word_bytes, file_name="homecare_report.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    # DB backup
    try:
        with open(DB_PATH, "rb") as f:
            db_bytes = f.read()
            st.download_button("Download DB file", data=db_bytes, file_name=DB_PATH, mime="application/x-sqlite3")
    except Exception as e:
        st.error("Could not read DB file: " + str(e))

    render_footer()

# ---------- LOGOUT ----------
elif choice == "Logout":
    logout_user()
    st.success("Logged out")
    st.experimental_rerun()

# fallback footer
else:
    render_footer()
