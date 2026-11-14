
import streamlit as st
import sqlite3
import hashlib
import uuid
import requests
import json
import os
from datetime import datetime, date

# =========================================================
# SMARTCARE AI - COMPLETE SINGLE FILE APPLICATION
# =========================================================

st.set_page_config(
    page_title="SMARTCARE AI",
    page_icon="🏥",
    layout="wide"
)

DB_NAME = "smartcare.db"

CATEGORIES = [
    "General Medicine",
    "Dental",
    "Bone / Orthopaedics",
    "X-ray / Radiology",
    "Cardiology",
    "Eye Care",
    "ENT",
    "Gynaecology",
    "Paediatrics",
    "Dermatology",
    "Neurology",
    "Other"
]

LANGUAGES = ["English", "ಕನ್ನಡ", "हिन्दी"]
STATUSES = ["Available", "Unavailable", "On Leave"]


# =========================================================
# DATABASE CONNECTION AND TABLE CREATION
# =========================================================

def get_db():
    connection = sqlite3.connect(DB_NAME, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def setup_database():
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            hospital TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            district TEXT,
            active INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            hospital TEXT,
            category TEXT,
            complaint TEXT,
            status TEXT DEFAULT 'Pending',
            date TEXT,
            ai_category TEXT,
            ai_summary TEXT,
            ai_priority TEXT,
            ai_urgent TEXT,
            ai_reason TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hospital TEXT NOT NULL,
            category TEXT NOT NULL,
            service_type TEXT,
            availability TEXT DEFAULT 'Available',
            timing TEXT,
            next_date TEXT
        )
    """)

    # Add missing AI columns to older complaint databases.
    existing_columns = [
        row["name"] for row in
        cursor.execute("PRAGMA table_info(complaints)").fetchall()
    ]

    for column in ["ai_category", "ai_summary", "ai_priority",
                   "ai_urgent", "ai_reason"]:
        if column not in existing_columns:
            cursor.execute(
                f"ALTER TABLE complaints ADD COLUMN {column} TEXT"
            )

    # Create the first administrator only if no users exist.
    # Change this password immediately after your first login.
    user_count = cursor.execute(
        "SELECT COUNT(*) AS total FROM users"
    ).fetchone()["total"]

    if user_count == 0:
        cursor.execute("""
            INSERT INTO users (username, password, role, hospital)
            VALUES (?, ?, ?, ?)
        """, (
            "districtadmin",
            hash_password("ChangeMe123!"),
            "District Admin",
            None
        ))

    connection.commit()
    connection.close()


# =========================================================
# PASSWORD SECURITY
# =========================================================

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password, saved_hash):
    return hash_password(password) == saved_hash


# =========================================================
# INITIALISE APPLICATION
# =========================================================

def initialise():
    setup_database()

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if "username" not in st.session_state:
        st.session_state.username = ""

    if "role" not in st.session_state:
        st.session_state.role = ""

    if "hospital" not in st.session_state:
        st.session_state.hospital = ""


initialise()


# =========================================================
# DATABASE HELPER FUNCTIONS
# =========================================================


def get_hospitals():
    """Safely retrieve active hospitals from the database."""
    connection = get_db()

    try:
        cursor = connection.cursor()

        # Check whether the hospitals table exists.
        table = cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='hospitals'
        """).fetchone()

        if table is None:
            return []

        # Check which columns are available.
        columns = [
            row["name"]
            for row in cursor.execute(
                "PRAGMA table_info(hospitals)"
            ).fetchall()
        ]

        if "name" not in columns:
            return []

        # Older databases may not have an active column.
        if "active" in columns:
            rows = cursor.execute("""
                SELECT name FROM hospitals
                WHERE active=1 ORDER BY name
            """).fetchall()
        else:
            rows = cursor.execute("""
                SELECT name FROM hospitals ORDER BY name
            """).fetchall()

        return [row["name"] for row in rows if row["name"]]

    finally:
        connection.close()



