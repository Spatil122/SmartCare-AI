import streamlit as st
import sqlite3
import uuid
import random
import hashlib
from datetime import datetime

# ---------------- DATABASE ----------------

conn = sqlite3.connect("smartcare.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
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

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    role TEXT,
    hospital TEXT,
    email TEXT,
    password TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS hospitals (
    name TEXT PRIMARY KEY,
    district TEXT,
    location TEXT
)
""")

cur.execute("""
INSERT OR IGNORE INTO hospitals
VALUES (?, ?, ?)
""", (
    "City General Hospital",
    "Kalaburagi",
    "Main City"
))

conn.commit()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# DEMO ACCOUNTS
demo_users = [
    ("district", "District Commissioner", "ALL",
     "district@example.com", "District@123"),

    ("hospital", "Hospital Admin", "City General Hospital",
     "hospital@example.com", "Hospital@123")
]

for user in demo_users:
    cur.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?)",
        (
            user[0], user[1], user[2], user[3],
            hash_password(user[4])
        )
    )

conn.commit()

# ---------------- PAGE SETTINGS ----------------

st.set_page_config(
    page_title="SmartCare AI",
    page_icon="🏥",
    layout="wide"
)

st.title("🏥 SmartCare AI")
st.caption("Public Grievance & Hospital Service Monitoring System")

# ---------------- SESSION ----------------

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user_role" not in st.session_state:
    st.session_state.user_role = None

if "username" not in st.session_state:
    st.session_state.username = None

if "otp" not in st.session_state:
    st.session_state.otp = None

if "reset_user" not in st.session_state:
    st.session_state.reset_user = None

# ---------------- LANGUAGE ----------------

languages = ["1 - Kannada", "2 - Hindi", "3 - English"]

# ---------------- SIDEBAR ----------------

if st.session_state.logged_in:

    st.sidebar.success(
        "Logged in: " + st.session_state.username
    )

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.username = None
        st.rerun()

    if st.session_state.user_role == "District Commissioner":
        page = st.sidebar.radio(
            "Navigation",
            [
                "Patient Portal",
                "District Dashboard",
                "Hospital Registration"
            ]
        )
    else:
        page = st.sidebar.radio(
            "Navigation",
            ["Patient Portal", "Hospital Dashboard"]
        )

else:
    page = st.sidebar.radio(
        "Navigation",
        ["Patient Portal", "Admin Login"]
    )

# ---------------- PATIENT PORTAL ----------------

if page == "Patient Portal":

    st.header("📝 Register Hospital Complaint")

    language = st.selectbox(
        "Select Language",
        languages
    )

    if language == "1 - Kannada":

        name_label = "ನಿಮ್ಮ ಹೆಸರು"
        phone_label = "ಮೊಬೈಲ್ ಸಂಖ್ಯೆ"
        hospital_label = "ಆಸ್ಪತ್ರೆಯ ಹೆಸರು"
        category_label = "ದೂರಿನ ಪ್ರಕಾರ"
        complaint_label = "ನಿಮ್ಮ ದೂರನ್ನು ವಿವರಿಸಿ"
        button_label = "ದೂರು ಸಲ್ಲಿಸಿ"

        categories = [
            "ವೈದ್ಯರು ಲಭ್ಯವಿಲ್ಲ",
            "ಔಷಧಿ ಲಭ್ಯವಿಲ್ಲ",
            "ಸ್ವಚ್ಛತೆ ಸಮಸ್ಯೆ",
            "ನೀರಿನ ಸಮಸ್ಯೆ",
            "ಹಾಸಿಗೆ ಲಭ್ಯವಿಲ್ಲ",
            "ಆಸ್ಪತ್ರೆ ಸೌಲಭ್ಯ ಸಮಸ್ಯೆ",
            "ಸಿಬ್ಬಂದಿ ವರ್ತನೆ ಸಮಸ್ಯೆ"
        ]

    elif language == "2 - Hindi":

        name_label = "आपका नाम"
        phone_label = "मोबाइल नंबर"
        hospital_label = "अस्पताल का नाम"
        category_label = "शिकायत का प्रकार"
        complaint_label = "अपनी शिकायत बताएं"
        button_label = "शिकायत जमा करें"

        categories = [
            "डॉक्टर उपलब्ध नहीं",
            "दवाइयां उपलब्ध नहीं",
            "सफाई की समस्या",
            "पानी की समस्या",
            "बेड उपलब्ध नहीं",
            "अस्पताल की सुविधाओं की समस्या",
            "कर्मचारियों के व्यवहार की समस्या"
        ]

    else:

        name_label = "Your Name"
        phone_label = "Mobile Number"
        hospital_label = "Hospital Name"
        category_label = "Complaint Category"
        complaint_label = "Describe Your Complaint"
        button_label = "Submit Complaint"

        categories = [
            "Doctor Unavailable",
            "Medicine Unavailable",
            "Cleanliness Problem",
            "Water Problem",
            "Bed Unavailable",
            "Hospital Facilities Problem",
            "Staff Behaviour Problem"
        ]

    name = st.text_input(name_label)

    phone = st.text_input(phone_label,max_chars=10,
                          key="patient_phone")

    # Fetch registered hospitals
    cur.execute("SELECT name FROM hospitals ORDER BY name")

    hospital_options = [
        row[0] for row in cur.fetchall()
    ]

    # Add Other option at the bottom
    if "Other" not in hospital_options:
        hospital_options.append("Other")

    hospital_choice = st.selectbox(
        hospital_label,
        hospital_options,
        key="patient_hospital"
    )

    # Ask for hospital name only if Other is selected
    if hospital_choice == "Other":

        hospital = st.text_input(
            "Enter your hospital name",
            key="other_hospital"
        )

    else:

        hospital = hospital_choice

    # These fields always remain visible
    category = st.selectbox(
        category_label,
        categories
    )

    complaint = st.text_area(
        complaint_label
    )

    if st.button(button_label):

        if (
    name.strip()
    and phone.isdigit()
    and len(phone) == 10
    and hospital.strip()
    and complaint.strip()
):

            complaint_id = "SC-" + uuid.uuid4().hex[:8].upper()

            cur.execute("""
                INSERT INTO complaints
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                complaint_id,
                name,
                phone,
                hospital.strip(),
                category,
                complaint,
                "Pending",
                datetime.now().strftime("%d-%m-%Y %H:%M")
            ))

            conn.commit()

            st.success("Complaint Registered Successfully!")
            st.info("Your Complaint ID: " + complaint_id)

        else:

           st.warning("Please fill all fields and enter a valid 10-digit mobile number.")

