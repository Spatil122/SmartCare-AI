"""
SMARTCARE AI - Complete Streamlit application
Includes patient complaints, Ollama AI assistance, hospital dashboards,
hospital registration, and doctor / medical-service availability.

Beginner note:
- This app uses the existing smartcare.db database.
- New tables and columns are added safely; existing complaint records are kept.
- Ollama is optional. If it is unavailable, complaint registration still works.
"""

import os
import json
from pathlib import Path
import uuid
import random
import hashlib
import hmac
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta

import streamlit as st
import plotly.express as px


# ---------------------------------------------------------
# PAGE SETTINGS
# ---------------------------------------------------------

st.set_page_config(
    page_title="SMARTCARE AI",
    page_icon="🏥",
    layout="wide"
)

DB_PATH = str(Path(__file__).resolve().parent / "smartcare.db")

DEFAULT_MEDICAL_CATEGORIES = [
    "Dental",
    "Bone / Orthopaedics",
    "X-ray / Radiology",
    "General Medicine",
    "Cardiology",
    "Eye Care",
    "ENT",
    "Gynaecology",
    "Paediatrics",
]

COMPLAINT_CATEGORIES = {
    "English": [
        "Doctor Unavailable",
        "Medicine Unavailable",
        "Cleanliness Problem",
        "Water Problem",
        "Bed Unavailable",
        "Hospital Facilities Problem",
        "Staff Behaviour Problem",
        "Other",
    ],
    "Kannada": [
        "ವೈದ್ಯರು ಲಭ್ಯವಿಲ್ಲ",
        "ಔಷಧಿ ಲಭ್ಯವಿಲ್ಲ",
        "ಸ್ವಚ್ಛತೆ ಸಮಸ್ಯೆ",
        "ನೀರಿನ ಸಮಸ್ಯೆ",
        "ಹಾಸಿಗೆ ಲಭ್ಯವಿಲ್ಲ",
        "ಆಸ್ಪತ್ರೆ ಸೌಲಭ್ಯ ಸಮಸ್ಯೆ",
        "ಸಿಬ್ಬಂದಿ ವರ್ತನೆ ಸಮಸ್ಯೆ",
        "ಇತರೆ",
    ],
    "Hindi": [
        "डॉक्टर उपलब्ध नहीं",
        "दवाइयां उपलब्ध नहीं",
        "सफाई की समस्या",
        "पानी की समस्या",
        "बेड उपलब्ध नहीं",
        "अस्पताल की सुविधाओं की समस्या",
        "कर्मचारियों के व्यवहार की समस्या",
        "अन्य",
    ],
}


# ---------------------------------------------------------
# DATABASE CONNECTION AND SAFE MIGRATIONS
# ---------------------------------------------------------

def get_connection():
    """Open the SQLite database and ensure required tables exist."""
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def column_exists(connection, table_name, column_name):
    """Check whether a database column already exists."""
    columns = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()
    return any(column["name"] == column_name for column in columns)


def initialize_database():
    """Create tables and add missing columns without deleting old records."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            hospital TEXT,
            category TEXT,
            complaint TEXT,
            status TEXT,
            date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            role TEXT,
            hospital TEXT,
            email TEXT,
            password TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            name TEXT PRIMARY KEY,
            district TEXT,
            location TEXT
        )
    """)

    # AI results are stored separately from the patient's selected category.
    ai_columns = {
        "ai_category": "TEXT",
        "ai_summary": "TEXT",
        "ai_priority": "TEXT",
        "ai_urgent": "INTEGER DEFAULT 0",
        "ai_reason": "TEXT",
        "ai_review_required": "INTEGER DEFAULT 1",
    }
    for column_name, column_type in ai_columns.items():
        if not column_exists(connection, "complaints", column_name):
            cursor.execute(
                f"ALTER TABLE complaints ADD COLUMN {column_name} {column_type}"
            )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medical_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctor_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hospital TEXT NOT NULL,
            category TEXT NOT NULL,
            record_type TEXT NOT NULL DEFAULT 'Doctor',
            service_name TEXT DEFAULT '',
            availability TEXT NOT NULL DEFAULT 'Available',
            consultation_days TEXT DEFAULT '',
            start_time TEXT DEFAULT '',
            end_time TEXT DEFAULT '',
            next_available TEXT DEFAULT '',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute(
        "INSERT OR IGNORE INTO hospitals(name, district, location) VALUES (?, ?, ?)",
        ("City General Hospital", "Kalaburagi", "Main City")
    )

    for category in DEFAULT_MEDICAL_CATEGORIES:
        cursor.execute(
            "INSERT OR IGNORE INTO medical_categories(name, active) VALUES (?, 1)",
            (category,)
        )

    # Keep the original demo accounts for continuity with the old application.
    # Change these demo passwords before making the app public.
    demo_accounts = [
        ("district", "District Commissioner", "ALL",
         "district@example.com", "District@123"),
        ("hospital", "Hospital Admin", "City General Hospital",
         "hospital@example.com", "Hospital@123"),
    ]
    for username, role, hospital, email, password in demo_accounts:
        cursor.execute(
            "INSERT OR IGNORE INTO users(username, role, hospital, email, password) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, role, hospital, email, hash_password(password))
        )

    connection.commit()
    connection.close()


