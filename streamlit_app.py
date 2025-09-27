# fullapp.py
# Smart Homecare Scheduler (single-file Streamlit app)
# All Rights Reserved - displayed inside app (HTML entity used to avoid source encoding issues)

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
from typing import List

# ---------------------------
# Configuration
# ---------------------------
DB_PATH = "homecare_scheduler.db"
APP_TITLE = "Smart Homecare Scheduler (24/7)"
RELAXING_BG = "#E8F6F3"
ACCENT = "#5DADE2"

STAFF_ROLES = ["Specialist", "GP", "Nurse", "RT", "PT", "Care Giver"]

# ---------------------------
# DB helpers (open/close for each write)
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def commit_close(conn):
    try:
        conn.commit()
    finally:
        conn.close()

# ---------------------------
# utilities
# ---------------------------
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def now_iso() -> str:
    return datetime.utcnow().isoformat()

# ---------------------------
# Initialize DB and tables
# ---------------------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT,
        role TEXT,
        created_at TEXT
      )
    """)
    cur.execute("""
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
    """)
    cur.execute("""
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
    """)
    cur.execute("""
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
    """)
    cur.execute("""
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
    """)
    cur.execute("""
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
    """)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS extra_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT,
        field_name TEXT,
        field_order INTEGER
      )
    """)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS extra_values (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT,
        record_id TEXT,
        field_id INTEGER,
        value TEXT
      )
    """)
    # seed demo users (won't overwrite existing)
    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                    ("admin", hash_pw("1234"), "admin", now_iso()))
        cur.execute("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                    ("doctor", hash_pw("abcd"), "doctor", now_iso()))
    commit_close(conn)

# ensure db
init_db()

# ---------------------------
# Read helpers (fresh reads)
# ---------------------------
@st.cache_data(show_spinner=False)
def read_table(tbl: str) -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql_query(f"SELECT * FROM {tbl}", conn)
    finally:
        conn.close()

# ---------------------------
# CSS + UI helpers
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
      .small-muted {{ font-size:12px; color:#666; }}
    </style>
    """, unsafe_allow_html=True)

def footer_html():
    return "<div class='footer'>All Rights Reserved &copy; Dr. Yousra Abdelatti</div>"

def make_visit_id() -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM schedule")
    c = cur.fetchone()["c"]
    conn.close()
    return f"V{c+1:05d}"

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
# Extra-fields (admin managed)
# ---------------------------
def get_extra_fields(entity: str = "patients") -> List[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, field_name, field_order FROM extra_fields WHERE entity=? ORDER BY field_order ASC, id ASC", (entity,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_extra_field(entity: str, field_name: str, order: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO extra_fields (entity, field_name, field_order) VALUES (?,?,?)", (entity, field_name, order))
    commit_close(conn)

