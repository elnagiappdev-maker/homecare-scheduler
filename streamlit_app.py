# Smart Homecare Scheduler - Streamlit App
# ALL RIGHTS RESERVED TO Dr. Yousra Abdelatti.
# Developed by Dr. Mohammedelnagi Mohammed
# Cleaned and ready to paste into GitHub / Streamlit

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date, time as dtime
from io import BytesIO
import altair as alt
import os
import hashlib

# ---------------------------
# Configuration / Constants
# ---------------------------
DB_PATH = "homecare_scheduler.db"  # SQLite DB stored next to the app
APP_TITLE = "Smart Homecare Scheduler (24/7)"
RELAXING_BG = "#E8F6F3"
ACCENT = "#5DADE2"

# ---------------------------
# Utility functions
# ---------------------------

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Users table (simple auth). Passwords stored as sha256 hashes for minimal safety.
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            role TEXT
        )
    ''')

    # Patients table
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
            notes TEXT
        )
    ''')

    # Staff table (doctors, nurses, pt, rt, caregivers)
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
            notes TEXT
        )
    ''')

    # Schedule table
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
            created_at TEXT
        )
    ''')

    # Seed admin user if none
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    if count == 0:
        admin_pw = hashlib.sha256("1234".encode()).hexdigest()
        cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role) VALUES (?,?,?)",
                    ("admin", admin_pw, "admin"))
        clinician_pw = hashlib.sha256("abcd".encode()).hexdigest()
        cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role) VALUES (?,?,?)",
                    ("doctor", clinician_pw, "doctor"))
    conn.commit()
    conn.close()


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ---------------------------
# Persistence helpers
# ---------------------------

init_db()
conn = get_db_connection()


@st.cache_data(show_spinner=False)
def read_table(name: str):
    try:
        return pd.read_sql_query(f"SELECT * FROM {name}", conn)
    except Exception:
        return pd.DataFrame()


# ---------------------------
# UI helpers
# ---------------------------

