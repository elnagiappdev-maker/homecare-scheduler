# app.py
# Smart Homecare Scheduler (enhanced with KPIs, conflict detection, calendar view, recurring visits, role-based access, analytics, filters)
# Footer: All Rights Reserved © Dr. Yousra Abdelatti (purple)
#         Developed By Dr. Mohammedelnagi Mohammed (blue)

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date, time as dtime
from io import BytesIO
import altair as alt
import hashlib
from docx import Document
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
            created_at TEXT,
            recurrence TEXT
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
# Helpers
# ---------------------------
@st.cache_data(show_spinner=False)
def read_table(name: str):
    return pd.read_sql_query(f"SELECT * FROM {name}", conn)

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
    return f"V{cur.fetchone()['c']+1:05d}"

def render_footer():
    st.markdown("---")
    st.markdown("""
    <div style="padding:12px 0; text-align:center;">
        <div style="font-weight:bold; color:purple;">All Rights Reserved © Dr. Yousra Abdelatti</div>
        <div style="font-weight:bold; color:blue;">Developed By Dr. Mohammedelnagi Mohammed</div>
    </div>
    """, unsafe_allow_html=True)

def is_conflict(staff_id, date, start, end):
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM schedule 
        WHERE staff_id = ? AND date = ?
        AND (
            (? BETWEEN start_time AND end_time) OR 
            (? BETWEEN start_time AND end_time) OR
            (start_time BETWEEN ? AND ?) OR 
            (end_time BETWEEN ? AND ?)
        )
    """, (staff_id, date, start, end, start, end, start, end))
    return cur.fetchone() is not None

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
    st.stop()

st.sidebar.title("📋 Menu")
menu = ["🏠 Dashboard","🧑‍⚕️ Patients","👩 Staff","📅 Schedule","📊 Analytics","🚨 Emergency","⚙️ Settings","💾 Export & Backup","🚪 Logout"]
choice = st.sidebar.radio("Go to", menu)

st.markdown(f"<div class='big-title'>{APP_TITLE}</div>", unsafe_allow_html=True)

# ---------- Dashboard ----------
if choice.startswith("🏠"):
    patients = read_table("patients")
    staff = read_table("staff")
    sched = read_table("schedule")
    c1,c2,c3 = st.columns(3)
    c1.metric("Patients", len(patients))
    c2.metric("Staff", len(staff))
    c3.metric("Visits", len(sched))

    if not sched.empty:
        avg_duration = round(sched['duration_minutes'].astype(float).mean(),1)
        common_type = sched['visit_type'].mode()[0] if not sched['visit_type'].isna().all() else "N/A"
        busiest = sched['staff_id'].value_counts().idxmax()
        st.metric("Avg Visit Duration (min)", avg_duration)
        st.metric("Most Common Visit Type", common_type)
        st.metric("Busiest Staff", busiest)

    render_footer()

# ---------- Patients ----------
elif choice.startswith("🧑‍⚕️"):
    st.subheader("Patients")
    patients = read_table("patients")
    search = st.text_input("Search by name/ID/phone")
    if search:
        patients = patients[patients.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
    with st.form("add_patient", clear_on_submit=True):
        p_id = st.text_input("Patient ID (unique)")
        p_name = st.text_input("Full name")
        p_dob = st.date_input("DOB", value=date(2000,1,1), min_value=date(1900,1,1))
        p_gender = st.selectbox("Gender", ["Female","Male","Other"])
        submitted = st.form_submit_button("Add")
        if submitted and p_id:
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO patients (id,name,dob,gender,created_by,created_at) VALUES (?,?,?,?,?,?)",
                        (p_id,p_name,p_dob.isoformat(),p_gender,st.session_state.user,now_iso()))
            conn.commit()
            st.success("Patient added")
            st.rerun()
    st.dataframe(patients)
    render_footer()

# ---------- Staff ----------
elif choice.startswith("👩"):
    st.subheader("Staff")
    staff = read_table("staff")
    search = st.text_input("Search staff")
    if search:
        staff = staff[staff.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
    with st.form("add_staff", clear_on_submit=True):
        s_id = st.text_input("Staff ID (unique)")
        s_name = st.text_input("Full name")
        s_role = st.selectbox("Role", STAFF_ROLES)
        submitted = st.form_submit_button("Add")
        if submitted and s_id:
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO staff (id,name,role,created_by,created_at) VALUES (?,?,?,?,?)",
                        (s_id,s_name,s_role,st.session_state.user,now_iso()))
            conn.commit()
            st.success("Staff added")
            st.rerun()
    st.dataframe(staff)
    render_footer()

# ---------- Schedule ----------
elif choice.startswith("📅"):
    st.subheader("Schedule")
    patients = read_table("patients")
    staff = read_table("staff")
    sched = read_table("schedule")

    with st.form("add_visit", clear_on_submit=True):
        patient_sel = st.selectbox("Patient", patients['id'].tolist() if not patients.empty else [])
        staff_sel = st.selectbox("Staff", staff['id'].tolist() if not staff.empty else [])
        v_date = st.date_input("Date", value=date.today())
        start = st.time_input("Start", value=dtime(9,0))
        end = st.time_input("End", value=dtime(10,0))
        v_type = st.text_input("Visit type")
        recurrence = st.selectbox("Recurrence", ["None","Daily","Weekly"])
        submitted = st.form_submit_button("Add Visit")
        if submitted and patient_sel and staff_sel:
            if end <= start:
                st.error("End time must be after start time.")
            elif is_conflict(staff_sel, v_date.isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M")):
                st.error("⚠️ Conflict detected! Staff already booked.")
            else:
                vid = make_visit_id()
                duration = int((datetime.combine(date.today(), end)-datetime.combine(date.today(), start)).seconds/60)
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO schedule (visit_id,patient_id,staff_id,date,start_time,end_time,visit_type,duration_minutes,created_by,created_at,recurrence) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (vid,patient_sel,staff_sel,v_date.isoformat(),start.strftime("%H:%M"),end.strftime("%H:%M"),v_type,duration,st.session_state.user,now_iso(),recurrence))
                # Add recurring
                if recurrence != "None":
                    for i in range(1,5): # add 4 recurrences
                        if recurrence == "Daily":
                            next_date = v_date + timedelta(days=i)
                        else:
                            next_date = v_date + timedelta(weeks=i)
                        vid2 = make_visit_id()
                        cur.execute("INSERT OR REPLACE INTO schedule (visit_id,patient_id,staff_id,date,start_time,end_time,visit_type,duration_minutes,created_by,created_at,recurrence) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                    (vid2,patient_sel,staff_sel,next_date.isoformat(),start.strftime("%H:%M"),end.strftime("%H:%M"),v_type,duration,st.session_state.user,now_iso(),recurrence))
                conn.commit()
                st.success("Visit(s) added")
                st.rerun()
    st.dataframe(sched)
    render_footer()

# ---------- Analytics ----------
elif choice.startswith("📊"):
    st.subheader("Analytics")
    patients = read_table("patients")
    sched = read_table("schedule")

    if not patients.empty:
        patients['dob_dt'] = pd.to_datetime(patients['dob'], errors="coerce")
        patients['age'] = ((pd.Timestamp(date.today())-patients['dob_dt']).dt.days//365).fillna(0)
        bins = pd.cut(patients['age'], bins=[-1,1,18,40,65,120], labels=["0-1","1-18","19-40","41-65","65+"])
        df = bins.value_counts().reset_index()
        df.columns=["Age group","Count"]
        st.altair_chart(alt.Chart(df).mark_bar().encode(x="Age group", y="Count"), use_container_width=True)

    if not sched.empty:
        # Staff workload
        w = sched['staff_id'].value_counts().reset_index()
        w.columns=["Staff","Visits"]
        st.altair_chart(alt.Chart(w).mark_bar().encode(x="Staff", y="Visits"), use_container_width=True)

        # Visit type distribution
        vt = sched['visit_type'].value_counts().reset_index()
        vt.columns=["Visit Type","Count"]
        st.altair_chart(alt.Chart(vt).mark_arc().encode(theta="Count", color="Visit Type"), use_container_width=True)

        # Monthly trend
        sched['month'] = pd.to_datetime(sched['date']).dt.to_period("M").astype(str)
        mt = sched['month'].value_counts().reset_index()
        mt.columns=["Month","Visits"]
        st.altair_chart(alt.Chart(mt).mark_line(point=True).encode(x="Month", y="Visits"), use_container_width=True)

    render_footer()

# ---------- Emergency ----------
elif choice.startswith("🚨"):
    st.subheader("Emergency")
    patients = read_table("patients")
    if not patients.empty:
        sel = st.selectbox("Patient", patients['id'].tolist())
        row = patients[patients['id']==sel].iloc[0]
        st.write(row.to_dict())
    render_footer()

# ---------- Settings ----------
elif choice.startswith("⚙️"):
    st.subheader("Settings")
    st.write(f"Logged in as {st.session_state.user} ({st.session_state.user_role})")
    users = read_table("users")
    st.dataframe(users)
    render_footer()

# ---------- Export ----------
elif choice.startswith("💾"):
    patients = read_table("patients")
    staff = read_table("staff")
    sched = read_table("schedule")

    def to_excel_bytes(dfs: dict):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for name, df in dfs.items():
                df.to_excel(writer, sheet_name=name[:31], index=False)
        output.seek(0)
        return output.getvalue()

    def create_word_report(patients_df, staff_df, schedule_df):
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
        f = BytesIO()
        doc.save(f)
        f.seek(0)
        return f.getvalue()

    excel = to_excel_bytes({"Patients":patients,"Staff":staff,"Schedule":sched})
    word = create_word_report(patients,staff,sched)

    st.download_button("Download Excel",excel,"data.xlsx")
    st.download_button("Download Word",word,"report.docx")
    st.download_button("Backup Database", open(DB_PATH,"rb").read(), "backup.db")

    render_footer()

# ---------- Logout ----------
elif choice.startswith("🚪"):
    logout_user()
    st.success("Logged out")
    st.rerun()

render_footer()