def remove_extra_field(field_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM extra_values WHERE field_id = ?", (field_id,))
    cur.execute("DELETE FROM extra_fields WHERE id = ?", (field_id,))
    commit_close(conn)

def reorder_extra_fields(entity: str, ordered_ids: List[int]):
    conn = get_conn()
    cur = conn.cursor()
    for idx, fid in enumerate(ordered_ids):
        cur.execute("UPDATE extra_fields SET field_order = ? WHERE id = ?", (idx, fid))
    commit_close(conn)

def upsert_extra_value(entity: str, record_id: str, field_id: int, value: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM extra_values WHERE entity=? AND record_id=? AND field_id=?", (entity, record_id, field_id))
    r = cur.fetchone()
    if r:
        cur.execute("UPDATE extra_values SET value=? WHERE id=?", (value, r["id"]))
    else:
        cur.execute("INSERT INTO extra_values (entity, record_id, field_id, value) VALUES (?,?,?,?)", (entity, record_id, field_id, value))
    commit_close(conn)

def get_extra_values_for_record(entity: str, record_id: str) -> List[dict]:
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
# Export helpers (Excel/Word/CSV)
# ---------------------------
def to_excel_bytes(dfs: dict) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in dfs.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    output.seek(0)
    return output.getvalue()

def create_word_report(patients_df: pd.DataFrame, staff_df: pd.DataFrame, schedule_df: pd.DataFrame, charts_png: dict = None) -> bytes:
    doc = Document()
    doc.add_heading(APP_TITLE, level=1)
    doc.add_paragraph("Report generated: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    for title, df in [("Patients", patients_df), ("Staff", staff_df), ("Schedule", schedule_df)]:
        doc.add_heading(title, level=2)
        if not df.empty:
            table = doc.add_table(rows=1, cols=len(df.columns))
            hdr = table.rows[0].cells
            for i, c in enumerate(df.columns):
                hdr[i].text = str(c)
            for _, r in df.iterrows():
                cells = table.add_row().cells
                for i, c in enumerate(df.columns):
                    cells[i].text = "" if pd.isna(r[c]) else str(r[c])
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
# ID update helpers (careful: updates linked tables)
# ---------------------------
def update_patient_id(old_id: str, new_id: str) -> bool:
    """Change primary key of a patient and update all references.
    Returns True on success, False on failure (e.g. new_id already exists)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # ensure new id not used
        cur.execute("SELECT 1 FROM patients WHERE id = ?", (new_id,))
        if cur.fetchone():
            conn.close()
            return False
        # update patients
        cur.execute("UPDATE patients SET id = ? WHERE id = ?", (new_id, old_id))
        # update schedules
        cur.execute("UPDATE schedule SET patient_id = ? WHERE patient_id = ?", (new_id, old_id))
        # update vitals
        cur.execute("UPDATE vitals SET patient_id = ? WHERE patient_id = ?", (new_id, old_id))
        # update visit_logs
        cur.execute("UPDATE visit_log SET patient_id = ? WHERE patient_id = ?", (new_id, old_id))
        commit_close(conn)
        return True
    except Exception:
        conn.close()
        return False

def update_staff_id(old_id: str, new_id: str) -> bool:
    """Change primary key of a staff and update schedule references.
    Returns True on success, False on failure (e.g. new_id already exists)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM staff WHERE id = ?", (new_id,))
        if cur.fetchone():
            conn.close()
            return False
        cur.execute("UPDATE staff SET id = ? WHERE id = ?", (new_id, old_id))
        cur.execute("UPDATE schedule SET staff_id = ? WHERE staff_id = ?", (new_id, old_id))
        commit_close(conn)
        return True
    except Exception:
        conn.close()
        return False

# ---------------------------
# Page config and login UI
# ---------------------------
inject_css()
st.set_page_config(page_title=APP_TITLE, layout="wide")

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
    st.markdown("<div class='login-bottom'><span style='font-weight:bold; color:purple;'>All Rights Reserved &copy; Dr. Yousra Abdelatti</span></div>", unsafe_allow_html=True)
    st.stop()

# ---------------------------
# Main app layout and menu
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
    if not schedule_df.empty:
        schedule_df['date_dt'] = pd.to_datetime(schedule_df['date'], errors='coerce')
        upcoming = schedule_df[(schedule_df['date_dt'] >= pd.Timestamp(date.today())) & (schedule_df['date_dt'] <= pd.Timestamp(date.today() + timedelta(days=30)))]
        upcoming = upcoming.sort_values(['date', 'start_time']).head(100)
        st.dataframe(upcoming[['visit_id', 'patient_id', 'staff_id', 'date', 'start_time', 'end_time', 'visit_type', 'priority']])
    else:
        st.info("No visits scheduled yet.")

    # quick analytics
    st.markdown("### Quick analytics")
    col1, col2 = st.columns(2)
    with col1:
        if not patients_df.empty:
            dfp = patients_df.copy()
            dfp['dob_dt'] = pd.to_datetime(dfp['dob'], errors='coerce')
            dfp['age'] = ((pd.Timestamp(date.today()) - dfp['dob_dt']).dt.days // 365).fillna(0).astype(int)
            age_bins = pd.cut(dfp['age'], bins=[-1, 0, 1, 5, 12, 18, 40, 65, 200], labels=["<1", "1-5", "6-12", "13-18", "19-40", "41-65", "66+"])
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

    st.markdown(footer_html(), unsafe_allow_html=True)

# ---------- PATIENTS ----------
elif choice == "Patients":
    st.subheader("🏥 Home Care Patient File")
    patients_df = read_table("patients")
    custom_fields = get_extra_fields("patients")

    with st.expander("Add New Patient (full file)", expanded=True):
        with st.form("add_patient_form", clear_on_submit=True):
            p_id = st.text_input("Patient ID (unique)", key="new_patient_id")
            p_name = st.text_input("Full name", key="new_patient_name")
            p_dob = st.date_input("Date of Birth", min_value=date(1900,1,1), key="new_patient_dob")
            p_gender = st.selectbox("Gender", ["Female", "Male", "Other", "Prefer not to say"], key="new_patient_gender")
            p_phone = st.text_input("Phone", key="new_patient_phone")
            p_email = st.text_input("Email", key="new_patient_email")
            p_address = st.text_area("Address", key="new_patient_address")
            p_emergency = st.text_input("Emergency contact (name & phone)", key="new_patient_emergency")
            p_ins_provider = st.text_input("Insurance provider", key="new_patient_ins")
            p_ins_number = st.text_input("Insurance number", key="new_patient_ins_num")
            p_allergies = st.text_area("Allergies", key="new_patient_allergies")
            p_meds = st.text_area("Current medications", key="new_patient_meds")
            p_diag = st.text_area("Primary diagnosis", key="new_patient_diag")
            p_equip = st.text_area("Equipment required", key="new_patient_equip")
            p_mobility = st.selectbox("Mobility level", ["Independent", "Assisted", "Wheelchair", "Bedbound"], key="new_patient_mobility")
            p_care_plan = st.text_area("Care plan summary", key="new_patient_care")
            p_notes = st.text_area("Notes / social history", key="new_patient_notes")

            # custom fields (admin-defined)
            custom_values = {}
            if custom_fields:
                st.markdown("### Custom Sections (Admin)")
                for cf in custom_fields:
                    key = f"custom_{cf['id']}"
                    custom_values[key] = st.text_input(cf['field_name'], key=key)

            submitted = st.form_submit_button("Save Patient")
            if submitted:
                if not p_id or not p_name:
                    st.error("Patient ID and Full name are required.")
                else:
                    conn = get_conn()
                    cur = conn.cursor()
                    try:
                        cur.execute("""
                          INSERT INTO patients
                          (id,name,dob,gender,phone,email,address,emergency_contact,insurance_provider,insurance_number,allergies,medications,diagnosis,equipment_required,mobility,care_plan,notes,created_by,created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (p_id, p_name, p_dob.isoformat(), p_gender, p_phone, p_email, p_address, p_emergency,
                              p_ins_provider, p_ins_number, p_allergies, p_meds, p_diag, p_equip, p_mobility, p_care_plan, p_notes, st.session_state.user, now_iso()))
                        commit_close(conn)
                        # save custom fields
                        for cf in custom_fields:
                            key = f"custom_{cf['id']}"
                            val = custom_values.get(key)
                            if val:
                                upsert_extra_value("patients", p_id, cf['id'], val)
                        st.success("Patient saved.")
                        st.experimental_rerun()
                    except sqlite3.IntegrityError:
                        conn.close()
                        st.error("A patient with that ID already exists. Use a unique ID.")

    st.markdown("---")
    st.write("Existing patients:")
    st.dataframe(patients_df)

    # Edit / Delete patient (admin or creator)
    if not patients_df.empty:
        st.markdown("### Edit / Delete patient")
        sel = st.selectbox("Select patient to edit", patients_df['id'].tolist(), key="edit_patient_select")
        row = patients_df[patients_df['id'] == sel].iloc[0]
        can_edit = (st.session_state.role == "admin") or (row.get("created_by") == st.session_state.user)
        if not can_edit:
            st.info("You can view this patient's record but only the admin or the creator can edit/delete it.")
        # Show current extra values
        extra_vals = get_extra_values_for_record("patients", sel)

        with st.form("edit_patient_form", clear_on_submit=False):
            e_id = st.text_input("Patient ID (editable)", value=row['id'], key="edit_patient_id")
            e_name = st.text_input("Name", value=row['name'], key="edit_patient_name")
            dob_val = pd.to_datetime(row['dob'], errors='coerce')
            e_dob = st.date_input("DOB", value=dob_val.date() if pd.notna(dob_val) else date.today(), key="edit_patient_dob")
            e_gender = st.selectbox("Gender", ["Female", "Male", "Other", "Prefer not to say"], index=0, key="edit_patient_gender")
            e_phone = st.text_input("Phone", value=row['phone'], key="edit_patient_phone")
            e_email = st.text_input("Email", value=row['email'], key="edit_patient_email")
            e_address = st.text_area("Address", value=row['address'], key="edit_patient_address")
            e_emergency = st.text_input("Emergency contact", value=row['emergency_contact'], key="edit_patient_emergency")
            e_ins = st.text_input("Insurance provider", value=row['insurance_provider'], key="edit_patient_ins")
            e_ins_num = st.text_input("Insurance number", value=row['insurance_number'], key="edit_patient_ins_num")
            e_all = st.text_area("Allergies", value=row['allergies'], key="edit_patient_all")
            e_meds = st.text_area("Medications", value=row['medications'], key="edit_patient_meds")
            e_diag = st.text_area("Diagnosis", value=row['diagnosis'], key="edit_patient_diag")
            e_equip = st.text_area("Equipment", value=row['equipment_required'], key="edit_patient_equip")
            e_mobility = st.selectbox("Mobility", ["Independent", "Assisted", "Wheelchair", "Bedbound"], index=0, key="edit_patient_mobility")
            e_care = st.text_area("Care plan", value=row['care_plan'], key="edit_patient_care")
            e_notes = st.text_area("Notes", value=row['notes'], key="edit_patient_notes")

            # show extra fields values for editing
            updated_custom = {}
            if extra_vals:
                st.markdown("### Custom fields (editable)")
                for ev in extra_vals:
                    k = f"ev_{ev['field_id']}"
                    updated_custom[k] = st.text_input(ev['field_name'], value=ev.get('value') or "", key=k)

            if can_edit:
                if st.form_submit_button("Save changes"):
                    conn = get_conn()
                    cur = conn.cursor()
                    try:
                        # If ID changed -> confirm and update references
                        if e_id != sel:
                            # confirm via a second prompt
                            confirm = st.checkbox(f"I confirm changing patient ID from {sel} to {e_id} (this will update schedule, vitals, visit_logs)", key="confirm_patient_id_change")
                            if not confirm:
                                st.error("Please check the confirmation box to change Patient ID.")
                                conn.close()
                            else:
                                # attempt update
                                success = update_patient_id(sel, e_id)
                                if not success:
                                    st.error("New Patient ID already exists or update failed.")
                                    conn.close()
                                else:
                                    # after id change, update patient data at new id
                                    conn2 = get_conn(); cur2 = conn2.cursor()
                                    cur2.execute("""
                                      UPDATE patients SET name=?, dob=?, gender=?, phone=?, email=?, address=?, emergency_contact=?, insurance_provider=?, insurance_number=?, allergies=?, medications=?, diagnosis=?, equipment_required=?, mobility=?, care_plan=?, notes=?
                                      WHERE id=?
                                    """, (e_name, e_dob.isoformat(), e_gender, e_phone, e_email, e_address, e_emergency, e_ins, e_ins_num, e_all, e_meds, e_diag, e_equip, e_mobility, e_care, e_notes, e_id))
                                    commit_close(conn2)
                                    # update extra values
                                    for ev in extra_vals:
                                        k = f"ev_{ev['field_id']}"
                                        val = updated_custom.get(k, "")
                                        if val != "":
                                            upsert_extra_value("patients", e_id, ev['field_id'], val)
                                    st.success("Patient ID and record updated.")
                                    st.experimental_rerun()
                        else:
                            # ID not changed: normal update
                            cur.execute("""
                              UPDATE patients SET name=?, dob=?, gender=?, phone=?, email=?, address=?, emergency_contact=?, insurance_provider=?, insurance_number=?, allergies=?, medications=?, diagnosis=?, equipment_required=?, mobility=?, care_plan=?, notes=?
                              WHERE id=?
                            """, (e_name, e_dob.isoformat(), e_gender, e_phone, e_email, e_address, e_emergency, e_ins, e_ins_num, e_all, e_meds, e_diag, e_equip, e_mobility, e_care, e_notes, sel))
                            commit_close(conn)
                            # update custom fields
                            for ev in extra_vals:
                                k = f"ev_{ev['field_id']}"
                                val = updated_custom.get(k, "")
                                if val != "":
                                    upsert_extra_value("patients", sel, ev['field_id'], val)
                            st.success("Patient updated.")
                            st.experimental_rerun()
                    except Exception as ex:
                        conn.close()
                        st.error("Error updating patient: " + str(ex))
                if st.button("Delete patient"):
                    conn = get_conn(); cur = conn.cursor()
                    cur.execute("DELETE FROM patients WHERE id=?", (sel,))
                    # remove related vitals, visit_log, schedules? (we'll keep schedule history unless admin chooses)
                    cur.execute("DELETE FROM vitals WHERE patient_id=?", (sel,))
                    cur.execute("DELETE FROM visit_log WHERE patient_id=?", (sel,))
                    cur.execute("DELETE FROM schedule WHERE patient_id=?", (sel,))
                    commit_close(conn)
                    st.success("Patient and related records deleted.")
                    st.experimental_rerun()

    st.markdown(footer_html(), unsafe_allow_html=True)

# ---------- STAFF ----------
elif choice == "Staff":
    st.subheader("Manage Staff")
    staff_df = read_table("staff")

    with st.form("add_staff_form", clear_on_submit=True):
        s_id = st.text_input("Staff ID (unique)", key="new_staff_id")
        s_name = st.text_input("Full name", key="new_staff_name")
        s_role = st.selectbox("Role", STAFF_ROLES, key="new_staff_role")
        s_license = st.text_input("License / registration number", key="new_staff_license")
        s_specialties = st.text_input("Specialties (comma separated)", key="new_staff_specs")
        s_phone = st.text_input("Phone", key="new_staff_phone")
        s_email = st.text_input("Email", key="new_staff_email")
        s_availability = st.text_area("Availability (e.g. Mon-Fri 08:00-16:00)", key="new_staff_avail")
        s_notes = st.text_area("Notes", key="new_staff_notes")
        if st.form_submit_button("Save staff"):
            if not s_id or not s_name:
                st.error("Staff ID and name required")
            else:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    cur.execute("""
                       INSERT INTO staff (id,name,role,license_number,specialties,phone,email,availability,notes,created_by,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (s_id, s_name, s_role, s_license, s_specialties, s_phone, s_email, s_availability, s_notes, st.session_state.user, now_iso()))
                    commit_close(conn)
                    st.success("Staff saved.")
                    st.experimental_rerun()
                except sqlite3.IntegrityError:
                    conn.close()
                    st.error("A staff member with that ID already exists. Use a unique ID.")

    st.markdown("---")
    st.write("Existing staff:")
    st.dataframe(staff_df)

    # Edit/Delete staff (admin or creator)
    if not staff_df.empty:
        st.markdown("### Edit / Delete staff")
        sel = st.selectbox("Select staff to edit", staff_df['id'].tolist(), key="edit_staff_select")
        row = staff_df[staff_df['id'] == sel].iloc[0]
        can_edit = (st.session_state.role == "admin") or (row.get("created_by") == st.session_state.user)
        if not can_edit:
            st.info("You can view this staff record but only the admin or the creator can edit/delete it.")

        with st.form("edit_staff_form", clear_on_submit=False):
            e_id = st.text_input("Staff ID (editable)", value=row['id'], key="edit_staff_id")
            e_name = st.text_input("Name", value=row['name'], key="edit_staff_name")
            e_role = st.selectbox("Role", STAFF_ROLES, index=STAFF_ROLES.index(row['role']) if row['role'] in STAFF_ROLES else 0, key="edit_staff_role")
            e_license = st.text_input("License/Registration", value=row['license_number'], key="edit_staff_license")
            e_specs = st.text_input("Specialties", value=row['specialties'], key="edit_staff_specs")
            e_phone = st.text_input("Phone", value=row['phone'], key="edit_staff_phone")
            e_email = st.text_input("Email", value=row['email'], key="edit_staff_email")
            e_avail = st.text_area("Availability", value=row['availability'], key="edit_staff_avail")
            e_notes = st.text_area("Notes", value=row['notes'], key="edit_staff_notes")

            if can_edit:
                if st.form_submit_button("Save staff changes"):
                    try:
                        # If ID changed -> confirm and update references
                        if e_id != sel:
                            confirm = st.checkbox(f"I confirm changing staff ID from {sel} to {e_id} (this will update schedule references)", key="confirm_staff_id_change")
                            if not confirm:
                                st.error("Please check the confirmation box to change Staff ID.")
                            else:
                                ok = update_staff_id(sel, e_id)
                                if not ok:
                                    st.error("New staff ID already exists or update failed.")
                                else:
                                    # update other staff fields
                                    conn2 = get_conn(); cur2 = conn2.cursor()
                                    cur2.execute("""
                                      UPDATE staff SET name=?, role=?, license_number=?, specialties=?, phone=?, email=?, availability=?, notes=? WHERE id=?
                                    """, (e_name, e_role, e_license, e_specs, e_phone, e_email, e_avail, e_notes, e_id))
                                    commit_close(conn2)
                                    st.success("Staff ID and record updated.")
                                    st.experimental_rerun()
                        else:
                            conn2 = get_conn(); cur2 = conn2.cursor()
                            cur2.execute("""
                              UPDATE staff SET name=?, role=?, license_number=?, specialties=?, phone=?, email=?, availability=?, notes=? WHERE id=?
                            """, (e_name, e_role, e_license, e_specs, e_phone, e_email, e_avail, e_notes, sel))
                            commit_close(conn2)
                            st.success("Staff updated.")
                            st.experimental_rerun()
                    except Exception as ex:
                        st.error("Error updating staff: " + str(ex))
                if st.button("Delete staff"):
                    conn2 = get_conn(); cur2 = conn2.cursor()
                    # remove schedule entries for this staff to avoid orphan references
                    cur2.execute("DELETE FROM schedule WHERE staff_id=?", (sel,))
                    cur2.execute("DELETE FROM staff WHERE id=?", (sel,))
                    commit_close(conn2)
                    st.success("Staff and related schedules deleted.")
                    st.experimental_rerun()

    st.markdown(footer_html(), unsafe_allow_html=True)

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
            visit_date = st.date_input("Date", value=date.today(), key="sch_date")
            start = st.time_input("Start", value=dtime(9, 0), key="sch_start")
            end = st.time_input("End", value=dtime(10, 0), key="sch_end")
            visit_type = st.selectbox("Visit type", ["Home visit", "Telehealth", "Wound care", "Medication administration", "Physiotherapy", "Respiratory therapy", "Assessment", "Other"], key="sch_vtype")
            priority = st.selectbox("Priority", ["Low", "Normal", "High", "Critical"], key="sch_priority")
            notes = st.text_area("Notes / visit plan", key="sch_notes")
            if st.form_submit_button("Create visit"):
                if not patient_sel or not staff_sel:
                    st.error("Select patient and staff")
                else:
                    vid = make_visit_id()
                    duration = int((datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).seconds / 60)
                    conn = get_conn(); cur = conn.cursor()
                    try:
                        cur.execute("""
                          INSERT INTO schedule (visit_id,patient_id,staff_id,date,start_time,end_time,visit_type,duration_minutes,priority,notes,created_by,created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (vid, patient_sel, staff_sel, visit_date.isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M"), visit_type, duration, priority, notes, st.session_state.user, now_iso()))
                        commit_close(conn)
                        st.success(f"Visit {vid} created")
                        st.experimental_rerun()
                    except sqlite3.IntegrityError:
                        conn.close()
                        st.error("A visit with that ID already exists. Try again.")

    with col2:
        st.markdown("### View / Manage visits")
        if schedule_df.empty:
            st.info("No visits scheduled yet.")
        else:
            sel_visit = st.selectbox("Select visit", schedule_df['visit_id'].tolist(), key="view_visit")
            row = schedule_df[schedule_df['visit_id'] == sel_visit].iloc[0]
            st.write(row.to_dict())
            can_edit = (st.session_state.role == "admin") or (row.get("created_by") == st.session_state.user)
            if can_edit:
                if st.button("Delete visit"):
                    conn = get_conn(); cur = conn.cursor()
                    cur.execute("DELETE FROM schedule WHERE visit_id = ?", (sel_visit,))
                    commit_close(conn)
                    st.success("Visit deleted")
                    st.experimental_rerun()
            else:
                st.info("Only admin or creator can delete this visit.")
    st.markdown(footer_html(), unsafe_allow_html=True)

# ---------- ANALYTICS ----------
elif choice == "Analytics":
    st.subheader("Analytics")
    patients_df = read_table("patients")
    schedule_df = read_table("schedule")

    st.markdown("### Patients by age group")
    if not patients_df.empty:
        patients_df['dob_dt'] = pd.to_datetime(patients_df['dob'], errors='coerce')
        patients_df['age'] = ((pd.Timestamp(date.today()) - patients_df['dob_dt']).dt.days // 365).fillna(0).astype(int)
        age_bins = pd.cut(patients_df['age'], bins=[-1,0,1,18,40,65,200], labels=["<1","1-17","18-39","40-64","65+"])
        age_count = age_bins.value_counts().sort_index().reset_index()
        age_count.columns = ['age_group', 'count']
        chart_age = alt.Chart(age_count).mark_bar(color=ACCENT).encode(x='age_group', y='count')
        st.altair_chart(chart_age, use_container_width=True)

        # provide downloadable PNG
        fig, ax = plt.subplots()
        age_count.plot(kind="bar", x="age_group", y="count", ax=ax, legend=False, color=ACCENT)
        buf = BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close(fig)
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
        buf2 = BytesIO(); plt.savefig(buf2, format="png"); buf2.seek(0); plt.close(fig)
        st.download_button("Download staff workload PNG", data=buf2.getvalue(), file_name="staff_workload.png", mime="image/png")
    else:
        st.info("No schedule data")

    st.markdown(footer_html(), unsafe_allow_html=True)

# ---------- EMERGENCY ----------
elif choice == "Emergency":
    st.subheader("Emergency")
    st.warning("Quick patient lookup for emergencies")
    patients_df = read_table("patients")
    if not patients_df.empty:
        sel = st.selectbox("Patient", patients_df['id'].tolist(), key="em_pat_select")
        row = patients_df[patients_df['id'] == sel].iloc[0]
        st.write(row.to_dict())
        if st.button("Show emergency contact"):
            st.info("Emergency contact: " + str(row['emergency_contact']))
    else:
        st.info("No patients yet.")
    st.markdown(footer_html(), unsafe_allow_html=True)

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
                conn = get_conn(); cur = conn.cursor()
                cur.execute("SELECT password_hash FROM users WHERE username = ?", (st.session_state.user,))
                row = cur.fetchone()
                if row and hash_pw(old) == row[0]:
                    cur.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hash_pw(new), st.session_state.user))
                    commit_close(conn)
                    st.success("Password changed.")
                else:
                    conn.close()
                    st.error("Current password incorrect.")

    # Admin functionality
    if st.session_state.role == "admin":
        st.markdown("### Admin: Manage users")
        users_df = read_table("users")
        if not users_df.empty:
            st.dataframe(users_df[['username','role','created_at']])
        else:
            st.info("No users found")

        with st.expander("Create new user"):
            u_name = st.text_input("Username", key="new_user_name")
            u_role = st.selectbox("Role", ["admin","doctor","nurse","staff","other"], key="new_user_role")
            u_pw = st.text_input("Password", type="password", key="new_user_pw")
            if st.button("Create user"):
                if not u_name or not u_pw:
                    st.error("Username and password required")
                else:
                    conn = get_conn(); cur = conn.cursor()
                    try:
                        cur.execute("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                                    (u_name, hash_pw(u_pw), u_role, now_iso()))
                        commit_close(conn)
                        st.success("User created")
                        st.experimental_rerun()
                    except sqlite3.IntegrityError:
                        conn.close()
                        st.error("User already exists")

        with st.expander("Reset user password"):
            users_df2 = read_table("users")
            if not users_df2.empty:
                sel = st.selectbox("Select user", users_df2['username'].tolist(), key="reset_user_select")
                new_pw = st.text_input("New password for selected user", type="password", key="reset_pw")
                if st.button("Reset password for selected user"):
                    if new_pw:
                        conn = get_conn(); cur = conn.cursor()
                        cur.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_pw(new_pw), sel))
                        commit_close(conn)
                        st.success("Password reset")
                    else:
                        st.error("Enter a password")
            else:
                st.info("No users found")

        with st.expander("Delete user"):
            users_df3 = read_table("users")
            if not users_df3.empty:
                sel_del = st.selectbox("Select user to delete", users_df3['username'].tolist(), key="delete_user_select")
                if sel_del == st.session_state.user:
                    st.info("You cannot delete your own account while logged in.")
                else:
                    if st.button("Delete selected user"):
                        conn = get_conn(); cur = conn.cursor()
                        cur.execute("DELETE FROM users WHERE username = ?", (sel_del,))
                        commit_close(conn)
                        st.success("User deleted")
                        st.experimental_rerun()
            else:
                st.info("No users found")

        # Extra fields management (patients)
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

    st.markdown(footer_html(), unsafe_allow_html=True)

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

    try:
        with open(DB_PATH, "rb") as f:
            db_bytes = f.read()
            st.download_button("Download DB file", data=db_bytes, file_name=DB_PATH, mime="application/x-sqlite3")
    except Exception as e:
        st.error("Could not read DB file: " + str(e))

    st.markdown(footer_html(), unsafe_allow_html=True)

# ---------- LOGOUT ----------
elif choice == "Logout":
    logout_user()
    st.success("Logged out")
    st.experimental_rerun()

# fallback footer
else:
    st.markdown(footer_html(), unsafe_allow_html=True)
