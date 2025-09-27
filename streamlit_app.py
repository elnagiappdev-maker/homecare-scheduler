# fullapp.py
# Smart Homecare Scheduler (Streamlit single-file app)
# All Rights Reserved © Dr. Yousra Abdelatti
#
# Single-file, production-friendly version with:
# - SQLite persistence + automatic schema migrations (adds missing columns safely)
# - Login/logout, roles (admin, doctor, staff, other)
# - Add / Edit / Delete Patients & Staff (IDs editable; cascades to related tables)
# - Schedule creation & management
# - Vitals & Visit Log
# - Admin: create/reset/delete users, manage custom patient sections (add/remove/reorder)
# - Exports: CSV, Excel, Word with charts (charts embedded as PNGs)
# - Analytics with downloadable PNGs
# - Admin-only privileges enforced
# - All Rights Reserved footer on login and app
#
# Requirements:
# pip install streamlit pandas openpyxl python-docx altair matplotlib

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
import typing

# ---------------------------
# Configuration
# ---------------------------
DB_PATH = "homecare_scheduler.db"
APP_TITLE = "Smart Homecare Scheduler (24/7)"
RELAXING_BG = "#E8F6F3"
ACCENT = "#5DADE2"

STAFF_ROLES = ["Specialist", "GP", "Nurse", "RT", "PT", "Care Giver"]

# ---------------------------
# DB / Migration helpers
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

def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols

