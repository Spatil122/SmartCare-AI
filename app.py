# ============================================================
# SMARTCARE AI - Hospital Complaint Management System
# Beginner-friendly, single-file Streamlit application.
#
# IMPORTANT:
# 1. Keep your existing smartcare.db file. This code upgrades
#    its tables safely and does not intentionally delete records.
# 2. Main Admin login (created only if missing):
#       username: mainadmin
#       password: MainAdmin@123
# 3. Existing "District Commissioner" accounts are upgraded
#    to the new role name "Main Admin".
# 4. Optional AI uses Ollama. If Ollama is unavailable, the
#    complaint is still saved and staff can choose the category.
# ============================================================

import streamlit as st

# Page settings must be the first Streamlit command.
st.set_page_config(
    page_title="SMARTCARE AI",
    page_icon="🏥",
    layout="wide"
)

import sqlite3
import uuid
import hashlib
import random
import requests
from datetime import datetime
import plotly.express as px

DB_FILE = "smartcare.db"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

CATEGORIES = [
    "Doctor Unavailable",
    "Medicine Unavailable",
    "Cleanliness Problem",
    "Water Problem",
    "Bed Unavailable",
    "Hospital Facilities Problem",
    "Staff Behaviour Problem",
    "Delay in Treatment",
    "Billing Problem",
    "Other"
]

STATUSES = ["Pending", "In Progress", "Resolved"]


# ------------------------------------------------------------
# DATABASE CONNECTION AND SAFE TABLE SETUP
# ------------------------------------------------------------

def get_connection():
    """Open the SQLite database and allow use across Streamlit reruns."""
    connection = sqlite3.connect(DB_FILE, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def hash_password(password):
    """Hash a password before saving it in the database."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def column_exists(connection, table_name, column_name):
    """Check whether a database table already has a column."""
    columns = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()
    return any(column["name"] == column_name for column in columns)


def add_column_if_missing(connection, table_name, column_name, column_type):
    """Add a new column only when it is not already present."""
    if not column_exists(connection, table_name, column_name):
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )


def setup_database():
    """Create required tables and upgrade older SMARTCARE databases."""
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

    # Extra fields are added safely to existing complaint tables.
    add_column_if_missing(connection, "complaints", "ai_category", "TEXT")
    add_column_if_missing(connection, "complaints", "ai_summary", "TEXT")

    # Every complaint interaction is stored as a separate history entry.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaint_interactions (
            interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT NOT NULL,
            author TEXT NOT NULL,
            author_role TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Add one starter hospital only when the hospital table is empty.
    hospital_count = cursor.execute(
        "SELECT COUNT(*) FROM hospitals"
    ).fetchone()[0]

    if hospital_count == 0:
        cursor.execute(
            "INSERT OR IGNORE INTO hospitals (name, district, location) VALUES (?, ?, ?)",
            ("City General Hospital", "Kalaburagi", "Main City")
        )

    # Rename the old role without changing usernames or passwords.
    cursor.execute("""
        UPDATE users
        SET role = 'Main Admin'
        WHERE role = 'District Commissioner'
    """)

    # Create a Main Admin account only if one does not already exist.
    main_admin_exists = cursor.execute(
        "SELECT username FROM users WHERE role='Main Admin' LIMIT 1"
    ).fetchone()

    if not main_admin_exists:
        cursor.execute("""
            INSERT OR IGNORE INTO users
            (username, role, hospital, email, password)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "mainadmin",
            "Main Admin",
            "ALL",
            "mainadmin@example.com",
            hash_password("MainAdmin@123")
        ))

    connection.commit()
    connection.close()


setup_database()


def fetch_hospitals():
    """Return registered hospital names."""
    connection = get_connection()
    rows = connection.execute(
        "SELECT name FROM hospitals ORDER BY name"
    ).fetchall()
    connection.close()
    return [row["name"] for row in rows]