def inject_css():
    st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(180deg, {RELAXING_BG} 0%, white 100%);
    }}
    .big-title {{
        font-size:32px;
        font-weight:700;
        color: #0b3d91;
    }}
    .card {{
        background: white;
        padding: 12px;
        border-radius: 12px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.06);
    }}
    </style>
    """, unsafe_allow_html=True)


def make_visit_id():
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM schedule")
    count = cur.fetchone()[0] + 1
    return f"V{count:05d}"


def overlaps(start_a, end_a, start_b, end_b):
    # times are datetime.time or strings 'HH:MM'
    if isinstance(start_a, str):
        start_a = datetime.strptime(start_a, "%H:%M").time()
    if isinstance(end_a, str):
        end_a = datetime.strptime(end_a, "%H:%M").time()
    if isinstance(start_b, str):
        start_b = datetime.strptime(start_b, "%H:%M").time()
    if isinstance(end_b, str):
        end_b = datetime.strptime(end_b, "%H:%M").time()
    return (start_a < end_b) and (start_b < end_a)


# ---------------------------
# App Layout and Logic
# ---------------------------

st.set_page_config(page_title=APP_TITLE, layout="wide")
inject_css()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.user_role = None

# --- Login ---
if not st.session_state.logged_in:
    st.markdown('<div class="big-title">Smart Homecare Scheduler Login</div>', unsafe_allow_html=True)
    st.write("### Please log in to continue")
    username = st.text_input("Username", key="login_user")
    password = st.text_input("Password", type="password", key="login_pw")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            cur = conn.cursor()
            cur.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            if row and hash_pw(password) == row[0]:
                st.session_state.logged_in = True
                st.session_state.user = username
                st.session_state.user_role = row[1]
                st.success(f"Welcome back, {username} ({row[1]})")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    with col2:
        st.write("If you don't have an account ask the administrator to create one. For demo, use admin/1234 or doctor/abcd.")
    st.stop()

# --- Main App ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/8/88/Patient_icon.svg", width=100)
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
    st.write("Upcoming visits (next 14 days):")
    if len(schedule_df) > 0:
        schedule_df['date_dt'] = pd.to_datetime(schedule_df['date'])
        upcoming = schedule_df[schedule_df['date_dt'] >= pd.Timestamp(date.today())].sort_values(['date','start_time']).head(50)
        st.dataframe(upcoming[['visit_id','patient_id','staff_id','date','start_time','end_time','visit_type','priority']])
    else:
        st.info("No visits scheduled yet.")

# ---------- Patients ----------
elif choice == "Patients":
    st.subheader("Manage Patients")
    patients_df = read_table("patients")

    with st.expander("Add new patient"):
        p_id = st.text_input("Patient ID (unique)")
        p_name = st.text_input("Full name")
        p_dob = st.date_input("Date of birth", value=date(1950,1,1))
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
        if st.button("Add patient"):
            if p_id.strip() == "":
                st.error("Patient ID required and must be unique")
            else:
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO patients (id,name,dob,gender,phone,email,address,emergency_contact,insurance_provider,insurance_number,allergies,medications,diagnosis,equipment_required,mobility,care_plan,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (p_id,p_name,p_dob.isoformat(),p_gender,p_phone,p_email,p_address,p_emergency,p_ins_provider,p_ins_number,p_allergies,p_meds,p_diag,p_equip,p_mobility,p_careplan,p_notes))
                conn.commit()
                st.success("Patient saved")
                st.experimental_rerun()

    st.markdown("---")
    st.write("Existing patients:")
    st.dataframe(patients_df)

    with st.expander("Edit / Delete patient"):
        if len(patients_df) == 0:
            st.info("No patients to edit")
        else:
            sel = st.selectbox("Select patient to edit", patients_df['id'].tolist())
            row = patients_df[patients_df['id'] == sel].iloc[0]
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name", value=row['name'])
                dob = st.date_input("DOB", value=pd.to_datetime(row['dob']).date() if pd.notna(row['dob']) else date(1950,1,1))
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
                if st.button("Save changes"):
                    cur = conn.cursor()
                    cur.execute("UPDATE patients SET name=?,dob=?,gender=?,phone=?,email=?,address=?,emergency_contact=?,allergies=?,medications=?,diagnosis=?,equipment_required=?,mobility=?,care_plan=?,notes=? WHERE id=?",
                                (name,dob.isoformat(),gender,phone,email,address,emergency,allergies,meds,diagnosis,equipment,mobility,careplan,notes,sel))
                    conn.commit()
                    st.success("Patient updated")
                    st.experimental_rerun()
            with col2:
                if st.button("Delete patient"):
                    cur = conn.cursor()
                    cur.execute("DELETE FROM patients WHERE id=?", (sel,))
                    conn.commit()
                    st.success("Patient deleted")
                    st.experimental_rerun()

# ---------- Staff ----------
elif choice == "Staff":
    st.subheader("Manage Staff (doctors, nurses, PT, RT, caregivers)")
    staff_df = read_table("staff")

    with st.expander("Add staff member"):
        s_id = st.text_input("Staff ID (unique)")
        s_name = st.text_input("Full name")
        s_role = st.selectbox("Role", ["Doctor","Nurse","Physiotherapist","Respiratory Therapist","Caregiver","Other"]) 
        s_license = st.text_input("License / registration number")
        s_specialties = st.text_input("Specialties (comma separated)")
        s_phone = st.text_input("Phone")
        s_email = st.text_input("Email")
        s_availability = st.text_area("Availability (e.g. Mon-Fri 08:00-16:00; Weekends off)")
        s_notes = st.text_area("Notes")
        if st.button("Add staff"):
            if s_id.strip() == "":
                st.error("Staff ID required")
            else:
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO staff (id,name,role,license_number,specialties,phone,email,availability,notes) VALUES (?,?,?,?,?,?,?,?,?)",
                            (s_id,s_name,s_role,s_license,s_specialties,s_phone,s_email,s_availability,s_notes))
                conn.commit()
                st.success("Staff saved")
                st.experimental_rerun()

    st.markdown("---")
    st.dataframe(staff_df)

    with st.expander("Edit / Delete staff"):
        if len(staff_df) == 0:
            st.info("No staff yet")
        else:
            sel = st.selectbox("Select staff", staff_df['id'].tolist())
            row = staff_df[staff_df['id'] == sel].iloc[0]
            name = st.text_input("Name", value=row['name'])
            role = st.selectbox("Role", ["Doctor","Nurse","Physiotherapist","Respiratory Therapist","Caregiver","Other"]) 
            license_num = st.text_input("License", value=row['license_number'])
            specialties = st.text_input("Specialties", value=row['specialties'])
            phone = st.text_input("Phone", value=row['phone'])
            email = st.text_input("Email", value=row['email'])
            availability = st.text_area("Availability", value=row['availability'])
            notes = st.text_area("Notes", value=row['notes'])
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save staff"):
                    cur = conn.cursor()
                    cur.execute("UPDATE staff SET name=?,role=?,license_number=?,specialties=?,phone=?,email=?,availability=?,notes=? WHERE id=?",
                                (name,role,license_num,specialties,phone,email,availability,notes,sel))
                    conn.commit()
                    st.success("Saved")
                    st.experimental_rerun()
            with col2:
                if st.button("Delete staff"):
                    cur = conn.cursor()
                    cur.execute("DELETE FROM staff WHERE id=?", (sel,))
                    conn.commit()
                    st.success("Deleted")
                    st.experimental_rerun()

# ---------- Schedule ----------
elif choice == "Schedule":
    st.subheader("Scheduling & Visits")
    patients_df = read_table("patients")
    staff_df = read_table("staff")
    schedule_df = read_table("schedule")

    col1, col2 = st.columns([2,1])
    with col1:
        st.markdown("### Create visit")
        if len(patients_df) == 0:
            st.warning("Add patients first")
        if len(staff_df) == 0:
            st.warning("Add staff first")

        patient_sel = st.selectbox("Patient", patients_df['id'].tolist() if len(patients_df)>0 else [])
        staff_sel = st.selectbox("Assign staff", staff_df['id'].tolist() if len(staff_df)>0 else [])
        visit_date = st.date_input("Date", value=date.today())
        start = st.time_input("Start", value=dtime(hour=9,minute=0))
        end = st.time_input("End", value=(datetime.combine(date.today(), start) + timedelta(minutes=60)).time())
        visit_type = st.selectbox("Visit type", ["Home visit","Telehealth","Wound care","Medication administration","Physiotherapy","Respiratory therapy","Assessment","Other"]) 
        priority = st.selectbox("Priority", ["Low","Normal","High","Urgent"]) 
        duration_minutes = int((datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).seconds / 60)
        diagnosis = st.text_area("Diagnosis (brief)")
        v_notes = st.text_area("Visit notes / instructions")
        recurring = st.selectbox("Recurring", ["None","Daily","Weekly","Monthly"]) 
        occurrences = 1
        if recurring != "None":
            occurrences = st.number_input("Occurrences", min_value=1, max_value=365, value=4)

        if st.button("Schedule visit"):
            if patient_sel == "" or staff_sel == "":
                st.error("Patient and staff must be selected")
            else:
                # conflict detection for the staff on that date
                conflict = False
                if len(schedule_df) > 0:
                    same_day = schedule_df[schedule_df['date'] == visit_date.isoformat()]
                    for _, r in same_day.iterrows():
                        if r['staff_id'] == staff_sel:
                            if overlaps(r['start_time'], r['end_time'], start.strftime("%H:%M"), end.strftime("%H:%M")):
                                conflict = True
                                break
                if conflict:
                    st.error("Schedule conflict: selected staff already has a visit overlapping that time.")
                else:
                    cur = conn.cursor()
                    base_date = visit_date
                    added = 0
                    for i in range(occurrences):
                        vid = make_visit_id()
                        d_iso = base_date.isoformat()
                        cur.execute("INSERT OR REPLACE INTO schedule (visit_id,patient_id,staff_id,date,start_time,end_time,visit_type,duration_minutes,priority,diagnosis,notes,recurring_rule,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                    (vid, patient_sel, staff_sel, d_iso, start.strftime("%H:%M"), end.strftime("%H:%M"), visit_type, duration_minutes, priority, diagnosis, v_notes, recurring if recurring!='None' else None, datetime.utcnow().isoformat()))
                        conn.commit()
                        added += 1
                        # advance base_date
                        if recurring == 'Daily':
                            base_date = base_date + timedelta(days=1)
                        elif recurring == 'Weekly':
                            base_date = base_date + timedelta(weeks=1)
                        elif recurring == 'Monthly':
                            base_date = base_date + timedelta(days=30)  # approximate
                    st.success(f"Scheduled {added} visit(s).")
                    st.experimental_rerun()

    with col2:
        st.markdown("### Upcoming / Search")
        schedule_df = read_table("schedule")
        if len(schedule_df) == 0:
            st.info("No scheduled visits")
        else:
            filter_staff = st.selectbox("Filter by staff", ["All"] + schedule_df['staff_id'].unique().tolist())
            filter_patient = st.selectbox("Filter by patient", ["All"] + schedule_df['patient_id'].unique().tolist())
            df_show = schedule_df.copy()
            if filter_staff != "All":
                df_show = df_show[df_show['staff_id'] == filter_staff]
            if filter_patient != "All":
                df_show = df_show[df_show['patient_id'] == filter_patient]
            df_show['date_dt'] = pd.to_datetime(df_show['date'])
            df_show = df_show.sort_values(['date','start_time'])
            st.dataframe(df_show[['visit_id','patient_id','staff_id','date','start_time','end_time','visit_type','priority']].head(200))

# ---------- Analytics ----------
elif choice == "Analytics":
    st.subheader("Analytics")
    schedule_df = read_table("schedule")
    staff_df = read_table("staff")
    if len(schedule_df) == 0:
        st.info("No data for analytics")
    else:
        # Visits per staff
        visits_staff = schedule_df.groupby('staff_id').size().reset_index(name='visits')
        chart = alt.Chart(visits_staff).mark_bar().encode(
            x=alt.X('staff_id:N', sort='-y'),
            y='visits:Q'
        )
        st.markdown("**Visits per staff**")
        st.altair_chart(chart, use_container_width=True)

        # Visits over time
        schedule_df['date_dt'] = pd.to_datetime(schedule_df['date'])
        visits_day = schedule_df.groupby('date_dt').size().reset_index(name='visits')
        line = alt.Chart(visits_day).mark_line(point=True).encode(x='date_dt:T', y='visits:Q')
        st.markdown("**Visits over time**")
        st.altair_chart(line, use_container_width=True)

# ---------- Emergency ----------
elif choice == "Emergency":
    st.subheader("Emergency contacts & quick actions")
    patients_df = read_table("patients")
    if len(patients_df) == 0:
        st.info("No patients yet")
    else:
        show = patients_df[['id','name','emergency_contact','phone','address']].rename(columns={'id':'Patient ID','name':'Name'})
        st.dataframe(show)

# ---------- Settings ----------
elif choice == "Settings":
    st.subheader("Settings & Users")
    users_df = read_table("users")
    st.markdown("**Existing users**")
    st.dataframe(users_df)

    with st.expander("Create new user"):
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type='password')
        new_role = st.selectbox("Role", ["admin","doctor","nurse","caregiver","other"]) 
        if st.button("Create user"):
            if new_username.strip() == "" or new_password.strip() == "":
                st.error("Username and password required")
            else:
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO users (username,password_hash,role) VALUES (?,?,?)",
                            (new_username, hashlib.sha256(new_password.encode()).hexdigest(), new_role))
                conn.commit()
                st.success("User created")
                st.experimental_rerun()

    with st.expander("Reset database (CAUTION)"):
        if st.button("Reset DB (Drop all data)"):
            if st.text_input("Type 'CONFIRM' to proceed") == 'CONFIRM':
                conn.close()
                os.remove(DB_PATH)
                init_db()
                st.success("Database reset")
                st.experimental_rerun()
            else:
                st.warning("Type CONFIRM in the box to enable reset")

# ---------- Export & Backup ----------
elif choice == "Export & Backup":
    st.subheader("Export & Backup")
    patients_df = read_table("patients")
    staff_df = read_table("staff")
    schedule_df = read_table("schedule")

    st.markdown("### Download CSVs")
    if st.button("Download patients CSV"):
        csv = patients_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download patients.csv", data=csv, file_name='patients.csv', mime='text/csv')
    if st.button("Download staff CSV"):
        csv = staff_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download staff.csv", data=csv, file_name='staff.csv', mime='text/csv')
    if st.button("Download schedule CSV"):
        csv = schedule_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download schedule.csv", data=csv, file_name='schedule.csv', mime='text/csv')

    st.markdown("### Download Excel workbook")
    if st.button("Download all as Excel"):
        towrite = BytesIO()
        with pd.ExcelWriter(towrite, engine='openpyxl') as writer:
            patients_df.to_excel(writer, sheet_name='patients', index=False)
            staff_df.to_excel(writer, sheet_name='staff', index=False)
            schedule_df.to_excel(writer, sheet_name='schedule', index=False)
        towrite.seek(0)
        st.download_button("Download workbook", data=towrite, file_name='homecare_export.xlsx')

# ---------- Logout ----------
elif choice == "Logout":
    st.subheader("Logout")
    if st.button("Logout now"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.user_role = None
        st.experimental_rerun()

# Footer
st.markdown("---")
st.caption("ALL RIGHTS RESERVED TO Dr. Yousra Abdelatti. Developed by Dr. Mohammedelnagi Mohammed.")