def hash_password(password):
    """Create a salted PBKDF2 password hash using Python's standard library."""
    iterations = 310000
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest}"


def verify_password(password, stored_value):
    """Verify new PBKDF2 hashes and older SHA-256 / plain-text records."""
    if not stored_value:
        return False

    if stored_value.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_hex, expected = stored_value.split("$", 3)
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
            ).hex()
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    # Older versions used an unsalted SHA-256 hash or plain-text password.
    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(stored_value, legacy_hash) or stored_value == password


def normalize_role(role):
    """Map older administrator role labels to the current role names."""
    cleaned = (role or "").strip().lower()
    if cleaned in {
        "district commissioner", "district admin", "district administrator",
        "main admin", "main administrator", "super admin"
    }:
        return "District Commissioner"
    if cleaned in {"hospital admin", "hospital administrator", "hospital manager"}:
        return "Hospital Admin"
    return role


initialize_database()


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

for key, default in {
    "logged_in": False,
    "user_role": None,
    "username": None,
    "otp": None,
    "reset_user": None,
    "otp_expiry": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------

def get_hospitals():
    """Return registered hospital names for dropdowns."""
    connection = get_connection()
    rows = connection.execute(
        "SELECT name FROM hospitals ORDER BY name"
    ).fetchall()
    connection.close()
    return [row["name"] for row in rows]


def get_medical_categories(active_only=True):
    """Return medical category names for dropdowns."""
    connection = get_connection()
    if active_only:
        rows = connection.execute(
            "SELECT name FROM medical_categories WHERE active=1 ORDER BY name"
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT name FROM medical_categories ORDER BY name"
        ).fetchall()
    connection.close()
    return [row["name"] for row in rows]


# ---------------------------------------------------------
# OPTIONAL LOCAL OLLAMA AI
# ---------------------------------------------------------

def analyse_complaint_with_ollama(complaint_text):
    """
    Ask a locally running Ollama model to organise the complaint.
    Patient name and phone number are never sent to Ollama.
    AI suggestions must be checked by a human hospital staff member.
    """
    ollama_url = os.getenv(
        "SMARTCARE_OLLAMA_URL",
        "http://localhost:11434/api/generate"
    )
    ollama_model = os.getenv("SMARTCARE_OLLAMA_MODEL", "qwen2.5:0.5b")

    prompt = f"""
You help organise hospital service complaints. Do not diagnose patients,
recommend treatment, or make clinical decisions. Classify only the service
issue described below. Return valid JSON only with these keys:
category, summary, priority, urgent, reason.
category must be one of: Doctor Unavailable, Medicine Unavailable,
Cleanliness Problem, Water Problem, Bed Unavailable,
Hospital Facilities Problem, Staff Behaviour Problem, Other.
priority must be Low, Medium, High, or Critical.
urgent must be true or false.
If the complaint suggests immediate danger or a medical emergency, set
urgent to true and priority to Critical. Keep summary short.
Complaint: {complaint_text}
"""
    payload = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    request = urllib.request.Request(
        ollama_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        ai_text = result.get("response", "{}")
        parsed = json.loads(ai_text)

        allowed_priorities = {"Low", "Medium", "High", "Critical"}
        priority = parsed.get("priority", "Medium")
        if priority not in allowed_priorities:
            priority = "Medium"

        allowed_categories = set(COMPLAINT_CATEGORIES["English"])
        category = parsed.get("category", "Other")
        if category not in allowed_categories:
            category = "Other"

        return {
            "category": category,
            "summary": str(parsed.get("summary", ""))[:500],
            "priority": priority,
            "urgent": 1 if parsed.get("urgent") is True else 0,
            "reason": str(parsed.get("reason", ""))[:500],
        }
    except Exception:
        # App remains usable when Ollama is not installed or not running.
        return None


# ---------------------------------------------------------
# HEADER AND SIDEBAR NAVIGATION
# ---------------------------------------------------------

st.title("🏥 SMARTCARE AI")
st.caption("Hospital Service Monitoring, Patient Complaints & Doctor Availability")

role = st.session_state.user_role
username = st.session_state.username
logged_in = st.session_state.logged_in

if logged_in:
    st.sidebar.success(f"Logged in: {username}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.username = None
        st.rerun()

    if role == "District Commissioner":
        page_options = [
            "Patient Portal",
            "Check Doctor Availability",
            "District Dashboard",
            "Hospital Registration",
            "Manage Users",
            "Doctor & Service Management",
        ]
    elif role == "Hospital Admin":
        page_options = [
            "Patient Portal",
            "Check Doctor Availability",
            "Hospital Dashboard",
            "Manage Users",
            "Doctor & Service Management",
        ]
    else:
        st.error("Unrecognised account role. Contact the District Commissioner.")
        st.stop()
else:
    page_options = [
        "Patient Portal",
        "Check Doctor Availability",
        "Admin Login",
    ]

page = st.sidebar.radio("Navigation", page_options)


# ---------------------------------------------------------
# PATIENT PORTAL - REGISTER A COMPLAINT
# ---------------------------------------------------------

if page == "Patient Portal":
    st.header("📝 Register Hospital Complaint")

    language = st.selectbox(
        "Select Language",
        ["English", "Kannada", "Hindi"],
        key="patient_language"
    )

    labels = {
        "English": {
            "name": "Your Name",
            "phone": "Mobile Number",
            "hospital": "Hospital Name",
            "category": "Complaint Category",
            "complaint": "Describe Your Complaint",
            "submit": "Submit Complaint",
        },
        "Kannada": {
            "name": "ನಿಮ್ಮ ಹೆಸರು",
            "phone": "ಮೊಬೈಲ್ ಸಂಖ್ಯೆ",
            "hospital": "ಆಸ್ಪತ್ರೆಯ ಹೆಸರು",
            "category": "ದೂರಿನ ಪ್ರಕಾರ",
            "complaint": "ನಿಮ್ಮ ದೂರನ್ನು ವಿವರಿಸಿ",
            "submit": "ದೂರು ಸಲ್ಲಿಸಿ",
        },
        "Hindi": {
            "name": "आपका नाम",
            "phone": "मोबाइल नंबर",
            "hospital": "अस्पताल का नाम",
            "category": "शिकायत का प्रकार",
            "complaint": "अपनी शिकायत बताएं",
            "submit": "शिकायत जमा करें",
        },
    }
    label = labels[language]
    complaint_categories = COMPLAINT_CATEGORIES[language]

    patient_name = st.text_input(label["name"])
    patient_phone = st.text_input(
        label["phone"], max_chars=10, key="patient_phone"
    )
    if patient_phone and not patient_phone.isdigit():
        st.warning("Enter digits only for the mobile number.")

    hospital_options = get_hospitals()
    if "Other" not in hospital_options:
        hospital_options.append("Other")
    hospital_choice = st.selectbox(label["hospital"], hospital_options)

    if hospital_choice == "Other":
        hospital_name = st.text_input("Enter your hospital name")
    else:
        hospital_name = hospital_choice

    complaint_category = st.selectbox(label["category"], complaint_categories)
    complaint_text = st.text_area(label["complaint"], height=130)

    if st.button(label["submit"], type="primary"):
        if (
            not patient_name.strip()
            or not patient_phone.isdigit()
            or len(patient_phone) != 10
            or not hospital_name.strip()
            or not complaint_text.strip()
        ):
            st.warning("Please complete all fields and enter a valid 10-digit phone number.")
        else:
            # Analyse the complaint before saving. This does not send patient identity.
            ai_result = analyse_complaint_with_ollama(complaint_text.strip())
            complaint_id = "SC-" + uuid.uuid4().hex[:8].upper()
            created_at = datetime.now().strftime("%d-%m-%Y %H:%M")

            connection = get_connection()
            connection.execute("""
                INSERT INTO complaints (
                    id, name, phone, hospital, category, complaint, status, date,
                    ai_category, ai_summary, ai_priority, ai_urgent, ai_reason,
                    ai_review_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                complaint_id,
                patient_name.strip(),
                patient_phone,
                hospital_name.strip(),
                complaint_category,
                complaint_text.strip(),
                "Pending",
                created_at,
                ai_result["category"] if ai_result else None,
                ai_result["summary"] if ai_result else None,
                ai_result["priority"] if ai_result else None,
                ai_result["urgent"] if ai_result else 0,
                ai_result["reason"] if ai_result else None,
                1,
            ))
            connection.commit()
            connection.close()

            st.success("Complaint registered successfully!")
            st.info(f"Your Complaint ID: {complaint_id}")
            if ai_result:
                st.caption("AI has prepared an initial suggestion for hospital staff review.")
            else:
                st.info(
                    "Complaint saved. Local Ollama AI is not reachable right now; "
                    "hospital staff can still review and organise this complaint."
                )


# ---------------------------------------------------------
# PATIENT PORTAL - CHECK DOCTOR / SERVICE AVAILABILITY
# ---------------------------------------------------------

elif page == "Check Doctor Availability":
    st.header("🔎 Check Doctor & Medical Service Availability")

    hospitals = get_hospitals()
    if not hospitals:
        st.info("No hospitals are registered yet.")
    else:
        selected_hospital = st.selectbox("Select Hospital", hospitals)
        categories = ["All Categories"] + get_medical_categories()

        selected_category = st.selectbox(
            "Select Medical Category",
            categories,
            key="patient_medical_category"
        )

        connection = get_connection()
        query = """
            SELECT name, category, record_type, service_name, availability,
                   consultation_days, start_time, end_time, next_available
            FROM doctor_services
            WHERE hospital=?
        """
        parameters = [selected_hospital]
        if selected_category != "All Categories":
            query += " AND category=?"
            parameters.append(selected_category)
        query += " ORDER BY category, name"

        records = connection.execute(query, parameters).fetchall()
        connection.close()

        if not records:
            st.info("No doctors or services are listed for this hospital and category.")
        for record in records:
            with st.container(border=True):
                st.subheader(record["name"])
                st.write(f"Hospital: {selected_hospital}")
                st.write(f"Category: {record['category']}")
                st.write(f"Type: {record['record_type']}")
                if record["service_name"]:
                    st.write(f"Service: {record['service_name']}")

                if record["availability"] == "Available":
                    st.success("Available")
                elif record["availability"] == "On Leave":
                    st.warning("On Leave")
                else:
                    st.error("Unavailable")

                st.write(
                    "Consultation days: "
                    + (record["consultation_days"] or "Please contact hospital")
                )
                st.write(
                    "Timings: "
                    + (record["start_time"] or "--")
                    + " to "
                    + (record["end_time"] or "--")
                )
                st.write("Next available: " + (record["next_available"] or "Not updated"))

        st.caption(
            "Availability is maintained by hospital administrators. "
            "Please confirm with the hospital before travelling."
        )


# ---------------------------------------------------------
# ADMIN LOGIN AND DEMO PASSWORD RESET
# ---------------------------------------------------------

elif page == "Admin Login":
    st.header("🔐 Admin Login")

    if not st.session_state.logged_in:
        login_username = st.text_input("Username")
        login_password = st.text_input("Password", type="password")

        if st.button("Login", type="primary"):
            connection = get_connection()
            account = connection.execute(
                "SELECT * FROM users WHERE username=?",
                (login_username.strip(),)
            ).fetchone()
            connection.close()

            if account and verify_password(login_password, account["password"]):
                # Upgrade older plain-text / SHA-256 passwords after a successful login.
                if not account["password"].startswith("pbkdf2_sha256$"):
                    upgrade_connection = get_connection()
                    upgrade_connection.execute(
                        "UPDATE users SET password=? WHERE username=?",
                        (hash_password(login_password), account["username"])
                    )
                    upgrade_connection.commit()
                    upgrade_connection.close()
                st.session_state.logged_in = True
                st.session_state.username = account["username"]
                st.session_state.user_role = normalize_role(account["role"])
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.divider()
    st.subheader("Forgot Password?")

    reset_email = st.text_input("Enter your registered email", key="forgot_email")
    if st.button("Generate Reset OTP"):
        connection = get_connection()
        account = connection.execute(
            "SELECT username FROM users WHERE email=?",
            (reset_email.strip(),)
        ).fetchone()
        connection.close()

        if account:
            st.session_state.reset_user = account["username"]
            st.session_state.otp = str(random.randint(100000, 999999))
            st.session_state.otp_expiry = datetime.now() + timedelta(minutes=5)
            st.warning(
                "DEMO OTP (not emailed): " + st.session_state.otp
                + ". Configure a real email/SMS provider before public use."
            )
        else:
            st.error("Email address not registered.")

    if st.session_state.otp:
        entered_otp = st.text_input("Enter OTP")
        new_password = st.text_input("Create New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")

        if st.button("Reset Password"):
            if datetime.now() > st.session_state.otp_expiry:
                st.error("OTP expired. Generate a new OTP.")
                st.session_state.otp = None
                st.session_state.reset_user = None
            elif entered_otp != st.session_state.otp:
                st.error("Incorrect OTP.")
            elif len(new_password) < 8:
                st.error("Password must contain at least 8 characters.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            else:
                connection = get_connection()
                connection.execute(
                    "UPDATE users SET password=? WHERE username=?",
                    (hash_password(new_password), st.session_state.reset_user)
                )
                connection.commit()
                connection.close()
                st.session_state.otp = None
                st.session_state.reset_user = None
                st.session_state.otp_expiry = None
                st.success("Password changed successfully!")


# ---------------------------------------------------------
# HOSPITAL REGISTRATION - DISTRICT ADMIN ONLY
# ---------------------------------------------------------

elif page == "Hospital Registration":
    if not st.session_state.logged_in or st.session_state.user_role != "District Commissioner":
        st.error("Only the District Commissioner can register hospitals.")
    else:
        st.header("🏥 Register New Hospital")

        with st.form("hospital_registration_form"):
            hospital_name = st.text_input("Hospital Name")
            district = st.text_input("District")
            location = st.text_input("Hospital Location")
            st.subheader("Create Hospital Admin Account")
            admin_username = st.text_input("Admin Username")
            admin_email = st.text_input("Admin Email")
            admin_password = st.text_input("Admin Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Register Hospital")

        if submitted:
            if not all([
                hospital_name.strip(), district.strip(), location.strip(),
                admin_username.strip(), admin_email.strip(),
                admin_password, confirm_password
            ]):
                st.warning("Please fill all fields.")
            elif len(admin_password) < 8:
                st.error("Password must contain at least 8 characters.")
            elif admin_password != confirm_password:
                st.error("Passwords do not match.")
            else:
                connection = get_connection()
                hospital_exists = connection.execute(
                    "SELECT 1 FROM hospitals WHERE name=?",
                    (hospital_name.strip(),)
                ).fetchone()
                user_exists = connection.execute(
                    "SELECT 1 FROM users WHERE username=?",
                    (admin_username.strip(),)
                ).fetchone()

                if hospital_exists:
                    st.error("Hospital already registered.")
                elif user_exists:
                    st.error("Username already exists.")
                else:
                    connection.execute(
                        "INSERT INTO hospitals(name, district, location) VALUES (?, ?, ?)",
                        (hospital_name.strip(), district.strip(), location.strip())
                    )
                    connection.execute(
                        "INSERT INTO users(username, role, hospital, email, password) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            admin_username.strip(),
                            "Hospital Admin",
                            hospital_name.strip(),
                            admin_email.strip(),
                            hash_password(admin_password)
                        )
                    )
                    connection.commit()
                    st.success("Hospital registered successfully.")
                    st.info("Hospital Admin Username: " + admin_username.strip())
                connection.close()


# ---------------------------------------------------------
# DOCTOR AND MEDICAL SERVICE MANAGEMENT
# ---------------------------------------------------------

elif page == "Doctor & Service Management":
    if not st.session_state.logged_in:
        st.error("Please log in first.")
    elif st.session_state.user_role not in ["District Commissioner", "Hospital Admin"]:
        st.error("You do not have permission to manage doctors and services.")
    else:
        current_role = st.session_state.user_role
        current_username = st.session_state.username

        connection = get_connection()
        user_account = connection.execute(
            "SELECT hospital FROM users WHERE username=?",
            (current_username,)
        ).fetchone()
        own_hospital = user_account["hospital"] if user_account else None

        st.header("🩺 Doctor & Medical Service Management")

        # Only the District Commissioner can create or deactivate global categories.
        if current_role == "District Commissioner":
            with st.expander("Manage Medical Categories", expanded=True):
                new_category = st.text_input("New medical category", key="new_med_category")
                if st.button("Add Category"):
                    cleaned = new_category.strip()
                    if not cleaned:
                        st.warning("Enter a category name.")
                    else:
                        try:
                            connection.execute(
                                "INSERT INTO medical_categories(name, active) VALUES (?, 1)",
                                (cleaned,)
                            )
                            connection.commit()
                            st.success("Category added.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.warning("This category already exists.")

                category_rows = connection.execute(
                    "SELECT id, name, active FROM medical_categories ORDER BY name"
                ).fetchall()
                for category_row in category_rows:
                    col_a, col_b = st.columns([4, 1])
                    col_a.write(category_row["name"])
                    button_text = "Deactivate" if category_row["active"] else "Activate"
                    if col_b.button(button_text, key=f"category_toggle_{category_row['id']}"):
                        connection.execute(
                            "UPDATE medical_categories SET active=? WHERE id=?",
                            (0 if category_row["active"] else 1, category_row["id"])
                        )
                        connection.commit()
                        st.rerun()

        active_categories = get_medical_categories()
        hospital_names = get_hospitals()

        if current_role == "District Commissioner":
            hospital_for_form = st.selectbox(
                "Select hospital for this doctor/service",
                hospital_names
            ) if hospital_names else None
        else:
            hospital_for_form = own_hospital
            st.text_input("Your hospital", value=own_hospital or "", disabled=True)

        if not active_categories:
            st.warning("No active medical categories are available.")
        elif not hospital_for_form:
            st.warning("Register a hospital before adding doctors or services.")
        else:
            st.subheader("Add Doctor or Medical Service")
            with st.form("add_doctor_service_form"):
                record_type = st.selectbox("Record type", ["Doctor", "Medical Service"])
                person_or_service = st.text_input(
                    "Doctor name or service title",
                    placeholder="e.g. Dr. Anil Kumar or X-ray Department"
                )
                medical_category = st.selectbox("Medical category", active_categories)
                service_description = st.text_input(
                    "Service name / details (optional)",
                    placeholder="e.g. Dental consultation, X-ray chest"
                )
                availability = st.selectbox(
                    "Availability", ["Available", "Unavailable", "On Leave"]
                )
                consultation_days = st.text_input(
                    "Consultation days", placeholder="e.g. Monday to Saturday"
                )
                time_col1, time_col2 = st.columns(2)
                start_time = time_col1.text_input("Start time", placeholder="09:00 AM")
                end_time = time_col2.text_input("End time", placeholder="01:00 PM")
                next_available = st.date_input(
                    "Next available date",
                    value=date.today(),
                    min_value=date.today()
                )
                save_record = st.form_submit_button("Save Doctor / Service")

            if save_record:
                if not person_or_service.strip():
                    st.error("Enter a doctor name or service title.")
                else:
                    connection.execute("""
                        INSERT INTO doctor_services (
                            name, hospital, category, record_type, service_name,
                            availability, consultation_days, start_time, end_time,
                            next_available
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        person_or_service.strip(),
                        hospital_for_form,
                        medical_category,
                        record_type,
                        service_description.strip(),
                        availability,
                        consultation_days.strip(),
                        start_time.strip(),
                        end_time.strip(),
                        next_available.isoformat(),
                    ))
                    connection.commit()
                    st.success("Doctor / service saved successfully.")
                    st.rerun()

        st.divider()
        st.subheader("Update Existing Doctors and Services")

        if current_role == "District Commissioner":
            filter_hospitals = ["All Hospitals"] + hospital_names
            chosen_hospital = st.selectbox("Filter records by hospital", filter_hospitals)
            if chosen_hospital == "All Hospitals":
                records = connection.execute(
                    "SELECT * FROM doctor_services ORDER BY hospital, category, name"
                ).fetchall()
            else:
                records = connection.execute(
                    "SELECT * FROM doctor_services WHERE hospital=? ORDER BY category, name",
                    (chosen_hospital,)
                ).fetchall()
        else:
            records = connection.execute(
                "SELECT * FROM doctor_services WHERE hospital=? ORDER BY category, name",
                (own_hospital,)
            ).fetchall()

        if not records:
            st.info("No doctors or services have been added yet.")

        for record in records:
            with st.expander(
                f"{record['name']} | {record['category']} | {record['hospital']}"
            ):
                st.write(f"Type: {record['record_type']}")
                st.write(f"Details: {record['service_name'] or 'Not specified'}")
                status_options = ["Available", "Unavailable", "On Leave"]
                current_status = record["availability"]
                status_index = status_options.index(current_status) if current_status in status_options else 0
                updated_status = st.selectbox(
                    "Availability status",
                    status_options,
                    index=status_index,
                    key=f"availability_{record['id']}"
                )
                updated_days = st.text_input(
                    "Consultation days",
                    value=record["consultation_days"] or "",
                    key=f"days_{record['id']}"
                )
                c_start, c_end = st.columns(2)
                updated_start = c_start.text_input(
                    "Start time", value=record["start_time"] or "",
                    key=f"start_{record['id']}"
                )
                updated_end = c_end.text_input(
                    "End time", value=record["end_time"] or "",
                    key=f"end_{record['id']}"
                )
                updated_next = st.text_input(
                    "Next available date (YYYY-MM-DD)",
                    value=record["next_available"] or "",
                    key=f"next_{record['id']}"
                )

                if st.button("Update Availability", key=f"update_{record['id']}"):
                    # Hospital Admin is restricted to records belonging to own hospital.
                    connection.execute("""
                        UPDATE doctor_services
                        SET availability=?, consultation_days=?, start_time=?,
                            end_time=?, next_available=?, updated_at=CURRENT_TIMESTAMP
                        WHERE id=? AND hospital=?
                    """, (
                        updated_status, updated_days, updated_start, updated_end,
                        updated_next, record["id"], own_hospital if current_role == "Hospital Admin"
                        else record["hospital"]
                    ))
                    connection.commit()
                    st.success("Availability updated.")
                    st.rerun()

                if st.button("Delete Record", key=f"delete_{record['id']}"):
                    if current_role == "District Commissioner":
                        connection.execute(
                            "DELETE FROM doctor_services WHERE id=?",
                            (record["id"],)
                        )
                    else:
                        connection.execute(
                            "DELETE FROM doctor_services WHERE id=? AND hospital=?",
                            (record["id"], own_hospital)
                        )
                    connection.commit()
                    st.success("Record deleted.")
                    st.rerun()

        connection.close()


# ---------------------------------------------------------
# DASHBOARD FUNCTION
# ---------------------------------------------------------

def show_dashboard(dashboard_role, hospital_name=None):
    """Display complaint counts, records and status controls."""
    connection = get_connection()

    if hospital_name:
        records = connection.execute(
            "SELECT * FROM complaints WHERE hospital=? ORDER BY date DESC",
            (hospital_name,)
        ).fetchall()
    else:
        records = connection.execute(
            "SELECT * FROM complaints ORDER BY date DESC"
        ).fetchall()

    total = len(records)
    pending = sum(1 for row in records if row["status"] == "Pending")
    in_progress = sum(1 for row in records if row["status"] == "In Progress")
    resolved = sum(1 for row in records if row["status"] == "Resolved")

    st.header(f"📊 {dashboard_role} Dashboard")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Complaints", total)
    c2.metric("Pending", pending)
    c3.metric("In Progress", in_progress)
    c4.metric("Resolved", resolved)

    # Circular charts use the patient's selected complaint category and status.
    st.divider()
    st.subheader("Complaint Statistics")
    chart_col1, chart_col2 = st.columns(2)

    category_counts = {}
    status_counts = {}
    for item in records:
        category_name = item["category"] or "Not specified"
        status_name = item["status"] or "Not specified"
        category_counts[category_name] = category_counts.get(category_name, 0) + 1
        status_counts[status_name] = status_counts.get(status_name, 0) + 1

    with chart_col1:
        st.caption("Complaints by patient-selected category")
        if category_counts:
            category_fig = px.pie(
                names=list(category_counts.keys()),
                values=list(category_counts.values()),
                hole=0.48
            )
            category_fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(category_fig, use_container_width=True)
        else:
            st.info("No category data to display yet.")

    with chart_col2:
        st.caption("Complaints by status")
        if status_counts:
            status_fig = px.pie(
                names=list(status_counts.keys()),
                values=list(status_counts.values()),
                hole=0.48
            )
            status_fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(status_fig, use_container_width=True)
        else:
            st.info("No status data to display yet.")

    if not hospital_name:
        hospital_counts = {}
        for item in records:
            hospital_label = item["hospital"] or "Not specified"
            hospital_counts[hospital_label] = hospital_counts.get(hospital_label, 0) + 1
        st.caption("Complaints by hospital")
        if hospital_counts:
            hospital_fig = px.pie(
                names=list(hospital_counts.keys()),
                values=list(hospital_counts.values()),
                hole=0.48
            )
            hospital_fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(hospital_fig, use_container_width=True)

    st.divider()
    st.subheader("Complaint Records")

    if not records:
        st.info("No complaints have been registered yet.")

    for record in records:
        with st.expander(
            f"{record['id']} | {record['hospital']} | {record['status']}"
        ):
            st.write("Patient:", record["name"])
            st.write("Phone:", record["phone"])
            st.write("Hospital:", record["hospital"])
            st.write("Patient category:", record["category"])
            st.write("Complaint:", record["complaint"])
            st.write("Status:", record["status"])
            st.write("Date:", record["date"])

            if record["ai_category"]:
                st.markdown("**AI review suggestion**")
                st.write("Suggested category:", record["ai_category"])
                st.write("Summary:", record["ai_summary"] or "Not available")
                st.write("Priority:", record["ai_priority"] or "Not set")
                if record["ai_urgent"]:
                    st.error("AI flagged this complaint as potentially urgent.")
                else:
                    st.write("Urgent flag: No")
                st.write("Reason:", record["ai_reason"] or "Not provided")
                st.warning(
                    "AI output is only a suggestion. A human staff member must review it."
                )
            else:
                st.info("No AI analysis is stored for this complaint.")

    if records:
        st.divider()
        st.subheader("Update Complaint Status")
        selected_id = st.selectbox(
            "Select Complaint ID",
            [record["id"] for record in records]
        )
        new_status = st.selectbox(
            "New Status", ["Pending", "In Progress", "Resolved"]
        )
        if st.button("Update Complaint Status"):
            connection.execute(
                "UPDATE complaints SET status=? WHERE id=?",
                (new_status, selected_id)
            )
            connection.commit()
            st.success("Complaint status updated.")
            st.rerun()

    connection.close()


# ---------------------------------------------------------
# USER ACCOUNT MANAGEMENT
# ---------------------------------------------------------

if page == "Manage Users":
    if not st.session_state.logged_in:
        st.error("Please log in first.")
    elif st.session_state.user_role not in ["District Commissioner", "Hospital Admin"]:
        st.error("You do not have permission to manage accounts.")
    else:
        current_role = st.session_state.user_role
        current_username = st.session_state.username
        connection = get_connection()
        current_account = connection.execute(
            "SELECT hospital FROM users WHERE username=?", (current_username,)
        ).fetchone()
        own_hospital = current_account["hospital"] if current_account else None

        st.header("👥 Manage User Accounts")
        st.caption("District Commissioner can manage all accounts. Hospital Admin can manage accounts linked to their own hospital.")

        with st.form("create_user_account_form"):
            new_username = st.text_input("New username")
            new_email = st.text_input("Email address")
            new_password = st.text_input("Temporary password", type="password")
            confirm_new_password = st.text_input("Confirm password", type="password")
            if current_role == "District Commissioner":
                account_role = "Hospital Admin"
                st.text_input("Account role", value=account_role, disabled=True)
                account_hospital = st.selectbox("Hospital", get_hospitals()) if get_hospitals() else ""
            else:
                account_role = "Hospital Admin"
                account_hospital = own_hospital or ""
                st.text_input("Hospital", value=account_hospital, disabled=True)
            create_account = st.form_submit_button("Create Account")

        if create_account:
            if not all([new_username.strip(), new_email.strip(), new_password, confirm_new_password, account_hospital]):
                st.warning("Complete all account fields.")
            elif len(new_password) < 8:
                st.error("Password must contain at least 8 characters.")
            elif new_password != confirm_new_password:
                st.error("Passwords do not match.")
            else:
                exists = connection.execute(
                    "SELECT 1 FROM users WHERE username=?", (new_username.strip(),)
                ).fetchone()
                if exists:
                    st.error("That username already exists.")
                else:
                    connection.execute(
                        "INSERT INTO users(username, role, hospital, email, password) VALUES (?, ?, ?, ?, ?)",
                        (new_username.strip(), account_role, account_hospital, new_email.strip(), hash_password(new_password))
                    )
                    connection.commit()
                    st.success("Account created successfully.")
                    st.rerun()

        st.divider()
        st.subheader("Existing Accounts")
        if current_role == "District Commissioner":
            user_rows = connection.execute(
                "SELECT username, role, hospital, email FROM users ORDER BY role, username"
            ).fetchall()
        else:
            user_rows = connection.execute(
                "SELECT username, role, hospital, email FROM users WHERE hospital=? AND username<>? ORDER BY username",
                (own_hospital, current_username)
            ).fetchall()

        for user_row in user_rows:
            with st.expander(f"{user_row['username']} — {user_row['role']}"):
                st.write("Hospital:", user_row["hospital"] or "Not assigned")
                st.write("Email:", user_row["email"] or "Not provided")
                with st.form(f"reset_user_{user_row['username']}"):
                    reset_password = st.text_input("Set new password", type="password", key=f"pw_{user_row['username']}")
                    reset_confirm = st.text_input("Confirm new password", type="password", key=f"pc_{user_row['username']}")
                    reset_clicked = st.form_submit_button("Reset Password")
                if reset_clicked:
                    if len(reset_password) < 8:
                        st.error("Password must contain at least 8 characters.")
                    elif reset_password != reset_confirm:
                        st.error("Passwords do not match.")
                    else:
                        connection.execute(
                            "UPDATE users SET password=? WHERE username=?",
                            (hash_password(reset_password), user_row["username"])
                        )
                        connection.commit()
                        st.success("Password updated.")
                        st.rerun()
                protected_usernames = {"district", current_username}
                if user_row["username"] not in protected_usernames:
                    if st.button("Delete Account", key=f"delete_user_{user_row['username']}"):
                        if current_role == "Hospital Admin":
                            connection.execute(
                                "DELETE FROM users WHERE username=? AND hospital=?",
                                (user_row["username"], own_hospital)
                            )
                        else:
                            connection.execute(
                                "DELETE FROM users WHERE username=?",
                                (user_row["username"],)
                            )
                        connection.commit()
                        st.success("Account deleted.")
                        st.rerun()
        connection.close()


# ---------------------------------------------------------
# DISTRICT AND HOSPITAL DASHBOARDS
# ---------------------------------------------------------

if page == "District Dashboard":
    if st.session_state.logged_in and st.session_state.user_role == "District Commissioner":
        show_dashboard("District Commissioner")
    else:
        st.error("Access denied. Please log in as District Commissioner.")

if page == "Hospital Dashboard":
    if st.session_state.logged_in and st.session_state.user_role == "Hospital Admin":
        connection = get_connection()
        account = connection.execute(
            "SELECT hospital FROM users WHERE username=?",
            (st.session_state.username,)
        ).fetchone()
        connection.close()

        if account and account["hospital"]:
            show_dashboard("Hospital Admin", account["hospital"])
        else:
            st.error("Your admin account is not linked to a hospital.")
    else:
        st.error("Access denied. Please log in as Hospital Admin.")


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------

st.divider()
st.caption(
    "SMARTCARE AI | AI suggestions are not medical advice. "
    "Hospital staff must verify complaint priorities and service availability."
)