def ensure_columns():
    """
    Create tables if missing and alter tables to add missing columns used by newer app versions.
    This allows safe upgrade without losing data.
    """
    conn = get_conn()
    cur = conn.cursor()

    # Core tables creation (only create if not exists)
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
            diagnosis TEXT,
            notes TEXT,
            recurring_rule TEXT,
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

    # extra_fields & extra_values for admin-managed dynamic fields
    cur.execute('''
        CREATE TABLE IF NOT EXISTS extra_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT,
            field_name TEXT,
            field_type TEXT,
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

    # Backward compatibility: ensure older DBs get missing columns
    # For patients (some fields may be missing)
    patient_expected = {
        "email": "TEXT",
        "insurance_provider": "TEXT",
        "insurance_number": "TEXT",
        "equipment_required": "TEXT",
        "care_plan": "TEXT"
    }
    for col, typ in patient_expected.items():
        if not column_exists(conn, "patients", col):
            try:
                cur.execute(f"ALTER TABLE patients ADD COLUMN {col} {typ}")
            except Exception:
                pass

    # For staff (some fields may be missing)
    staff_expected = {
        "license_number": "TEXT",
        "specialties": "TEXT",
        "availability": "TEXT"
    }
    for col, typ in staff_expected.items():
        if not column_exists(conn, "staff", col):
            try:
                cur.execute(f"ALTER TABLE staff ADD COLUMN {col} {typ}")
            except Exception:
                pass

    # For schedule (diagnosis, recurring_rule)
    schedule_expected = {
        "diagnosis": "TEXT",
        "recurring_rule": "TEXT"
    }
    for col, typ in schedule_expected.items():
        if not column_exists(conn, "schedule", col):
            try:
                cur.execute(f"ALTER TABLE schedule ADD COLUMN {col} {typ}")
            except Exception:
                pass

    # Seed default users if none
    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        now = datetime.utcnow().isoformat()
        cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                    ("admin", hashlib.sha256("1234".encode()).hexdigest(), "admin", now))
        cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                    ("doctor", hashlib.sha256("abcd".encode()).hexdigest(), "doctor", now))

    db_commit_and_close(conn)

# Ensure DB and columns exist on startup
ensure_columns()

# ---------------------------
# Utility helpers
# ---------------------------
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def now_iso() -> str:
    return datetime.utcnow().isoformat()

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
# Extra fields (admin-managed dynamic patient fields)
# ---------------------------
def get_extra_fields(entity: str = "patients"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, field_name, field_type, field_order FROM extra_fields WHERE entity = ? ORDER BY field_order ASC, id ASC", (entity,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_extra_field(entity: str, field_name: str, field_type: str = "text", order: int = 9999):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO extra_fields (entity, field_name, field_type, field_order) VALUES (?,?,?,?)", (entity, field_name, field_type, order))
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
# Exports
# ---------------------------
def to_excel_bytes(dfs: dict) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in dfs.items():
            try:
                df.to_excel(writer, sheet_name=name[:31], index=False)
            except Exception:
                # if df is not a dataframe
                pd.DataFrame(df).to_excel(writer, sheet_name=name[:31], index=False)
    output.seek(0)
    return output.getvalue()

def create_word_report(patients_df: pd.DataFrame, staff_df: pd.DataFrame, schedule_df: pd.DataFrame, charts_png: dict = None) -> bytes:
    doc = Document()
    doc.add_heading(APP_TITLE, level=1)
    doc.add_paragraph("Report generated: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    for title, df in [("Patients", patients_df), ("Staff", staff_df), ("Schedule", schedule_df)]:
        doc.add_heading(title, level=2)
        if df is None or df.empty:
            doc.add_paragraph("No data")
            continue
        # Create table
        cols = list(df.columns)
        table = doc.add_table(rows=1, cols=len(cols))
        hdr = table.rows[0].cells
        for i, c in enumerate(cols):
            hdr[i].text = str(c)
        for _, r in df.iterrows():
            row_cells = table.add_row().cells
            for i, c in enumerate(cols):
                val = r[c]
                row_cells[i].text = "" if pd.isna(val) else str(val)

    # Add charts as images if provided
    if charts_png:
        for title, img in charts_png.items():
            doc.add_page_break()
            doc.add_heading(title, level=2)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(img)
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
# Authentication & session
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
# Utility for editing primary IDs (cascade updates)
# ---------------------------
def change_patient_id(old_id: str, new_id: str):
    """
    Change patient primary key and cascade updates to schedule, vitals, visit_log, extra_values.
    """
    if not old_id or not new_id or old_id == new_id:
        return
    conn = get_conn()
    cur = conn.cursor()
    # Ensure new_id doesn't already exist
    cur.execute("SELECT 1 FROM patients WHERE id = ?", (new_id,))
    if cur.fetchone():
        conn.close()
        raise ValueError("New Patient ID already exists.")
    # Update patients row
    cur.execute("UPDATE patients SET id = ? WHERE id = ?", (new_id, old_id))
    # Update related tables
    cur.execute("UPDATE schedule SET patient_id = ? WHERE patient_id = ?", (new_id, old_id))
    cur.execute("UPDATE vitals SET patient_id = ? WHERE patient_id = ?", (new_id, old_id))
    cur.execute("UPDATE visit_log SET patient_id = ? WHERE patient_id = ?", (new_id, old_id))
    cur.execute("UPDATE extra_values SET record_id = ? WHERE record_id = ? AND entity = 'patients'", (new_id, old_id))
    db_commit_and_close(conn)

def change_staff_id(old_id: str, new_id: str):
    """
    Change staff primary key and cascade updates to schedule.
    """
    if not old_id or not new_id or old_id == new_id:
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM staff WHERE id = ?", (new_id,))
    if cur.fetchone():
        conn.close()
        raise ValueError("New Staff ID already exists.")
    cur.execute("UPDATE staff SET id = ? WHERE id = ?", (new_id, old_id))
    cur.execute("UPDATE schedule SET staff_id = ? WHERE staff_id = ?", (new_id, old_id))
    db_commit_and_close(conn)

# ---------------------------
# UI / CSS
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
    .login-bottom {{
        text-align:center;
        margin-top: 1rem;
        font-weight:bold;
        color:purple;
    }}
    </style>
    """, unsafe_allow_html=True)

def render_footer():
    st.markdown("---")
    st.markdown("<div class='footer'>All Rights Reserved © Dr. Yousra Abdelatti</div>", unsafe_allow_html=True)

inject_css()
st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")

# ---------------------------
# Login Page (single click)
# ---------------------------
if not st.session_state.get("logged_in", False):
    st.markdown('<div class="big-title">Smart Homecare Scheduler — Login</div>', unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pw")
        submitted = st.form_submit_button("Login")
        if submitted:
            ok = login_user(username, password)
            if ok:
                st.success(f"Welcome back, {st.session_state.user} ({st.session_state.role})")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    col1, col2 = st.columns([1, 1])
    with col2:
        st.write("Demo accounts: admin / 1234  •  doctor / abcd")
        st.write("If you don't have an account ask the administrator to create one.")
    st.markdown("<div class='login-bottom'>All Rights Reserved © Dr. Yousra Abdelatti</div>", unsafe_allow_html=True)
    st.stop()

# ---------------------------
# Main menu & header
# ---------------------------
st.sidebar.title("Menu")
menu = ["Dashboard", "Patients", "Staff", "Schedule", "Analytics", "Emergency", "Settings", "Export & Backup", "Logout"]
choice = st.sidebar.selectbox("Go to", menu)

st.markdown(f"<div class='big-title'>{APP_TITLE}</div>", unsafe_allow_html=True)

# ---------------------------
# DASHBOARD
# ---------------------------
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

# ---------------------------
# PATIENTS
# ---------------------------
elif choice == "Patients":
    st.subheader("🏥 Home Care Patient File")
    patients_df = read_table("patients")
    custom_fields = get_extra_fields("patients")

    with st.expander("Add New Patient (full file)", expanded=True):
        with st.form("add_patient_form", clear_on_submit=True):
            p_id = st.text_input("Patient ID (unique)", key="new_patient_id")
            p_name = st.text_input("Name", key="new_patient_name")
            p_dob = st.date_input("Date of Birth", min_value=date(1900, 1, 1), key="new_patient_dob")
            p_gender = st.selectbox("Gender", ["Female", "Male", "Other", "Prefer not to say"], key="new_patient_gender")
            p_email = st.text_input("Email", key="new_patient_email")
            p_address = st.text_area("Address", key="new_patient_address")
            p_phone = st.text_input("Contact Number", key="new_patient_phone")
            p_emergency = st.text_input("Emergency Contact", key="new_patient_emergency")

            p_diagnosis = st.text_area("Primary Diagnosis", key="new_patient_diag")
            p_pmh = st.text_area("Past Medical History", key="new_patient_pmh")
            p_allergies = st.text_area("Allergies", key="new_patient_allergies")
            p_medications = st.text_area("Medications", key="new_patient_meds")
            p_physician = st.text_input("Physician", key="new_patient_physician")

            p_ins_provider = st.text_input("Insurance Provider", key="new_patient_ins")
            p_ins_number = st.text_input("Insurance Number", key="new_patient_ins_n")
            p_equip = st.text_area("Equipment Required", key="new_patient_equip")

            p_care_plan = st.text_area("Care Plan", key="new_patient_careplan")
            p_mobility = st.selectbox("Mobility", ["Independent", "Assisted", "Wheelchair", "Bedbound"], key="new_patient_mobility")
            p_notes = st.text_area("Notes / Social History", key="new_patient_notes")

            # custom dynamic fields
            custom_values = {}
            if custom_fields:
                st.markdown("### Custom Sections (Admin)")
                for cf in custom_fields:
                    key = f"custom_{cf['id']}"
                    # type can be extended (text, longtext, number, date, etc.)
                    custom_values[key] = st.text_input(cf['field_name'], key=key)

            add_submitted = st.form_submit_button("Save Patient")
            if add_submitted:
                if not p_id or not p_name:
                    st.error("Patient ID and Name are required.")
                else:
                    conn_write = get_conn()
                    cur = conn_write.cursor()
                    cur.execute("""
                        INSERT OR REPLACE INTO patients
                        (id,name,dob,gender,phone,email,address,emergency_contact,insurance_provider,insurance_number,allergies,medications,diagnosis,equipment_required,mobility,care_plan,notes,created_by,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        p_id, p_name, p_dob.isoformat(), p_gender, p_phone, p_email, p_address, p_emergency,
                        p_ins_provider, p_ins_number, p_allergies, p_medications, p_diagnosis, p_equip, p_mobility, p_care_plan, p_notes, st.session_state.user, now_iso()
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

    # Edit / Delete patient (admin or creator)
    if not patients_df.empty:
        st.markdown("### Edit / Delete patient")
        sel = st.selectbox("Select patient to edit", patients_df['id'].tolist(), key="edit_patient_select")
        row = patients_df[patients_df['id'] == sel].iloc[0]
        can_edit = (st.session_state.role == "admin") or (row.get("created_by") == st.session_state.user)
        if not can_edit:
            st.info("You can view this patient's record but only the admin or the creator can edit/delete it.")
        # Include editable ID with cascade
        with st.form("edit_patient_form", clear_on_submit=False):
            new_id = st.text_input("Patient ID (editable)", value=row['id'], key="edit_patient_id")
            e_name = st.text_input("Name", value=row.get('name', ''), key="edit_patient_name")
            dob_val = pd.to_datetime(row.get('dob'), errors='coerce')
            e_dob = st.date_input("DOB", value=dob_val.date() if pd.notna(dob_val) else date.today(), key="edit_patient_dob")
            e_gender = st.selectbox("Gender", ["Female", "Male", "Other", "Prefer not to say"], index=0, key="edit_patient_gender")
            e_email = st.text_input("Email", value=row.get('email', ''), key="edit_patient_email")
            e_address = st.text_area("Address", value=row.get('address', ''), key="edit_patient_address")
            e_phone = st.text_input("Contact Number", value=row.get('phone', ''), key="edit_patient_phone")
            e_emergency = st.text_input("Emergency Contact", value=row.get('emergency_contact', ''), key="edit_patient_emergency")
            e_diagnosis = st.text_area("Primary Diagnosis", value=row.get('diagnosis', ''), key="edit_patient_diag")
            e_pmh = st.text_area("Past Medical History", value=row.get('pmh', ''), key="edit_patient_pmh")
            e_allergies = st.text_area("Allergies", value=row.get('allergies', ''), key="edit_patient_allergies")
            e_medications = st.text_area("Medications", value=row.get('medications', ''), key="edit_patient_meds")
            e_physician = st.text_input("Physician", value=row.get('physician', ''), key="edit_patient_physician")
            e_ins_provider = st.text_input("Insurance Provider", value=row.get('insurance_provider', ''), key="edit_patient_ins")
            e_ins_number = st.text_input("Insurance Number", value=row.get('insurance_number', ''), key="edit_patient_ins_n")
            e_equip = st.text_area("Equipment Required", value=row.get('equipment_required', ''), key="edit_patient_equip")
            e_care_plan = st.text_area("Care Plan", value=row.get('care_plan', ''), key="edit_patient_careplan")
            e_mobility = st.selectbox("Mobility", ["Independent", "Assisted", "Wheelchair", "Bedbound"], index=0, key="edit_patient_mobility")
            e_notes = st.text_area("Notes / Social History", value=row.get('notes', ''), key="edit_patient_notes")

            # custom dynamic fields: load existing values
            custom_vals_existing = get_extra_values_for_record("patients", sel)
            custom_inputs = {}
            for cf in custom_fields:
                existing = next((x for x in custom_vals_existing if x['field_id'] == cf['id']), None)
                custom_inputs[cf['id']] = st.text_input(cf['field_name'], value=existing.get('value','') if existing else '', key=f"edit_custom_{cf['id']}")

            submitted_edit = st.form_submit_button("Save changes")
            if submitted_edit:
                if not new_id or not e_name:
                    st.error("Patient ID and Name are required.")
                else:
                    try:
                        if new_id != sel:
                            # cascade change
                            change_patient_id(sel, new_id)
                            # after change, update row variable
                            sel_to_use = new_id
                        else:
                            sel_to_use = sel
                        conn_write = get_conn()
                        cur = conn_write.cursor()
                        cur.execute("""
                            UPDATE patients SET name=?, dob=?, gender=?, phone=?, email=?, address=?, emergency_contact=?, diagnosis=?, allergies=?, medications=?, physician=?, equipment_required=?, mobility=?, care_plan=?, notes=?
                            WHERE id=?
                        """, (e_name, e_dob.isoformat(), e_gender, e_phone, e_email, e_address, e_emergency, e_diagnosis, e_allergies, e_medications, e_physician, e_equip, e_mobility, e_care_plan, e_notes, sel_to_use))
                        db_commit_and_close(conn_write)
                        # save custom fields
                        for cf in custom_fields:
                            val = custom_inputs.get(cf['id'], '')
                            if val is not None:
                                upsert_extra_value("patients", sel_to_use, cf['id'], val)
                        st.success("Patient updated")
                        st.experimental_rerun()
                    except ValueError as ve:
                        st.error(str(ve))
                    except Exception as e:
                        st.error("Error updating patient: " + str(e))

            if st.button("Delete patient"):
                if can_edit:
                    conn_write = get_conn()
                    cur = conn_write.cursor()
                    cur.execute("DELETE FROM patients WHERE id = ?", (sel,))
                    # cascade delete related records
                    cur.execute("DELETE FROM schedule WHERE patient_id = ?", (sel,))
                    cur.execute("DELETE FROM vitals WHERE patient_id = ?", (sel,))
                    cur.execute("DELETE FROM visit_log WHERE patient_id = ?", (sel,))
                    cur.execute("DELETE FROM extra_values WHERE record_id = ? AND entity = 'patients'", (sel,))
                    db_commit_and_close(conn_write)
                    st.success("Patient and related records deleted")
                    st.experimental_rerun()
                else:
                    st.error("Only admin or creator can delete this patient.")

    # Vitals & visit log (forms included above)
    st.markdown("---")
    render_footer()

# ---------------------------
# STAFF
# ---------------------------
elif choice == "Staff":
    st.subheader("Manage Staff")
    staff_df = read_table("staff")

    with st.form("add_staff_form", clear_on_submit=True):
        s_id = st.text_input("Staff ID (unique)", key="new_staff_id")
        s_name = st.text_input("Full name", key="new_staff_name")
        s_role = st.selectbox("Role", STAFF_ROLES, key="new_staff_role")
        s_license = st.text_input("License / Registration Number", key="new_staff_license")
        s_specialties = st.text_input("Specialties (comma separated)", key="new_staff_specialties")
        s_phone = st.text_input("Phone", key="new_staff_phone")
        s_email = st.text_input("Email", key="new_staff_email")
        s_availability = st.text_area("Availability (e.g. Mon-Fri 08:00-16:00)", key="new_staff_avail")
        s_notes = st.text_area("Notes", key="new_staff_notes")
        add_staff_submitted = st.form_submit_button("Save staff")
        if add_staff_submitted:
            if not s_id or not s_name:
                st.error("Staff ID and name required")
            else:
                conn_write = get_conn()
                cur = conn_write.cursor()
                cur.execute("""
                    INSERT OR REPLACE INTO staff (id,name,role,license_number,specialties,phone,email,availability,notes,created_by,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (s_id, s_name, s_role, s_license, s_specialties, s_phone, s_email, s_availability, s_notes, st.session_state.user, now_iso()))
                db_commit_and_close(conn_write)
                st.success("Staff saved")
                st.experimental_rerun()

    st.markdown("---")
    st.write("Existing staff:")
    st.dataframe(staff_df)

    # Edit / Delete staff
    if not staff_df.empty:
        st.markdown("### Edit / Delete staff")
        sel_staff = st.selectbox("Select staff to edit", staff_df['id'].tolist(), key="edit_staff_select")
        row = staff_df[staff_df['id'] == sel_staff].iloc[0]
        can_edit_staff = (st.session_state.role == "admin") or (row.get("created_by") == st.session_state.user)
        if not can_edit_staff:
            st.info("You can view this staff record but only the admin or the creator can edit/delete it.")
        with st.form("edit_staff_form", clear_on_submit=False):
            new_staff_id = st.text_input("Staff ID (editable)", value=row['id'], key="edit_staff_id")
            es_name = st.text_input("Name", value=row.get('name',''), key="edit_staff_name")
            es_role = st.selectbox("Role", STAFF_ROLES, index=STAFF_ROLES.index(row['role']) if row.get('role') in STAFF_ROLES else 0, key="edit_staff_role")
            es_license = st.text_input("License/Registration", value=row.get('license_number',''), key="edit_staff_license")
            es_specialties = st.text_input("Specialties", value=row.get('specialties',''), key="edit_staff_specialties")
            es_phone = st.text_input("Phone", value=row.get('phone',''), key="edit_staff_phone")
            es_email = st.text_input("Email", value=row.get('email',''), key="edit_staff_email")
            es_avail = st.text_area("Availability", value=row.get('availability',''), key="edit_staff_avail")
            es_notes = st.text_area("Notes", value=row.get('notes',''), key="edit_staff_notes")

            save_staff_changes = st.form_submit_button("Save staff changes")
            if save_staff_changes:
                if not new_staff_id or not es_name:
                    st.error("Staff ID and Name required.")
                else:
                    try:
                        if new_staff_id != sel_staff:
                            change_staff_id(sel_staff, new_staff_id)
                            sel_to_use = new_staff_id
                        else:
                            sel_to_use = sel_staff
                        conn_write = get_conn()
                        cur = conn_write.cursor()
                        cur.execute("""
                            UPDATE staff SET name=?, role=?, license_number=?, specialties=?, phone=?, email=?, availability=?, notes=?
                            WHERE id=?
                        """, (es_name, es_role, es_license, es_specialties, es_phone, es_email, es_avail, es_notes, sel_to_use))
                        db_commit_and_close(conn_write)
                        st.success("Staff updated")
                        st.experimental_rerun()
                    except ValueError as ve:
                        st.error(str(ve))
                    except Exception as e:
                        st.error("Error updating staff: " + str(e))

            if st.button("Delete staff"):
                if can_edit_staff:
                    conn_write = get_conn()
                    cur = conn_write.cursor()
                    cur.execute("DELETE FROM staff WHERE id=?", (sel_staff,))
                    # optionally cascade schedule entries or mark them unassigned; here we keep them but remove staff link
                    cur.execute("UPDATE schedule SET staff_id = NULL WHERE staff_id = ?", (sel_staff,))
                    db_commit_and_close(conn_write)
                    st.success("Staff deleted (schedule entries unassigned)")
                    st.experimental_rerun()
                else:
                    st.error("Only admin or creator can delete this staff.")

    render_footer()

# ---------------------------
# SCHEDULE
# ---------------------------
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
            visit_date = st.date_input("Date", value=date.today(), key="sch_date")
            start = st.time_input("Start", value=dtime(hour=9, minute=0), key="sch_start")
            end = st.time_input("End", value=dtime(hour=10, minute=0), key="sch_end")
            visit_type = st.selectbox("Visit type", ["Home visit", "Telehealth", "Wound care", "Medication administration", "Physiotherapy", "Respiratory therapy", "Assessment", "Other"], key="sch_vtype")
            priority = st.selectbox("Priority", ["Low", "Normal", "High", "Critical"], key="sch_priority")
            notes = st.text_area("Notes / visit plan", key="sch_notes")
            create_visit_clicked = st.form_submit_button("Create visit")
            if create_visit_clicked:
                if not patient_sel or not staff_sel:
                    st.error("Select patient and staff")
                else:
                    visit_id = make_visit_id()
                    duration = int((datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).seconds / 60)
                    conn_write = get_conn()
                    cur = conn_write.cursor()
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
            sel_visit = st.selectbox("Select visit", schedule_df['visit_id'].tolist(), key="view_visit_select")
            row = schedule_df[schedule_df['visit_id'] == sel_visit].iloc[0]
            st.write(row.to_dict())
            can_edit = (st.session_state.role == "admin") or (row.get("created_by") == st.session_state.user)
            if can_edit:
                if st.button("Delete visit"):
                    conn_write = get_conn()
                    cur = conn_write.cursor()
                    cur.execute("DELETE FROM schedule WHERE visit_id = ?", (sel_visit,))
                    db_commit_and_close(conn_write)
                    st.success("Visit deleted")
                    st.experimental_rerun()
            else:
                st.info("Only admin or creator can delete this visit.")
    render_footer()

# ---------------------------
# ANALYTICS
# ---------------------------
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
        chart_age = alt.Chart(age_count).mark_bar(color=ACCENT).encode(x='age_group', y='count')
        st.altair_chart(chart_age, use_container_width=True)

        # allow download of the chart as PNG
        fig, ax = plt.subplots()
        age_count.plot(kind="bar", x="age_group", y="count", ax=ax, legend=False, color=ACCENT)
        buf = BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        plt.close(fig)
        st.download_button("Download age distribution PNG", data=buf.getvalue(), file_name="age_distribution.png", mime="image/png")

    else:
        st.info("No patient data")

    st.markdown("### Staff workload (visits per staff)")
    if not schedule_df.empty:
        w = schedule_df['staff_id'].value_counts().reset_index()
        w.columns = ['staff_id', 'visits']
        chart_w = alt.Chart(w).mark_bar(color="#66c2a5").encode(x='staff_id', y='visits')
        st.altair_chart(chart_w, use_container_width=True)

        fig, ax = plt.subplots()
        w.plot(kind="bar", x="staff_id", y="visits", ax=ax, legend=False, color="#66c2a5")
        buf2 = BytesIO()
        plt.savefig(buf2, format="png", bbox_inches="tight")
        buf2.seek(0)
        plt.close(fig)
        st.download_button("Download staff workload PNG", data=buf2.getvalue(), file_name="staff_workload.png", mime="image/png")
    else:
        st.info("No schedule data")

    render_footer()

# ---------------------------
# EMERGENCY
# ---------------------------
elif choice == "Emergency":
    st.subheader("Emergency")
    st.warning("This panel can be connected to SMS/Call systems in production.")
    patients_df = read_table("patients")
    if not patients_df.empty:
        sel = st.selectbox("Patient", patients_df['id'].tolist(), key="em_patient")
        row = patients_df[patients_df['id'] == sel].iloc[0]
        st.write(row.to_dict())
        if st.button("Show emergency contact"):
            st.info("Emergency contact: " + str(row.get('emergency_contact', '')))
    else:
        st.info("No patients yet.")
    render_footer()

# ---------------------------
# SETTINGS (user management, admin controls)
# ---------------------------
elif choice == "Settings":
    st.subheader("Settings & User Management")
    st.write(f"Logged in as **{st.session_state.user}** ({st.session_state.role})")

    # Change password
    with st.expander("Change your password", expanded=True):
        with st.form("change_pw_form", clear_on_submit=True):
            old = st.text_input("Current password", type="password", key="old_pw")
            new = st.text_input("New password", type="password", key="new_pw")
            new2 = st.text_input("Confirm new password", type="password", key="new_pw2")
            change_sub = st.form_submit_button("Change password")
            if change_sub:
                if not old or not new or new != new2:
                    st.error("Ensure fields are filled and new passwords match.")
                else:
                    conn_write = get_conn()
                    cur = conn_write.cursor()
                    cur.execute("SELECT password_hash FROM users WHERE username = ?", (st.session_state.user,))
                    row = cur.fetchone()
                    if row and hash_pw(old) == row[0]:
                        cur.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hash_pw(new), st.session_state.user))
                        db_commit_and_close(conn_write)
                        st.success("Password changed.")
                    else:
                        conn_write.close()
                        st.error("Current password incorrect.")

    # Admin-only panels
    if st.session_state.role == "admin":
        st.markdown("### Admin: Manage users")
        users_df = read_table("users")
        if not users_df.empty:
            st.dataframe(users_df[['username', 'role', 'created_at']])
        else:
            st.info("No users found")

        with st.expander("Create new user"):
            with st.form("create_user_form", clear_on_submit=True):
                u_name = st.text_input("Username", key="new_user_name")
                u_role = st.selectbox("Role", ["admin", "doctor", "nurse", "staff", "other"], key="new_user_role")
                u_pw = st.text_input("Password", type="password", key="new_user_pw")
                create_user_clicked = st.form_submit_button("Create user")
                if create_user_clicked:
                    if not u_name or not u_pw:
                        st.error("Username and password required")
                    else:
                        conn_write = get_conn()
                        cur = conn_write.cursor()
                        cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                                    (u_name, hash_pw(u_pw), u_role, now_iso()))
                        db_commit_and_close(conn_write)
                        st.success("User created")
                        st.experimental_rerun()

        with st.expander("Reset user password"):
            users_df2 = read_table("users")
            if not users_df2.empty:
                with st.form("reset_pw_form", clear_on_submit=True):
                    sel = st.selectbox("Select user", users_df2['username'].tolist(), key="reset_user_select")
                    new_pw = st.text_input("New password for selected user", type="password", key="reset_pw")
                    reset_clicked = st.form_submit_button("Reset password for selected user")
                    if reset_clicked:
                        if new_pw:
                            conn_write = get_conn()
                            cur = conn_write.cursor()
                            cur.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_pw(new_pw), sel))
                            db_commit_and_close(conn_write)
                            st.success("Password reset")
                        else:
                            st.error("Enter a password")
            else:
                st.info("No users found")

        with st.expander("Delete user"):
            users_df3 = read_table("users")
            if not users_df3.empty:
                with st.form("delete_user_form", clear_on_submit=True):
                    sel_del = st.selectbox("Select user to delete", users_df3['username'].tolist(), key="delete_user_select")
                    delete_clicked = st.form_submit_button("Delete selected user")
                    if delete_clicked:
                        if sel_del == st.session_state.user:
                            st.info("You cannot delete your own account while logged in.")
                        else:
                            conn_write = get_conn(); cur = conn_write.cursor()
                            cur.execute("DELETE FROM users WHERE username = ?", (sel_del,))
                            db_commit_and_close(conn_write)
                            st.success("User deleted")
                            st.experimental_rerun()
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
            with st.form("add_custom_field", clear_on_submit=True):
                new_field_name = st.text_input("Field label (e.g. Drug history)", key="cf_name")
                new_order = st.number_input("Order (0 = top)", min_value=0, step=1, value=len(cur_fields), key="cf_order")
                add_cf_clicked = st.form_submit_button("Add section")
                if add_cf_clicked:
                    if new_field_name.strip() == "":
                        st.error("Provide a field label")
                    else:
                        add_extra_field("patients", new_field_name.strip(), "text", int(new_order))
                        st.success("Added")
                        st.experimental_rerun()

        with st.expander("Remove custom patient section"):
            if cur_fields:
                with st.form("remove_custom_field", clear_on_submit=True):
                    remove_sel = st.selectbox("Select section to remove", [f"{cf['id']}|{cf['field_name']}" for cf in cur_fields], key="remove_cf_select")
                    remove_clicked = st.form_submit_button("Remove selected section")
                    if remove_clicked:
                        fid = int(remove_sel.split("|")[0])
                        remove_extra_field(fid)
                        st.success("Removed")
                        st.experimental_rerun()
            else:
                st.info("No custom sections to remove")

        with st.expander("Reorder custom patient sections"):
            if cur_fields:
                with st.form("reorder_custom_field", clear_on_submit=True):
                    ordered_input = st.text_input("Enter field ids in desired order, comma-separated (e.g. 3,1,2)", value=",".join(str(cf['id']) for cf in cur_fields), key="reorder_cf_input")
                    apply_reorder_clicked = st.form_submit_button("Apply new order")
                    if apply_reorder_clicked:
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

# ---------------------------
# EXPORT & BACKUP
# ---------------------------
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
        # patients age chart
        if not patients_df.empty:
            try:
                tmp = patients_df.copy()
                tmp['dob_dt'] = pd.to_datetime(tmp['dob'], errors='coerce')
                tmp['age'] = ((pd.Timestamp(date.today()) - tmp['dob_dt']).dt.days // 365).fillna(0).astype(int)
                age_bins = pd.cut(tmp['age'], bins=[-1, 1, 18, 40, 65, 120], labels=["<1", "1-17", "18-39", "40-64", "65+"])
                age_count = age_bins.value_counts().sort_index().reset_index()
                age_count.columns = ['Age group', 'Count']
                fig, ax = plt.subplots()
                age_count.plot(kind="bar", x="Age group", y="Count", ax=ax, legend=False, color=ACCENT)
                buf = BytesIO(); plt.savefig(buf, format="png", bbox_inches="tight"); buf.seek(0); charts["Patients by age group"] = buf.getvalue(); plt.close(fig)
            except Exception:
                pass
        # staff workload chart
        if not schedule_df.empty:
            try:
                workload = schedule_df['staff_id'].value_counts().reset_index()
                workload.columns = ['Staff', 'Visits']
                fig, ax = plt.subplots()
                workload.plot(kind="bar", x="Staff", y="Visits", ax=ax, legend=False, color="#66c2a5")
                buf = BytesIO(); plt.savefig(buf, format="png", bbox_inches="tight"); buf.seek(0); charts["Staff workload"] = buf.getvalue(); plt.close(fig)
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

# ---------------------------
# LOGOUT
# ---------------------------
elif choice == "Logout":
    logout_user()
    st.success("Logged out")
    st.experimental_rerun()

# default footer
else:
    render_footer()
