# app.py
# Smart Homecare Scheduler (Streamlit App)
# ----------------------------------------
# All Rights Reserved © Dr. Yousra Abdelatti

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
import tempfile, os

# ---------------------------
# Config
# ---------------------------
DB_PATH = "homecare_scheduler.db"
APP_TITLE = "Smart Homecare Scheduler (24/7)"
RELAXING_BG = "#E8F6F3"
STAFF_ROLES = ["Specialist", "GP", "Nurse", "RT", "PT", "Care Giver"]

# ---------------------------
# DB Setup
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()
def now_iso(): return datetime.utcnow().isoformat()

def init_db():
    conn = get_conn(); cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, password_hash TEXT, role TEXT, created_at TEXT)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS patients (
        id TEXT PRIMARY KEY, name TEXT, dob TEXT, gender TEXT, phone TEXT, address TEXT,
        emergency_contact TEXT, diagnosis TEXT, pmh TEXT, allergies TEXT, medications TEXT,
        physician TEXT, care_type TEXT, care_frequency TEXT, care_needs TEXT,
        mobility TEXT, cognition TEXT, nutrition TEXT, psychosocial TEXT, notes TEXT,
        created_by TEXT, created_at TEXT)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS staff (
        id TEXT PRIMARY KEY, name TEXT, role TEXT, phone TEXT, email TEXT,
        availability TEXT, notes TEXT, created_by TEXT, created_at TEXT)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS schedule (
        visit_id TEXT PRIMARY KEY, patient_id TEXT, staff_id TEXT, date TEXT,
        start_time TEXT, end_time TEXT, visit_type TEXT, duration_minutes INTEGER,
        priority TEXT, notes TEXT, created_by TEXT, created_at TEXT)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS vitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, date TEXT,
        bp TEXT, hr TEXT, temp TEXT, resp TEXT, o2sat TEXT, weight TEXT, notes TEXT)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS visit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, date TEXT,
        caregiver TEXT, visit_type TEXT, services TEXT, response TEXT, signature TEXT)""")

    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute("INSERT INTO users VALUES (?,?,?,?)", ("admin", hash_pw("1234"), "admin", now_iso()))
        cur.execute("INSERT INTO users VALUES (?,?,?,?)", ("doctor", hash_pw("abcd"), "doctor", now_iso()))

    conn.commit(); conn.close()
init_db()

# ---------------------------
# Helpers
# ---------------------------
@st.cache_data(show_spinner=False)
def read_table(name): return pd.read_sql_query(f"SELECT * FROM {name}", get_conn())

def inject_css():
    st.markdown(f"""
    <style>
    .stApp {{ background: linear-gradient(180deg, {RELAXING_BG} 0%, white 100%); }}
    .big-title {{ font-size:28px; font-weight:700; color: #0b3d91; }}
    .footer {{ font-size: 14px; text-align: center; margin-top: 20px; font-weight: bold; color: purple; }}
    </style>
    """, unsafe_allow_html=True)

def make_visit_id():
    cur=get_conn().cursor(); cur.execute("SELECT COUNT(*) as c FROM schedule")
    return f"V{cur.fetchone()['c']+1:05d}"

def render_footer():
    st.markdown("---")
    st.markdown("<div class='footer'>All Rights Reserved © Dr. Yousra Abdelatti</div>", unsafe_allow_html=True)

# ---------------------------
# Auth
# ---------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in, st.session_state.user, st.session_state.role = False, None, None

def login(u,p):
    cur=get_conn().cursor(); cur.execute("SELECT password_hash, role FROM users WHERE username=?",(u,))
    row=cur.fetchone()
    if row and hash_pw(p)==row[0]:
        st.session_state.logged_in=True; st.session_state.user=u; st.session_state.role=row[1]; return True
    return False
def logout(): st.session_state.logged_in=False; st.session_state.user=None; st.session_state.role=None

# ---------------------------
# Word Export
# ---------------------------
def create_word_report(patients, staff, sched, charts=None):
    doc = Document(); doc.add_heading(APP_TITLE, level=1)
    doc.add_paragraph("Generated: "+datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    for title,df in [("Patients",patients),("Staff",staff),("Schedule",sched)]:
        doc.add_heading(title, level=2)
        if not df.empty:
            t=doc.add_table(rows=1, cols=len(df.columns))
            for i,c in enumerate(df.columns): t.rows[0].cells[i].text=c
            for _,r in df.iterrows(): row_cells=t.add_row().cells; [row_cells[i].__setattr__("text",str(r[c])) for i,c in enumerate(df.columns)]
        else: doc.add_paragraph("No data")
    if charts:
        for title,img in charts.items():
            doc.add_page_break(); doc.add_heading(title, level=2)
            with tempfile.NamedTemporaryFile(delete=False,suffix=".png") as tmp:
                tmp.write(img); tmp.flush(); doc.add_picture(tmp.name,width=Inches(5)); os.unlink(tmp.name)
    f=BytesIO(); doc.save(f); f.seek(0); return f.getvalue()

# ---------------------------
# Layout
# ---------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide"); inject_css()

if not st.session_state.logged_in:
    st.markdown('<div class="big-title">Login</div>', unsafe_allow_html=True)
    u=st.text_input("Username"); p=st.text_input("Password",type="password")
    if st.button("Login"): st.rerun() if login(u,p) else st.error("Invalid credentials")
    st.markdown("<div class='footer'>All Rights Reserved © Dr. Yousra Abdelatti</div>", unsafe_allow_html=True)
    st.stop()

menu=["Dashboard","Patients","Staff","Schedule","Analytics","Emergency","Settings","Export & Backup","Logout"]
choice=st.sidebar.radio("Go to",menu); st.markdown(f"<div class='big-title'>{APP_TITLE}</div>",unsafe_allow_html=True)

# ---------- Patients ----------
if choice=="Patients":
    st.subheader("🏥 Home Care Patient File")
    patients=read_table("patients")

    with st.expander("Add New Patient"):
        with st.form("add_patient",clear_on_submit=True):
            pid=st.text_input("Patient ID (unique)")
            name=st.text_input("Name"); dob=st.date_input("Date of Birth",min_value=date(1900,1,1))
            gender=st.selectbox("Gender",["Female","Male","Other"])
            phone=st.text_input("Contact Number"); addr=st.text_area("Address")
            emerg=st.text_input("Emergency Contact"); diag=st.text_area("Primary Diagnosis")
            pmh=st.text_area("Past Medical History"); allergies=st.text_area("Allergies")
            meds=st.text_area("Medications"); physician=st.text_input("Physician")
            care_type=st.text_input("Type of Care"); freq=st.text_input("Frequency"); needs=st.text_area("Specific Needs")
            mobility=st.selectbox("Mobility",["Independent","Assisted","Wheelchair","Bedbound"])
            cog=st.text_area("Cognition"); nutri=st.text_area("Nutrition"); psycho=st.text_area("Psychosocial")
            notes=st.text_area("Notes")
            submitted=st.form_submit_button("Save Patient")
            if submitted and pid:
                cur=get_conn().cursor()
                cur.execute("""INSERT OR REPLACE INTO patients 
                (id,name,dob,gender,phone,address,emergency_contact,diagnosis,pmh,allergies,medications,physician,
                 care_type,care_frequency,care_needs,mobility,cognition,nutrition,psychosocial,notes,created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,name,dob.isoformat(),gender,phone,addr,emerg,diag,pmh,allergies,meds,physician,
                 care_type,freq,needs,mobility,cog,nutri,psycho,notes,st.session_state.user,now_iso()))
                get_conn().commit(); st.success("Patient saved"); st.rerun()
    st.dataframe(patients)

    # Vitals
    st.markdown("### Vital Signs Record")
    v=read_table("vitals")
    if not patients.empty:
        with st.form("add_vital",clear_on_submit=True):
            sel=st.selectbox("Patient",patients['id'].tolist())
            d=st.date_input("Date",value=date.today()); bp=st.text_input("BP"); hr=st.text_input("HR")
            temp=st.text_input("Temp"); resp=st.text_input("Resp"); o2=st.text_input("O2 Sat")
            wt=st.text_input("Weight"); notes=st.text_area("Notes")
            if st.form_submit_button("Save Vital"):
                cur=get_conn().cursor()
                cur.execute("INSERT INTO vitals (patient_id,date,bp,hr,temp,resp,o2sat,weight,notes) VALUES (?,?,?,?,?,?,?,?,?)",
                            (sel,d.isoformat(),bp,hr,temp,resp,o2,wt,notes)); get_conn().commit(); st.success("Saved"); st.rerun()
    st.dataframe(v)

    # Visit log
    st.markdown("### Visit Log")
    vl=read_table("visit_log")
    if not patients.empty:
        with st.form("add_log",clear_on_submit=True):
            sel=st.selectbox("Patient ",patients['id'].tolist())
            d=st.date_input("Date",value=date.today()); care=st.text_input("Caregiver")
            vt=st.text_input("Visit Type"); serv=st.text_area("Services Provided")
            resp=st.text_area("Patient Response"); sig=st.text_input("Signature")
            if st.form_submit_button("Save Log"):
                cur=get_conn().cursor()
                cur.execute("INSERT INTO visit_log (patient_id,date,caregiver,visit_type,services,response,signature) VALUES (?,?,?,?,?,?,?)",
                            (sel,d.isoformat(),care,vt,serv,resp,sig)); get_conn().commit(); st.success("Saved"); st.rerun()
    st.dataframe(vl)

    render_footer()

# ---------- Staff ----------
elif choice=="Staff":
    st.subheader("Staff"); staff=read_table("staff")
    with st.form("add_staff",clear_on_submit=True):
        sid=st.text_input("Staff ID"); nm=st.text_input("Name"); role=st.selectbox("Role",STAFF_ROLES)
        phone=st.text_input("Phone"); email=st.text_input("Email"); avail=st.text_area("Availability")
        notes=st.text_area("Notes")
        if st.form_submit_button("Save Staff") and sid:
            cur=get_conn().cursor()
            cur.execute("INSERT OR REPLACE INTO staff (id,name,role,phone,email,availability,notes,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (sid,nm,role,phone,email,avail,notes,st.session_state.user,now_iso()))
            get_conn().commit(); st.success("Saved"); st.rerun()
    st.dataframe(staff); render_footer()

# ---------- Schedule ----------
elif choice=="Schedule":
    st.subheader("Schedule"); patients=read_table("patients"); staff=read_table("staff"); sched=read_table("schedule")
    with st.form("add_visit",clear_on_submit=True):
        pat=st.selectbox("Patient",patients['id'].tolist() if not patients.empty else [])
        stf=st.selectbox("Staff",staff['id'].tolist() if not staff.empty else [])
        d=st.date_input("Date",value=date.today()); s=st.time_input("Start",dtime(9,0)); e=st.time_input("End",dtime(10,0))
        vtype=st.text_input("Visit Type"); pri=st.selectbox("Priority",["Low","Normal","High","Critical"]); notes=st.text_area("Notes")
        if st.form_submit_button("Save Visit") and pat and stf:
            vid=make_visit_id(); dur=int((datetime.combine(date.today(),e)-datetime.combine(date.today(),s)).seconds/60)
            cur=get_conn().cursor()
            cur.execute("""INSERT OR REPLACE INTO schedule VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (vid,pat,stf,d.isoformat(),s.strftime("%H:%M"),e.strftime("%H:%M"),vtype,dur,pri,notes,st.session_state.user,now_iso()))
            get_conn().commit(); st.success("Visit saved"); st.rerun()
    st.dataframe(sched); render_footer()

# ---------- Analytics ----------
elif choice=="Analytics":
    st.subheader("Analytics"); patients=read_table("patients"); sched=read_table("schedule")
    if not patients.empty:
        patients['dob_dt']=pd.to_datetime(patients['dob'],errors="coerce")
        patients['age']=((pd.Timestamp(date.today())-patients['dob_dt']).dt.days//365).fillna(0)
        bins=pd.cut(patients['age'],[-1,1,18,40,65,120],labels=["0-1","1-18","19-40","41-65","65+"])
        df=bins.value_counts().reset_index(); df.columns=["Age group","Count"]
        st.altair_chart(alt.Chart(df).mark_bar(color="#5DADE2").encode(x="Age group",y="Count"),use_container_width=True)
    if not sched.empty:
        w=sched['staff_id'].value_counts().reset_index(); w.columns=["Staff","Visits"]
        st.altair_chart(alt.Chart(w).mark_bar(color="#66c2a5").encode(x="Staff",y="Visits"),use_container_width=True)
    render_footer()

# ---------- Emergency ----------
elif choice=="Emergency":
    st.subheader("Emergency"); patients=read_table("patients")
    if not patients.empty:
        sel=st.selectbox("Patient",patients['id'].tolist()); row=patients[patients['id']==sel].iloc[0]; st.write(row.to_dict())
    render_footer()

# ---------- Settings ----------
elif choice=="Settings":
    st.subheader("Settings"); st.write(f"Logged in as {st.session_state.user} ({st.session_state.role})")
    users=read_table("users"); st.dataframe(users); render_footer()

# ---------- Export ----------
elif choice=="Export & Backup":
    st.subheader("Export & Backup"); patients=read_table("patients"); staff=read_table("staff"); sched=read_table("schedule")
    charts={}; 
    if not patients.empty:
        patients['dob_dt']=pd.to_datetime(patients['dob'],errors="coerce")
        patients['age']=((pd.Timestamp(date.today())-patients['dob_dt']).dt.days//365).fillna(0)
        bins=pd.cut(patients['age'],[-1,1,18,40,65,120],labels=["0-1","1-18","19-40","41-65","65+"])
        df=bins.value_counts().reset_index(); df.columns=["Age group","Count"]
        fig,ax=plt.subplots(); df.plot(kind="bar",x="Age group",y="Count",ax=ax,legend=False); buf=BytesIO(); plt.savefig(buf,format="png"); charts["Patients by Age"]=buf.getvalue(); buf.close()
    if not sched.empty:
        w=sched['staff_id'].value_counts().reset_index(); w.columns=["Staff","Visits"]
        fig,ax=plt.subplots(); w.plot(kind="bar",x="Staff",y="Visits",ax=ax,legend=False); buf=BytesIO(); plt.savefig(buf,format="png"); charts["Workload"]=buf.getvalue(); buf.close()
    word=create_word_report(patients,staff,sched,charts)
    st.download_button("Download Word Report",word,"homecare_report.docx")
    with open(DB_PATH,"rb") as f: st.download_button("Download DB",f.read(),DB_PATH)
    render_footer()

# ---------- Logout ----------
elif choice=="Logout": logout(); st.success("Logged out"); st.rerun()