def get_doctors(hospital=None, category=None):
    connection = get_db()

    query = "SELECT * FROM doctors WHERE 1=1"
    values = []

    if hospital:
        query += " AND hospital=?"
        values.append(hospital)

    if category:
        query += " AND category=?"
        values.append(category)

    query += " ORDER BY name"

    rows = connection.execute(query, values).fetchall()
    connection.close()
    return rows


# =========================================================
# OPTIONAL LOCAL OLLAMA AI ANALYSIS
# =========================================================

def analyse_complaint(complaint, category):
    """
    Uses a locally running Ollama model.
    No paid AI API is used.
    """

    ollama_url = os.getenv(
        "OLLAMA_URL",
        "http://localhost:11434/api/generate"
    )

    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")

    prompt = f"""
    Analyse this hospital complaint.

    Patient selected category: {category}
    Complaint: {complaint}

    Return only JSON with these keys:
    category, summary, priority, urgent, reason.

    Priority must be Normal, Medium, High, or Critical.
    Urgent must be Yes or No.
    Do not claim to provide a medical diagnosis.
    """

    try:
        response = requests.post(
            ollama_url,
            json={
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=30
        )

        response.raise_for_status()
        result = response.json().get("response", "{}")
        data = json.loads(result)

        return {
            "category": str(data.get("category", category)),
            "summary": str(data.get("summary", "")),
            "priority": str(data.get("priority", "Normal")),
            "urgent": str(data.get("urgent", "No")),
            "reason": str(data.get("reason", ""))
        }

    except Exception:
        return {
            "category": category,
            "summary": "AI analysis is currently unavailable.",
            "priority": "Normal",
            "urgent": "No",
            "reason": "Please arrange a manual staff review."
        }


# =========================================================
# APPLICATION HEADER
# =========================================================

st.title("🏥 SMARTCARE AI")
st.caption("Smart Hospital Complaint and Service Management System")

if not st.session_state.logged_in:
    login_tab, register_tab = st.tabs(["Login", "Patient Complaint"])

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    with login_tab:
        st.subheader("Administrator / Hospital Staff Login")

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login", use_container_width=True):
            connection = get_db()

            user = connection.execute(
                "SELECT * FROM users WHERE username=?",
                (username.strip(),)
            ).fetchone()

            connection.close()

            if user and verify_password(password, user["password"]):
                st.session_state.logged_in = True
                st.session_state.username = user["username"]
                st.session_state.role = user["role"]
                st.session_state.hospital = user["hospital"] or ""
                st.rerun()
            else:
                st.error("Incorrect username or password.")

        st.info(
            "First login: username districtadmin | "
            "password ChangeMe123! "
            "Change this password after logging in."
        )

    # -----------------------------------------------------
    # PATIENT COMPLAINT REGISTRATION
    # -----------------------------------------------------

    with register_tab:
        st.subheader("Register a Hospital Complaint")

        hospitals = get_hospitals()

        if not hospitals:
            st.warning("No hospitals have been registered yet.")
        else:
            with st.form("patient_complaint_form"):
                patient_name = st.text_input("Patient Full Name")
                patient_phone = st.text_input("Phone Number")

                selected_hospital = st.selectbox(
                    "Select Hospital",
                    hospitals
                )

                selected_category = st.selectbox(
                    "Select Complaint Category",
                    CATEGORIES
                )

                complaint_text = st.text_area(
                    "Describe Your Complaint",
                    height=150
                )

                submitted = st.form_submit_button(
                    "Submit Complaint",
                    use_container_width=True
                )

                if submitted:
                    if not patient_name.strip():
                        st.error("Please enter the patient name.")
                    elif not patient_phone.strip():
                        st.error("Please enter the phone number.")
                    elif not complaint_text.strip():
                        st.error("Please describe your complaint.")
                    else:
                        with st.spinner("Registering complaint..."):
                            ai = analyse_complaint(
                                complaint_text,
                                selected_category
                            )

                            reference = (
                                "SC-" + uuid.uuid4().hex[:8].upper()
                            )

                            connection = get_db()

                            connection.execute("""
                                INSERT INTO complaints (
                                    id, name, phone, hospital, category,
                                    complaint, status, date, ai_category,
                                    ai_summary, ai_priority, ai_urgent,
                                    ai_reason
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                reference,
                                patient_name.strip(),
                                patient_phone.strip(),
                                selected_hospital,
                                selected_category,
                                complaint_text.strip(),
                                "Pending",
                                datetime.now().isoformat(
                                    timespec="seconds"
                                ),
                                ai["category"],
                                ai["summary"],
                                ai["priority"],
                                ai["urgent"],
                                ai["reason"]
                            ))

                            connection.commit()
                            connection.close()

                        st.success("Complaint registered successfully!")
                        st.code(reference)
                        st.info(
                            "Save this reference number to track your complaint."
                        )

    st.stop()


# =========================================================
# LOGGED-IN NAVIGATION
# =========================================================

st.sidebar.success(
    f"Logged in: {st.session_state.username}"
)
st.sidebar.write(f"Role: {st.session_state.role}")

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.hospital = ""
    st.rerun()

# Convert old account role names into supported role names.
role = str(st.session_state.role).strip().lower()

if role in ["district admin", "district_admin", "admin", "main admin"]:
    st.session_state.role = "District Admin"

    menu = [
        "District Dashboard",
        "Manage Hospitals",
        "Manage Users",
        "Manage Doctors and Services",
        "All Complaints",
        "Doctor Availability"
    ]

elif role in ["hospital admin", "hospital_admin", "hospital"]:
    st.session_state.role = "Hospital Admin"

    menu = [
        "Hospital Dashboard",
        "Manage Doctors and Services",
        "Hospital Complaints",
        "Doctor Availability"
    ]
else:
    st.error("Your account role is not recognised.")
    st.write("ROLE FOUND IN DATABASE:", repr(st.session_state.role))
    st.stop()


page = st.sidebar.radio("Navigation", menu)


# =========================================================
# DASHBOARD
# =========================================================

def show_dashboard(hospital=None):
    
    import pandas as pd

    st.divider()
    st.subheader("📊 Graphical Complaint Analysis")

    if not records:
        st.info("No complaint data available.")
        return

    # 1. Circular chart: Complaint categories.
    category_counts = {}
    for record in records:
        category = record["category"] or "Other"
        category_counts[category] = category_counts.get(category, 0) + 1

    st.markdown("### 🏥 Complaints by Category")

    category_df = pd.DataFrame({
        "Category": list(category_counts.keys()),
        "Complaints": list(category_counts.values())
    })

    st.plotly_chart(
        __import__("plotly.express").express.pie(
            category_df,
            names="Category",
            values="Complaints",
            hole=0.45,
            title="Medical Complaint Distribution"
        ),
        use_container_width=True
    )

    # 2. Circular chart: Complaint status.
    st.markdown("### 📋 Complaint Status")

    status_df = pd.DataFrame({
        "Status": ["Pending", "In Progress", "Resolved"],
        "Count": [pending, progress, resolved]
    })

    st.plotly_chart(
        __import__("plotly.express").express.pie(
            status_df,
            names="Status",
            values="Count",
            hole=0.45,
            title="Complaint Status Distribution"
        ),
        use_container_width=True
    )

    # 3. Circular chart: Hospital-wise complaints.
    if not hospital:
        st.markdown("### 🏥 Hospital-wise Complaints")

        hospital_counts = {}
        for record in records:
            name = record["hospital"] or "Other"
            hospital_counts[name] = hospital_counts.get(name, 0) + 1

        hospital_df = pd.DataFrame({
            "Hospital": list(hospital_counts.keys()),
            "Count": list(hospital_counts.values())
        })

        st.plotly_chart(
            __import__("plotly.express").express.pie(
                hospital_df,
                names="Hospital",
                values="Count",
                hole=0.45,
                title="Hospital Complaint Distribution"
            ),
            use_container_width=True
        )




# =========================================================
# MANAGE HOSPITALS
# =========================================================

elif page == "Manage Hospitals":
    # Display the hospital management page.
    st.header("🏥 Manage Hospitals")

    # Form to register a new hospital.
    with st.form("add_hospital_form"):
        hospital_name = st.text_input("Hospital Name")
        district_name = st.text_input("District")
        add_hospital = st.form_submit_button("Add Hospital")

        if add_hospital:
            if not hospital_name.strip():
                st.error("Enter a hospital name.")
            else:
                try:
                    connection = get_db()
                    connection.execute("""
                        INSERT INTO hospitals (name, district)
                        VALUES (?, ?)
                    """, (hospital_name.strip(), district_name.strip()))
                    connection.commit()
                    connection.close()
                    st.success("Hospital added successfully.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("This hospital already exists.")

    # Get all registered hospitals.
    connection = get_db()
    hospitals = connection.execute(
        "SELECT * FROM hospitals ORDER BY name"
    ).fetchall()
    connection.close()

    st.subheader("Registered Hospitals")

    # Display hospitals and allow deactivation.
    for hospital in hospitals:
        st.write(
            f"{hospital['name']} | District: {hospital['district']} | "
            f"Active: {'Yes' if hospital['active'] else 'No'}"
        )

        if hospital["active"]:
            if st.button(
                f"Deactivate {hospital['name']}",
                key=f"deactivate_{hospital['id']}"
            ):
                connection = get_db()
                connection.execute(
                    "UPDATE hospitals SET active=0 WHERE id=?",
                    (hospital["id"],)
                )
                connection.commit()
                connection.close()
                st.rerun()

# =========================================================
# MANAGE STAFF USERS
# =========================================================


# =========================================================
# MANAGE ADMINISTRATORS AND STAFF ACCOUNTS
# =========================================================

elif page == "Manage Users":
    st.header("👥 User and Administrator Management")

    if st.session_state.role != "District Admin":
        st.error("Only District Admin can manage accounts.")
        st.stop()

    hospitals = get_hospitals()

    # Create administrator or hospital staff account.
    st.subheader("Create New Account")

    with st.form("create_user_form"):
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")

        new_role = st.selectbox(
            "Account Role",
            ["Hospital Admin", "District Admin"]
        )

        if new_role == "Hospital Admin":
            if hospitals:
                new_hospital = st.selectbox(
                    "Assign Hospital",
                    hospitals
                )
            else:
                new_hospital = None
        else:
            new_hospital = None

        create_account = st.form_submit_button("Create Account")

        if create_account:
            if not new_username.strip() or not new_password:
                st.error("Enter username and password.")
            elif len(new_password) < 8:
                st.error("Password must contain at least 8 characters.")
            elif new_role == "Hospital Admin" and not new_hospital:
                st.error("Register a hospital first.")
            else:
                try:
                    connection = get_db()
                    connection.execute("""
                        INSERT INTO users
                        (username, password, role, hospital)
                        VALUES (?, ?, ?, ?)
                    """, (
                        new_username.strip(),
                        hash_password(new_password),
                        new_role,
                        new_hospital
                    ))
                    connection.commit()
                    connection.close()

                    st.success("Account created successfully.")
                    st.rerun()

                except sqlite3.IntegrityError:
                    st.error("This username already exists.")

    st.divider()

    # Display all existing accounts.
    st.subheader("Registered Accounts")

    connection = get_db()
    users = connection.execute("""
        SELECT id, username, role, hospital
        FROM users
        ORDER BY username
    """).fetchall()
    connection.close()

    if not users:
        st.info("No accounts found.")

    for user in users:
        with st.expander(
            f"{user['username']} | {user['role']}"
        ):
            st.write("Username:", user["username"])
            st.write("Role:", user["role"])
            st.write("Hospital:", user["hospital"] or "All hospitals")

            # Reset an existing user's password.
            with st.form(f"reset_password_{user['id']}"):
                replacement_password = st.text_input(
                    "New Password",
                    type="password"
                )

                reset = st.form_submit_button("Reset Password")

                if reset:
                    if len(replacement_password) < 8:
                        st.error("Password must contain at least 8 characters.")
                    else:
                        connection = get_db()
                        connection.execute("""
                            UPDATE users
                            SET password=?
                            WHERE id=?
                        """, (
                            hash_password(replacement_password),
                            user["id"]
                        ))
                        connection.commit()
                        connection.close()

                        st.success("Password updated successfully.")

            # Do not allow deleting the currently logged-in account.
            if user["username"] != st.session_state.username:
                if st.button(
                    "Remove Account",
                    key=f"remove_user_{user['id']}"
                ):
                    connection = get_db()
                    connection.execute(
                        "DELETE FROM users WHERE id=?",
                        (user["id"],)
                    )
                    connection.commit()
                    connection.close()

                    st.success("Account removed.")
                    st.rerun()
            else:
                st.info("You cannot remove your currently logged-in account.")
# =========================================================
# ADD AND MANAGE DOCTORS AND SERVICES
# =========================================================

elif page == "Manage Doctors and Services":
    st.header("🩺 Manage Doctors and Medical Services")

    hospitals = get_hospitals()

    if st.session_state.role == "Hospital Admin":
        hospitals = [st.session_state.hospital]

    if not hospitals:
        st.warning("No active hospitals available.")
    else:
        with st.form("add_doctor_form"):
            doctor_name = st.text_input("Doctor / Service Name")
            hospital_name = st.selectbox("Hospital", hospitals)
            category = st.selectbox("Medical Category", CATEGORIES)

            service_type = st.text_input(
                "Service Type (Doctor, X-ray, Scan, etc.)"
            )

            timing = st.text_input(
                "Available Timings (example: 9 AM - 1 PM)"
            )

            next_date = st.date_input(
                "Next Available Date",
                value=date.today()
            )

            availability = st.selectbox(
                "Availability",
                STATUSES
            )

            add_doctor = st.form_submit_button("Save Doctor / Service")

            if add_doctor:
                if not doctor_name.strip():
                    st.error("Enter a doctor or service name.")
                else:
                    connection = get_db()
                    connection.execute("""
                        INSERT INTO doctors (
                            name, hospital, category, service_type,
                            availability, timing, next_date
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        doctor_name.strip(),
                        hospital_name,
                        category,
                        service_type.strip(),
                        availability,
                        timing.strip(),
                        str(next_date)
                    ))
                    connection.commit()
                    connection.close()

                    st.success("Doctor / service added.")
                    st.rerun()

    st.divider()
    st.subheader("Existing Doctors and Services")

    selected_hospital = st.selectbox(
        "Filter Hospital",
        hospitals,
        key="doctor_filter"
    )

    doctors = get_doctors(hospital=selected_hospital)

    for doctor in doctors:
        with st.expander(
            f"{doctor['name']} | {doctor['category']}"
        ):
            st.write("Hospital:", doctor["hospital"])
            st.write("Service:", doctor["service_type"])
            st.write("Timings:", doctor["timing"])
            st.write("Next available:", doctor["next_date"])
            st.write("Availability:", doctor["availability"])

            new_status = st.selectbox(
                "Update Availability",
                STATUSES,
                index=STATUSES.index(doctor["availability"])
                if doctor["availability"] in STATUSES else 0,
                key=f"status_{doctor['id']}"
            )

            if st.button(
                "Update",
                key=f"update_doctor_{doctor['id']}"
            ):
                connection = get_db()
                connection.execute(
                    "UPDATE doctors SET availability=? WHERE id=?",
                    (new_status, doctor["id"])
                )
                connection.commit()
                connection.close()
                st.success("Availability updated.")
                st.rerun()

            if st.session_state.role == "District Admin":
                if st.button(
                    "Delete Doctor / Service",
                    key=f"delete_doctor_{doctor['id']}"
                ):
                    connection = get_db()
                    connection.execute(
                        "DELETE FROM doctors WHERE id=?",
                        (doctor["id"],)
                    )
                    connection.commit()
                    connection.close()
                    st.rerun()


# =========================================================
# PATIENT-FACING DOCTOR AVAILABILITY
# =========================================================

elif page == "Doctor Availability":
    st.header("🔎 Check Doctor and Service Availability")

    hospitals = get_hospitals()

    if not hospitals:
        st.warning("No hospitals are registered.")
    else:
        selected_hospital = st.selectbox(
            "Select Hospital",
            hospitals,
            key="availability_hospital"
        )

        selected_category = st.selectbox(
            "Select Medical Category",
            CATEGORIES,
            key="availability_category"
        )

        results = get_doctors(
            hospital=selected_hospital,
            category=selected_category
        )

        if not results:
            st.info("No doctors or services are listed in this category.")
        else:
            for doctor in results:
                st.markdown(f"### {doctor['name']}")

                st.write("Service:", doctor["service_type"])
                st.write("Category:", doctor["category"])
                st.write("Hospital:", doctor["hospital"])
                st.write("Timings:", doctor["timing"])
                st.write("Next available date:", doctor["next_date"])

                if doctor["availability"] == "Available":
                    st.success("Available")
                elif doctor["availability"] == "On Leave":
                    st.warning("On Leave")
                else:
                    st.error("Unavailable")

                st.divider()


# =========================================================
# COMPLAINT MANAGEMENT
# =========================================================

elif page in ["All Complaints", "Hospital Complaints"]:
    st.header("📋 Complaint Management")

    if st.session_state.role == "Hospital Admin":
        connection = get_db()
        records = connection.execute("""
            SELECT * FROM complaints
            WHERE hospital=?
            ORDER BY date DESC
        """, (st.session_state.hospital,)).fetchall()
        connection.close()
    else:
        connection = get_db()
        records = connection.execute(
            "SELECT * FROM complaints ORDER BY date DESC"
        ).fetchall()
        connection.close()

    if not records:
        st.info("No complaints found.")
    else:
        for record in records:
            with st.expander(
                f"{record['id']} | {record['hospital']} | {record['status']}"
            ):
                st.write("Patient:", record["name"])
                st.write("Phone:", record["phone"])
                st.write("Category:", record["category"])
                st.write("Complaint:", record["complaint"])
                st.write("Date:", record["date"])

                st.markdown("**AI Suggestion**")
                st.write("Suggested category:", record["ai_category"])
                st.write("Summary:", record["ai_summary"])
                st.write("Priority:", record["ai_priority"])
                st.write("Urgent:", record["ai_urgent"])
                st.write("Reason:", record["ai_reason"])

                new_status = st.selectbox(
                    "Complaint Status",
                    ["Pending", "In Progress", "Resolved"],
                    index=[
                        "Pending", "In Progress", "Resolved"
                    ].index(record["status"])
                    if record["status"] in [
                        "Pending", "In Progress", "Resolved"
                    ] else 0,
                    key=f"complaint_status_{record['id']}"
                )

                if st.button(
                    "Save Complaint Status",
                    key=f"save_complaint_{record['id']}"
                ):
                    connection = get_db()
                    connection.execute(
                        "UPDATE complaints SET status=? WHERE id=?",
                        (new_status, record["id"])
                    )
                    connection.commit()
                    connection.close()

                    st.success("Complaint status updated.")
                    st.rerun()


# =========================================================
# FOOTER
# =========================================================

st.divider()
st.caption(
    "SMARTCARE AI | AI suggestions are not medical advice. "
    "Staff must verify complaint priorities and service availability."
)