# ---------------- ADMIN LOGIN ----------------

elif page == "Admin Login":

    st.header("🔐 Admin Login")

    if not st.session_state.logged_in:

        username = st.text_input("Username")

        password = st.text_input(
            "Password",
            type="password"
        )

        if st.button("Login"):

            cur.execute(
                "SELECT * FROM users WHERE username=?",
                (username,)
            )

            user = cur.fetchone()

            if user and user[4] == hash_password(password):

                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.user_role = user[1]

                st.success("Login successful!")
                st.rerun()

            else:
                st.error("Invalid username or password.")

    st.divider()

    st.subheader("Forgot Password?")

    email = st.text_input(
        "Enter your registered email",
        key="forgot_email"
    )

    if st.button("Generate Reset OTP"):

        cur.execute(
            "SELECT username FROM users WHERE email=?",
            (email,)
        )

        account = cur.fetchone()

        if account:

            st.session_state.reset_user = account[0]
            st.session_state.otp = str(
                random.randint(100000, 999999)
            )

            # DEMONSTRATION ONLY:
            # This displays OTP locally; it does not email it.
            st.warning(
                "DEMO OTP (not emailed): "
                + st.session_state.otp
            )

        else:
            st.error("Email address not registered.")

    if st.session_state.otp:

        entered_otp = st.text_input(
            "Enter OTP",
            key="entered_otp"
        )

        new_password = st.text_input(
            "Create New Password",
            type="password"
        )

        confirm_password = st.text_input(
            "Confirm New Password",
            type="password"
        )

        if st.button("Reset Password"):

            if entered_otp != st.session_state.otp:
                st.error("Incorrect OTP.")

            elif len(new_password) < 8:
                st.error("Password must contain at least 8 characters.")

            elif new_password != confirm_password:
                st.error("Passwords do not match.")

            else:

                cur.execute(
                    "UPDATE users SET password=? WHERE username=?",
                    (
                        hash_password(new_password),
                        st.session_state.reset_user
                    )
                )

                conn.commit()

                st.session_state.otp = None
                st.session_state.reset_user = None

                st.success("Password changed successfully!")

# ---------------- DASHBOARD FUNCTION ----------------
# ---------------- HOSPITAL REGISTRATION ----------------

