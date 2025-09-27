# app.py
# Smart Homecare Scheduler (Streamlit App) - Single-file updated
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

# Ensure DB exists
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
# (unchanged code for extra fields...)

# ---------------------------
# Export helpers
# ---------------------------
# (unchanged code for export...)

# ---------------------------
# Page config + login UI
# ---------------------------
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
    col1, col2 = st.columns([1, 1])
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

# ---------- STAFF ----------
elif choice == "Staff":
    st.subheader("Manage Staff")
    staff_df = read_table("staff")

    with st.form("add_staff_form", clear_on_submit=True):
        s_id = st.text_input("Staff ID (unique)", key="new_staff_id")
        s_name = st.text_input("Full name", key="new_staff_name")
        s_role = st.selectbox("Role", STAFF_ROLES, key="new_staff_role")
        s_phone = st.text_input("Phone", key="new_staff_phone")
        s_email = st.text_input("Email", key="new_staff_email")
        s_availability = st.text_area("Availability (e.g. Mon-Fri 08:00-16:00)", key="new_staff_avail")
        s_notes = st.text_area("Notes", key="new_staff_notes")
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

    # ✅ Editable Staff ID block
    if not staff_df.empty:
        st.markdown("### Edit / Delete staff")
        sel_staff = st.selectbox("Select staff to edit", staff_df['id'].tolist(), key="edit_staff_select")
        row = staff_df[staff_df['id'] == sel_staff].iloc[0]
        can_edit_staff = (st.session_state.role == "admin") or (row.get("created_by") == st.session_state.user)

        if not can_edit_staff:
            st.info("You can view this staff record but only the admin or the creator can edit/delete it.")

        with st.form("edit_staff_form", clear_on_submit=False):
            es_id = st.text_input("Staff ID", value=row['id'])  # now editable
            es_name = st.text_input("Name", value=row['name'])
            es_role = st.selectbox("Role", STAFF_ROLES,
                                   index=STAFF_ROLES.index(row['role']) if row['role'] in STAFF_ROLES else 0)
            es_phone = st.text_input("Phone", value=row['phone'])
            es_email = st.text_input("Email", value=row['email'])
            es_avail = st.text_area("Availability", value=row['availability'])
            es_notes = st.text_area("Notes", value=row['notes'])

            if can_edit_staff:
                if st.form_submit_button("Save staff changes"):
                    conn_write = get_conn(); cur = conn_write.cursor()
                    cur.execute("""
                        UPDATE staff SET id=?, name=?, role=?, phone=?, email=?, availability=?, notes=?
                        WHERE id=?
                    """, (es_id, es_name, es_role, es_phone, es_email, es_avail, es_notes, sel_staff))
                    if es_id != sel_staff:
                        cur.execute("UPDATE schedule SET staff_id=? WHERE staff_id=?", (es_id, sel_staff))
                    db_commit_and_close(conn_write)
                    st.success("Staff updated")
                    st.experimental_rerun()

                if st.form_submit_button("Delete staff"):
                    conn_write = get_conn(); cur = conn_write.cursor()
                    cur.execute("DELETE FROM staff WHERE id=?", (sel_staff,))
                    cur.execute("DELETE FROM schedule WHERE staff_id=?", (sel_staff,))
                    db_commit_and_close(conn_write)
                    st.success("Staff deleted")
                    st.experimental_rerun()

    render_footer()

# (rest of your app unchanged...)