def add_interaction(complaint_id, author, role, message):
    """Save a staff reply or complaint update in the interaction history."""
    connection = get_connection()
    connection.execute("""
        INSERT INTO complaint_interactions
        (complaint_id, author, author_role, message, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        complaint_id,
        author,
        role,
        message.strip(),
        datetime.now().strftime("%d-%m-%Y %H:%M")
    ))
    connection.commit()
    connection.close()


# ------------------------------------------------------------
# OPTIONAL OLLAMA AI CLASSIFICATION
# ------------------------------------------------------------

def classify_with_ollama(complaint_text):
    """
    Ask Ollama to suggest one complaint category.
    If Ollama is not running or cannot be reached, return None.
    The complaint is still registered even when AI is unavailable.
    """
    prompt = f"""
Choose exactly one category from this list:
{", ".join(CATEGORIES)}

Complaint:
{complaint_text}

Return only the category name. Do not provide medical advice.
"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=12
        )
        response.raise_for_status()
        answer = response.json().get("response", "").strip()

        # Match the AI answer to one of the approved categories.
        for category in CATEGORIES:
            if category.lower() in answer.lower():
                return category
        return "Other"
    except requests.RequestException:
        return None
    except (ValueError, KeyError):
        return None


# ------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------

defaults = {
    "logged_in": False,
    "username": None,
    "user_role": None,
    "user_hospital": None,
    "otp": None,
    "reset_user": None,
    "last_complaint_id": None
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ------------------------------------------------------------
# TOP OF APPLICATION
# ------------------------------------------------------------

st.title("🏥 SMARTCARE AI")
st.caption("Hospital Complaint Registration, Tracking and Service Monitoring")

with st.sidebar:
    st.subheader("Navigation")

    if st.session_state.logged_in:
        st.success(f"Logged in: {st.session_state.username}")
        st.caption(f"Role: {st.session_state.user_role}")

        if st.button("Logout", use_container_width=True):
            for key, value in defaults.items():
                st.session_state[key] = value
            st.rerun()

        if st.session_state.user_role == "Main Admin":
            menu = [
                "Patient Portal",
                "Track Complaint",
                "Main Admin Dashboard",
                "Hospital Management",
                "User Management"
            ]
        elif st.session_state.user_role == "Hospital Admin":
            menu = [
                "Patient Portal",
                "Track Complaint",
                "Hospital Dashboard",
                "Staff Management"
            ]
        else:
            menu = [
                "Patient Portal",
                "Track Complaint",
                "Staff Dashboard"
            ]
    else:
        menu = ["Patient Portal", "Track Complaint", "Admin Login"]

    page = st.radio("Open page", menu)


# ------------------------------------------------------------
# PATIENT PORTAL
# ------------------------------------------------------------

if page == "Patient Portal":
    st.header("📝 Register a Hospital Complaint")

    language = st.selectbox(
        "Select Language / ಭಾಷೆ / भाषा",
        ["English", "ಕನ್ನಡ (Kannada)", "हिन्दी (Hindi)"]
    )

    if language == "ಕನ್ನಡ (Kannada)":
        labels = {
            "name": "ನಿಮ್ಮ ಹೆಸರು",
            "phone": "10 ಅಂಕಿಯ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ",
            "hospital": "ಆಸ್ಪತ್ರೆ",
            "category": "ದೂರಿನ ಪ್ರಕಾರ",
            "complaint": "ನಿಮ್ಮ ದೂರನ್ನು ವಿವರಿಸಿ",
            "submit": "ದೂರು ಸಲ್ಲಿಸಿ"
        }
        category_labels = [
            "ವೈದ್ಯರು ಲಭ್ಯವಿಲ್ಲ", "ಔಷಧಿ ಲಭ್ಯವಿಲ್ಲ", "ಸ್ವಚ್ಛತೆ ಸಮಸ್ಯೆ",
            "ನೀರಿನ ಸಮಸ್ಯೆ", "ಹಾಸಿಗೆ ಲಭ್ಯವಿಲ್ಲ", "ಆಸ್ಪತ್ರೆ ಸೌಲಭ್ಯ ಸಮಸ್ಯೆ",
            "ಸಿಬ್ಬಂದಿ ವರ್ತನೆ ಸಮಸ್ಯೆ", "ಚಿಕಿತ್ಸೆಯಲ್ಲಿ ವಿಳಂಬ",
            "ಬಿಲ್ಲಿಂಗ್ ಸಮಸ್ಯೆ", "ಇತರೆ"
        ]
    elif language == "हिन्दी (Hindi)":
        labels = {
            "name": "आपका नाम",
            "phone": "10 अंकों का मोबाइल नंबर",
            "hospital": "अस्पताल",
            "category": "शिकायत का प्रकार",
            "complaint": "अपनी शिकायत बताएं",
            "submit": "शिकायत जमा करें"
        }
        category_labels = [
            "डॉक्टर उपलब्ध नहीं", "दवाइयां उपलब्ध नहीं", "सफाई की समस्या",
            "पानी की समस्या", "बेड उपलब्ध नहीं", "अस्पताल की सुविधाओं की समस्या",
            "कर्मचारियों के व्यवहार की समस्या", "इलाज में देरी",
            "बिलिंग की समस्या", "अन्य"
        ]
    else:
        labels = {
            "name": "Your Name",
            "phone": "10-digit Mobile Number",
            "hospital": "Hospital",
            "category": "Complaint Category",
            "complaint": "Describe Your Complaint",
            "submit": "Submit Complaint"
        }
        category_labels = CATEGORIES

    patient_name = st.text_input(labels["name"])
    patient_phone = st.text_input(labels["phone"], max_chars=10)

    hospital_options = fetch_hospitals()
    hospital_choices = hospital_options + ["Other"] if "Other" not in hospital_options else hospital_options

    selected_hospital = st.selectbox(labels["hospital"], hospital_choices)
    if selected_hospital == "Other":
        hospital_name = st.text_input("Enter hospital name")
    else:
        hospital_name = selected_hospital

    selected_category_label = st.selectbox(labels["category"], category_labels)
    if language == "English":
        chosen_category = selected_category_label
    else:
        # Keep the stored category in English so reports stay consistent.
        chosen_category = CATEGORIES[category_labels.index(selected_category_label)]

    complaint_text = st.text_area(labels["complaint"], height=150)

    st.caption("AI will suggest a category after you submit. Staff can review the suggestion.")

    if st.button(labels["submit"], type="primary"):
        if not patient_name.strip():
            st.error("Please enter your name.")
        elif not (patient_phone.isdigit() and len(patient_phone) == 10):
            st.error("Please enter a valid 10-digit mobile number.")
        elif not hospital_name.strip():
            st.error("Please select or enter a hospital.")
        elif not complaint_text.strip():
            st.error("Please describe your complaint.")
        else:
            with st.spinner("AI is checking the complaint category..."):
                ai_category = classify_with_ollama(complaint_text)

            complaint_id = "SC-" + uuid.uuid4().hex[:8].upper()
            final_category = ai_category if ai_category else chosen_category
            ai_summary = (
                "AI suggested: " + ai_category
                if ai_category
                else "AI unavailable. Patient-selected category used."
            )

            connection = get_connection()
            connection.execute("""
                INSERT INTO complaints
                (id, name, phone, hospital, category, complaint, status, date, ai_category, ai_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                complaint_id,
                patient_name.strip(),
                patient_phone,
                hospital_name.strip(),
                final_category,
                complaint_text.strip(),
                "Pending",
                datetime.now().strftime("%d-%m-%Y %H:%M"),
                ai_category,
                ai_summary
            ))
            connection.commit()
            connection.close()

            add_interaction(
                complaint_id,
                patient_name.strip(),
                "Patient",
                "Complaint submitted."
            )

            st.session_state.last_complaint_id = complaint_id
            st.success("Complaint registered successfully.")
            st.info(f"Your Complaint ID: **{complaint_id}**")
            st.write("Saved category:", final_category)
            if ai_category:
                st.success(f"AI category suggestion: {ai_category}")
            else:
                st.warning("AI is not connected. Your complaint is saved using your selected category.")
            st.caption("Keep your Complaint ID and mobile number safe to track updates.")


# ------------------------------------------------------------
# PATIENT COMPLAINT TRACKING AND INTERACTION HISTORY
# ------------------------------------------------------------

elif page == "Track Complaint":
    st.header("🔎 Track Your Complaint")
    st.write("Enter the Complaint ID and the same mobile number used during registration.")

    track_id = st.text_input("Complaint ID", value=st.session_state.last_complaint_id or "")
    track_phone = st.text_input("Registered Mobile Number", max_chars=10, key="track_phone")

    if st.button("Find Complaint"):
        if not track_id.strip() or not (track_phone.isdigit() and len(track_phone) == 10):
            st.error("Enter a valid Complaint ID and 10-digit mobile number.")
        else:
            connection = get_connection()
            record = connection.execute("""
                SELECT * FROM complaints WHERE id=? AND phone=?
            """, (track_id.strip().upper(), track_phone)).fetchone()
            interactions = connection.execute("""
                SELECT author, author_role, message, created_at
                FROM complaint_interactions
                WHERE complaint_id=?
                ORDER BY interaction_id
            """, (track_id.strip().upper(),)).fetchall()
            connection.close()

            if not record:
                st.error("No complaint found. Please check the Complaint ID and mobile number.")
            else:
                st.success("Complaint found.")
                a, b, c = st.columns(3)
                a.metric("Status", record["status"])
                b.metric("Category", record["category"])
                c.metric("Hospital", record["hospital"])
                st.write("Complaint:", record["complaint"])
                st.write("Registered on:", record["date"])

                st.subheader("Conversation / Update History")
                if interactions:
                    for item in interactions:
                        with st.container(border=True):
                            st.write(f"**{item['author']} ({item['author_role'] or 'User'})**")
                            st.write(item["message"])
                            st.caption(item["created_at"])
                else:
                    st.info("No updates have been added yet.")


# ------------------------------------------------------------
# ADMIN LOGIN AND PASSWORD RESET DEMO
# ------------------------------------------------------------

elif page == "Admin Login":
    st.header("🔐 Admin Login")

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login", type="primary"):
        connection = get_connection()
        user = connection.execute(
            "SELECT * FROM users WHERE username=?",
            (username.strip(),)
        ).fetchone()
        connection.close()

        if user and user["password"] == hash_password(password):
            st.session_state.logged_in = True
            st.session_state.username = user["username"]
            st.session_state.user_role = user["role"]
            st.session_state.user_hospital = user["hospital"]
            st.success("Login successful. Open the sidebar to select your dashboard.")
            st.rerun()
        else:
            st.error("Invalid username or password.")

    st.divider()
    st.subheader("Forgot Password?")

    reset_email = st.text_input("Registered email address", key="reset_email")
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
            st.warning("DEMO OTP (not emailed or texted): " + st.session_state.otp)
        else:
            st.error("Email address not found.")

    if st.session_state.otp:
        entered_otp = st.text_input("Enter OTP", key="reset_otp")
        new_password = st.text_input("New Password", type="password", key="new_password")
        confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_password")

        if st.button("Reset Password"):
            if entered_otp != st.session_state.otp:
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
                st.success("Password changed successfully.")


# ------------------------------------------------------------
# COMMON DASHBOARD
# ------------------------------------------------------------

def show_dashboard(title, hospital_scope=None, allow_hospital_filter=False):
    """Show metrics, donut charts, complaint list, and staff interactions."""
    st.header("📊 " + title)

    connection = get_connection()

    if hospital_scope:
        hospital_filter = hospital_scope
        st.info("Showing data only for: " + hospital_scope)
    elif allow_hospital_filter:
        available = ["All Hospitals"] + fetch_hospitals()
        hospital_filter = st.selectbox("Filter by Hospital", available)
    else:
        hospital_filter = "All Hospitals"

    if allow_hospital_filter:
        category_filter = st.selectbox("Filter by Category", ["All Categories"] + CATEGORIES)
    else:
        category_filter = "All Categories"

    query = "SELECT * FROM complaints WHERE 1=1"
    params = []

    if hospital_filter != "All Hospitals":
        query += " AND hospital=?"
        params.append(hospital_filter)

    if category_filter != "All Categories":
        query += " AND category=?"
        params.append(category_filter)

    query += " ORDER BY date DESC"
    records = connection.execute(query, params).fetchall()

    total = len(records)
    pending = sum(1 for row in records if row["status"] == "Pending")
    in_progress = sum(1 for row in records if row["status"] == "In Progress")
    resolved = sum(1 for row in records if row["status"] == "Resolved")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Complaints", total)
    col2.metric("Pending", pending)
    col3.metric("In Progress", in_progress)
    col4.metric("Resolved", resolved)

    st.divider()
    st.subheader("Complaint Analysis - Donut Charts")

    if records:
        chart_data = [dict(row) for row in records]
        left, middle, right = st.columns(3)

        with left:
            category_counts = {}
            for row in chart_data:
                category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
            fig_category = px.pie(
                names=list(category_counts.keys()),
                values=list(category_counts.values()),
                hole=0.55,
                title="Problems by Category"
            )
            st.plotly_chart(fig_category, use_container_width=True)

        with middle:
            status_counts = {}
            for status in STATUSES:
                status_counts[status] = sum(1 for row in chart_data if row["status"] == status)
            fig_status = px.pie(
                names=list(status_counts.keys()),
                values=list(status_counts.values()),
                hole=0.55,
                title="Complaints by Status"
            )
            st.plotly_chart(fig_status, use_container_width=True)

        with right:
            hospital_counts = {}
            for row in chart_data:
                hospital_counts[row["hospital"]] = hospital_counts.get(row["hospital"], 0) + 1
            fig_hospital = px.pie(
                names=list(hospital_counts.keys()),
                values=list(hospital_counts.values()),
                hole=0.55,
                title="Complaints by Hospital"
            )
            st.plotly_chart(fig_hospital, use_container_width=True)
    else:
        st.info("No complaints match the selected filters. Charts will appear when complaints are registered.")

    st.divider()
    st.subheader("Complaint Records")

    if not records:
        st.info("No complaints found.")
        connection.close()
        return

    for record in records:
        with st.expander(
            f"{record['id']} | {record['hospital']} | {record['category']} | {record['status']}"
        ):
            st.write("Patient:", record["name"])
            st.write("Phone:", record["phone"])
            st.write("Hospital:", record["hospital"])
            st.write("Category:", record["category"])
            st.write("AI category suggestion:", record["ai_category"] or "Not available")
            st.write("Complaint:", record["complaint"])
            st.write("Status:", record["status"])
            st.write("Date:", record["date"])

            # Show the full conversation/update history for this complaint.
            history = connection.execute("""
                SELECT author, author_role, message, created_at
                FROM complaint_interactions
                WHERE complaint_id=?
                ORDER BY interaction_id
            """, (record["id"],)).fetchall()

            st.markdown("**Interaction History**")
            if history:
                for item in history:
                    st.write(f"{item['created_at']} - {item['author']} ({item['author_role']}): {item['message']}")
            else:
                st.caption("No interaction history.")

    st.divider()
    st.subheader("Update Complaint and Reply to Patient")

    selected_id = st.selectbox(
        "Select Complaint ID",
        [record["id"] for record in records],
        key=f"selected_complaint_{title.replace(' ', '_')}"
    )

    selected_record = next(record for record in records if record["id"] == selected_id)

    new_status = st.selectbox(
        "Complaint Status",
        STATUSES,
        index=STATUSES.index(selected_record["status"]) if selected_record["status"] in STATUSES else 0,
        key=f"status_{title.replace(' ', '_')}"
    )
    reply = st.text_area(
        "Write a reply or progress update for the patient",
        key=f"reply_{title.replace(' ', '_')}"
    )

    if st.button("Save Status and Reply", type="primary", key=f"save_{title.replace(' ', '_')}"):
        connection.execute(
            "UPDATE complaints SET status=? WHERE id=?",
            (new_status, selected_id)
        )
        connection.commit()

        if reply.strip():
            connection.execute("""
                INSERT INTO complaint_interactions
                (complaint_id, author, author_role, message, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                selected_id,
                st.session_state.username,
                st.session_state.user_role,
                reply.strip(),
                datetime.now().strftime("%d-%m-%Y %H:%M")
            ))
            connection.commit()

        connection.close()
        st.success("Complaint status and reply saved.")
        st.rerun()

    connection.close()


# ------------------------------------------------------------
# HOSPITAL MANAGEMENT - MAIN ADMIN ONLY
# ------------------------------------------------------------

if page == "Hospital Management":
    if st.session_state.logged_in and st.session_state.user_role == "Main Admin":
        st.header("🏥 Hospital Management")
        with st.form("add_hospital_form"):
            new_hospital = st.text_input("Hospital Name")
            new_district = st.text_input("District")
            new_location = st.text_input("Hospital Location")
            add_hospital = st.form_submit_button("Register Hospital")

        if add_hospital:
            if not new_hospital.strip() or not new_district.strip() or not new_location.strip():
                st.error("Please fill all hospital fields.")
            else:
                connection = get_connection()
                try:
                    connection.execute("""
                        INSERT INTO hospitals (name, district, location)
                        VALUES (?, ?, ?)
                    """, (new_hospital.strip(), new_district.strip(), new_location.strip()))
                    connection.commit()
                    st.success("Hospital registered.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("This hospital name already exists.")
                finally:
                    connection.close()

        st.subheader("Registered Hospitals")
        connection = get_connection()
        hospital_rows = connection.execute(
            "SELECT * FROM hospitals ORDER BY name"
        ).fetchall()
        connection.close()

        for hospital in hospital_rows:
            st.write(f"**{hospital['name']}** — {hospital['district']} — {hospital['location']}")
    else:
        st.error("Access denied. Main Admin only.")


# ------------------------------------------------------------
# USER MANAGEMENT
# ------------------------------------------------------------

elif page == "User Management":
    if st.session_state.logged_in and st.session_state.user_role == "Main Admin":
        st.header("👥 User Management - Main Admin")
        st.write("Main Admin can create Hospital Admin and Hospital Staff accounts.")

        with st.form("main_admin_create_user"):
            new_username = st.text_input("New Username")
            new_email = st.text_input("Email")
            new_role = st.selectbox("Account Role", ["Hospital Admin", "Hospital Staff"])
            new_user_hospital = st.selectbox("Hospital", fetch_hospitals())
            new_user_password = st.text_input("Temporary Password", type="password")
            create_user = st.form_submit_button("Create Account")

        if create_user:
            if not all([new_username.strip(), new_email.strip(), new_user_password]):
                st.error("Fill all fields.")
            elif len(new_user_password) < 8:
                st.error("Password must contain at least 8 characters.")
            else:
                connection = get_connection()
                try:
                    connection.execute("""
                        INSERT INTO users (username, role, hospital, email, password)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        new_username.strip(),
                        new_role,
                        new_user_hospital,
                        new_email.strip(),
                        hash_password(new_user_password)
                    ))
                    connection.commit()
                    st.success("User account created.")
                except sqlite3.IntegrityError:
                    st.error("That username already exists.")
                finally:
                    connection.close()

        st.divider()
        st.subheader("Existing Accounts")
        connection = get_connection()
        accounts = connection.execute(
            "SELECT username, role, hospital, email FROM users ORDER BY role, username"
        ).fetchall()
        connection.close()

        for account in accounts:
            st.write(
                f"**{account['username']}** | {account['role']} | "
                f"{account['hospital']} | {account['email']}"
            )

        deletable_accounts = [a["username"] for a in accounts if a["role"] != "Main Admin"]
        if deletable_accounts:
            delete_username = st.selectbox("Select account to delete", deletable_accounts)
            if st.button("Delete Selected Account"):
                connection = get_connection()
                connection.execute("DELETE FROM users WHERE username=?", (delete_username,))
                connection.commit()
                connection.close()
                st.success("Account deleted.")
                st.rerun()
    else:
        st.error("Access denied. Main Admin only.")


# ------------------------------------------------------------
# DASHBOARD ROUTING
# ------------------------------------------------------------

elif page == "Main Admin Dashboard":
    if st.session_state.logged_in and st.session_state.user_role == "Main Admin":
        show_dashboard("Main Admin Dashboard", allow_hospital_filter=True)
    else:
        st.error("Access denied. Main Admin only.")

elif page == "Hospital Dashboard":
    if st.session_state.logged_in and st.session_state.user_role == "Hospital Admin":
        show_dashboard(
            "Hospital Dashboard",
            hospital_scope=st.session_state.user_hospital
        )
    else:
        st.error("Access denied. Hospital Admin only.")

elif page == "Staff Dashboard":
    if st.session_state.logged_in and st.session_state.user_role == "Hospital Staff":
        show_dashboard(
            "Staff Dashboard",
            hospital_scope=st.session_state.user_hospital
        )
    else:
        st.error("Access denied.")

elif page == "Staff Management":
    if st.session_state.logged_in and st.session_state.user_role == "Hospital Admin":
        st.header("👥 Staff Management")
        st.write("You can create and manage staff accounts for your hospital only.")

        with st.form("hospital_staff_create"):
            staff_username = st.text_input("Staff Username")
            staff_email = st.text_input("Staff Email")
            staff_password = st.text_input("Temporary Password", type="password")
            create_staff = st.form_submit_button("Create Staff Account")

        if create_staff:
            if not staff_username.strip() or not staff_email.strip() or not staff_password:
                st.error("Please fill all fields.")
            elif len(staff_password) < 8:
                st.error("Password must contain at least 8 characters.")
            else:
                connection = get_connection()
                try:
                    connection.execute("""
                        INSERT INTO users (username, role, hospital, email, password)
                        VALUES (?, 'Hospital Staff', ?, ?, ?)
                    """, (
                        staff_username.strip(),
                        st.session_state.user_hospital,
                        staff_email.strip(),
                        hash_password(staff_password)
                    ))
                    connection.commit()
                    st.success("Staff account created.")
                except sqlite3.IntegrityError:
                    st.error("That username already exists.")
                finally:
                    connection.close()

        connection = get_connection()
        staff_accounts = connection.execute("""
            SELECT username, email FROM users
            WHERE hospital=? AND role='Hospital Staff'
            ORDER BY username
        """, (st.session_state.user_hospital,)).fetchall()
        connection.close()

        st.subheader("Your Hospital Staff")
        if staff_accounts:
            for staff in staff_accounts:
                st.write(f"**{staff['username']}** — {staff['email']}")
            staff_to_delete = st.selectbox(
                "Select staff account to remove",
                [staff["username"] for staff in staff_accounts]
            )
            if st.button("Remove Selected Staff"):
                connection = get_connection()
                connection.execute("""
                    DELETE FROM users
                    WHERE username=? AND hospital=? AND role='Hospital Staff'
                """, (staff_to_delete, st.session_state.user_hospital))
                connection.commit()
                connection.close()
                st.success("Staff account removed.")
                st.rerun()
        else:
            st.info("No staff accounts have been created yet.")
    else:
        st.error("Access denied. Hospital Admin only.")


# ------------------------------------------------------------
# END OF APP
# ------------------------------------------------------------
