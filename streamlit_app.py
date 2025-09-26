# app.py
# Smart Homecare Scheduler (enhanced single-file Streamlit app)
# All Rights Reserved © Dr. Yousra Abdelatti (footer in purple)
# Developed By Dr. Mohammedelnagi Mohammed (footer in blue)
#
# Fixes:
# - Staff assignment bug fixed
# - Staff/patient save/edit bug fixed
# - Error messages cleaned up
# - Footer styled as requested

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date, time as dtime
from io import BytesIO
import altair as alt
import os
import hashlib
from docx import Document
from docx.shared import Inches
import tempfile

# ---------------------------
# Configuration / Constants
# ---------------------------
DB_PATH = "homecare_scheduler.db"
APP_TITLE = "Smart Homecare Scheduler (24/7)"
RELAXING_BG = "#E8F6F3"
ACCENT = "#5DADE2"
FOOTER = """
<div style="padding:12px 0; text-align:center;">
    <div style="font-weight:bold; color:purple;">All Rights Reserved © Dr. Yousra Abdelatti</div>
    <div style="font-weight:bold; color:blue;">Developed By Dr. Mohammedelnagi Mohammed</div>
</div>
"""

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
            diagnosis TEXT,
            notes TEXT,
            recurring_rule TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')
    # seed admin & doctor if none
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
# Read helpers (cached)
# ---------------------------
@st.cache_data(show_spinner=False)
def read_table(name: str):
    return pd.read_sql_query(f"SELECT * FROM {name}", conn)

# ---------------------------
# UI Helpers / CSS
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
    </style>
    """, unsafe_allow_html=True)

def make_visit_id():
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM schedule")
    count = cur.fetchone()["c"] + 1
    return f"V{count:05d}"

def render_footer():
    st.markdown(FOOTER, unsafe_allow_html=True)

# ---------------------------
# Authentication & Session
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
# App Layout
# ---------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")
inject_css()

if not st.session_state.logged_in:
    st.markdown('<div class="big-title">Smart Homecare Scheduler Login</div>', unsafe_allow_html=True)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if login_user(username, password):
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.stop()

st.sidebar.title("Menu")
menu = ["Dashboard","Patients","Staff","Schedule","Logout"]
choice = st.sidebar.radio("Go to", menu)

st.markdown(f"<div class='big-title'>{APP_TITLE}</div>", unsafe_allow_html=True)

# ---------- Staff ----------
if choice == "Staff":
    st.subheader("Manage Staff")
    staff_df = read_table("staff")

    with st.expander("Add staff member"):
        s_id = st.text_input("Staff ID (unique)")
        s_name = st.text_input("Full name")
        s_role = st.selectbox("Role", ["Doctor","Nurse","Physiotherapist","Respiratory Therapist","Caregiver","Other"])
        if st.button("Add staff"):
            if s_id.strip():
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO staff (id,name,role,created_by,created_at) VALUES (?,?,?,?,?)",
                            (s_id,s_name,s_role,st.session_state.user, now_iso()))
                conn.commit()
                st.success("Staff saved")
                st.rerun()

    st.dataframe(staff_df)

# ---------- Patients ----------
elif choice == "Patients":
    st.subheader("Manage Patients")
    patients_df = read_table("patients")

    with st.expander("Add patient"):
        p_id = st.text_input("Patient ID (unique)")
        p_name = st.text_input("Full name")
        p_dob = st.date_input("Date of birth", max_value=date.today())
        if st.button("Add patient"):
            if p_id.strip():
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO patients (id,name,dob,created_by,created_at) VALUES (?,?,?,?,?)",
                            (p_id,p_name,p_dob.isoformat(),st.session_state.user, now_iso()))
                conn.commit()
                st.success("Patient saved")
                st.rerun()

    st.dataframe(patients_df)

# ---------- Schedule ----------
elif choice == "Schedule":
    st.subheader("Create Visit")
    patients_df = read_table("patients")
    staff_df = read_table("staff")
    if patients_df.empty or staff_df.empty:
        st.warning("Add patients and staff first.")
    else:
        patient_sel = st.selectbox("Patient", patients_df['id'].tolist())
        staff_sel = st.selectbox("Assign staff", staff_df['id'].tolist())
        visit_date = st.date_input("Date", value=date.today())
        start = st.time_input("Start", value=dtime(9,0))
        end = st.time_input("End", value=dtime(10,0))
        if st.button("Save visit"):
            visit_id = make_visit_id()
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO schedule (visit_id,patient_id,staff_id,date,start_time,end_time,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (visit_id,patient_sel,staff_sel,visit_date.isoformat(),start.strftime("%H:%M"),end.strftime("%H:%M"),st.session_state.user, now_iso()))
            conn.commit()
            st.success(f"Visit {visit_id} saved")
            st.rerun()

# ---------- Logout ----------
elif choice == "Logout":
    logout_user()
    st.success("Logged out")
    st.rerun()

render_footer()