if page == "Hospital Registration":

    if (
        st.session_state.logged_in
        and st.session_state.user_role == "District Commissioner"
    ):

        st.header("🏥 Register New Hospital")

        with st.form("hospital_registration_form"):

            hospital_name = st.text_input("Hospital Name")

            district = st.text_input("District")

            location = st.text_input("Hospital Location")

            st.subheader("Create Hospital Admin Account")

            admin_username = st.text_input("Admin Username")

            admin_email = st.text_input("Admin Email")

            admin_password = st.text_input(
                "Admin Password",
                type="password"
            )

            confirm_password = st.text_input(
                "Confirm Password",
                type="password"
            )

            submit = st.form_submit_button(
                "Register Hospital"
            )

            if submit:

                if not all([
                    hospital_name.strip(),
                    district.strip(),
                    location.strip(),
                    admin_username.strip(),
                    admin_email.strip(),
                    admin_password,
                    confirm_password
                ]):

                    st.warning("Please fill all fields.")

                elif len(admin_password) < 8:

                    st.error("Password must contain at least 8 characters.")

                elif admin_password != confirm_password:

                    st.error("Passwords do not match.")

                else:

                    cur.execute(
                        "SELECT name FROM hospitals WHERE name=?",
                        (hospital_name.strip(),)
                    )

                    existing_hospital = cur.fetchone()

                    cur.execute(
                        "SELECT username FROM users WHERE username=?",
                        (admin_username.strip(),)
                    )

                    existing_admin = cur.fetchone()

                    if existing_hospital:

                        st.error("Hospital already registered.")

                    elif existing_admin:

                        st.error("Username already exists.")

                    else:

                        cur.execute("""
                            INSERT INTO hospitals
                            VALUES (?, ?, ?)
                        """, (
                            hospital_name.strip(),
                            district.strip(),
                            location.strip()
                        ))

                        cur.execute("""
                            INSERT INTO users
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            admin_username.strip(),
                            "Hospital Admin",
                            hospital_name.strip(),
                            admin_email.strip(),
                            hash_password(admin_password)
                        ))

                        conn.commit()

                        st.success("Hospital registered successfully!")

                        st.info(
                            "Hospital Admin Username: "
                            + admin_username
                        )

    else:

        st.error("Only District Commissioner can register hospitals.")
def show_dashboard(role, hospital_name=None):

    st.header("📊 " + role + " Dashboard")

    if hospital_name:

        cur.execute(
            "SELECT * FROM complaints WHERE hospital=? ORDER BY date DESC",
            (hospital_name,)
        )

    else:

        cur.execute(
            "SELECT * FROM complaints ORDER BY date DESC"
        )

    records = cur.fetchall()

    total = len(records)

    pending = sum(1 for r in records if r[6] == "Pending")
    progress = sum(1 for r in records if r[6] == "In Progress")
    resolved = sum(1 for r in records if r[6] == "Resolved")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Complaints", total)
    c2.metric("Pending", pending)
    c3.metric("In Progress", progress)
    c4.metric("Resolved", resolved)

    st.divider()

    st.subheader("Complaint Records")

    for record in records:

        with st.expander(
            f"{record[0]} | {record[3]} | {record[6]}"
        ):

            st.write("Patient:", record[1])
            st.write("Phone:", record[2])
            st.write("Hospital:", record[3])
            st.write("Category:", record[4])
            st.write("Complaint:", record[5])
            st.write("Status:", record[6])
            st.write("Date:", record[7])

    if records:

        st.divider()
        st.subheader("Update Complaint Status")

        selected_id = st.selectbox(
            "Select Complaint ID",
            [r[0] for r in records]
        )

        new_status = st.selectbox(
            "New Status",
            ["Pending", "In Progress", "Resolved"]
        )

        if st.button("Update Status"):

            cur.execute(
                "UPDATE complaints SET status=? WHERE id=?",
                (new_status, selected_id)
            )

            conn.commit()

            st.success("Status updated successfully!")
            st.rerun()

# ---------------- DISTRICT DASHBOARD ----------------


if page == "District Dashboard":

    if st.session_state.logged_in and st.session_state.user_role == "District Commissioner":

        show_dashboard("District Commissioner")

    else:
        st.error("Access denied. Please login as District Commissioner.")

# ---------------- HOSPITAL DASHBOARD ----------------

if page == "Hospital Dashboard":

    if (
        st.session_state.logged_in
        and st.session_state.user_role == "Hospital Admin"
    ):

        cur.execute(
            "SELECT hospital FROM users WHERE username=?",
            (st.session_state.username,)
        )

        account = cur.fetchone()

        if account:
            show_dashboard(
                "Hospital Admin",
                account[0]
            )

    else:
        st.error("Access denied. Please login as Hospital Admin.")
