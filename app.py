
# =========================================================
# DASHBOARD AND PAGE NAVIGATION
# =========================================================

import pandas as pd
import plotly.express as px


def show_dashboard(hospital=None):
    """Show complaint statistics and circular charts."""

    connection = get_db()

    if hospital:
        records = connection.execute(
            "SELECT * FROM complaints WHERE hospital=?",
            (hospital,)
        ).fetchall()
    else:
        records = connection.execute(
            "SELECT * FROM complaints"
        ).fetchall()

    connection.close()

    st.header("📊 Hospital Dashboard")

    if not records:
        st.info("No complaint records available yet.")
        return

    # Count complaint statuses.
    pending = sum(1 for r in records if r["status"] == "Pending")
    progress = sum(1 for r in records if r["status"] == "In Progress")
    resolved = sum(1 for r in records if r["status"] == "Resolved")

    # Display summary numbers.
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Complaints", len(records))
    col2.metric("Pending", pending)
    col3.metric("In Progress", progress)
    col4.metric("Resolved", resolved)

    st.divider()
    st.subheader("📊 Circular Complaint Charts")

    # Group complaints using the patient's selected category.
    category_counts = {}
    for record in records:
        category = (record["category"] or "").strip() or "Other"
        category_counts[category] = category_counts.get(category, 0) + 1

    category_df = pd.DataFrame(
        list(category_counts.items()),
        columns=["Category", "Complaints"]
    )

    st.markdown("### 🏥 Category-wise Complaints")

    st.plotly_chart(
        px.pie(
            category_df,
            names="Category",
            values="Complaints",
            hole=0.45,
            title="Complaints by Medical Category"
        ),
        use_container_width=True
    )

    # Group complaints by status.
    status_df = pd.DataFrame({
        "Status": ["Pending", "In Progress", "Resolved"],
        "Count": [pending, progress, resolved]
    })

    st.markdown("### 📋 Complaint Status")

    st.plotly_chart(
        px.pie(
            status_df[status_df["Count"] > 0],
            names="Status",
            values="Count",
            hole=0.45,
            title="Complaint Status Distribution"
        ),
        use_container_width=True
    )

    # Show hospital-wise distribution for the District Admin.
    if not hospital:
        hospital_counts = {}

        for record in records:
            name = (record["hospital"] or "").strip() or "Other"
            hospital_counts[name] = hospital_counts.get(name, 0) + 1

        hospital_df = pd.DataFrame(
            list(hospital_counts.items()),
            columns=["Hospital", "Complaints"]
        )

        st.markdown("### 🏥 Hospital-wise Complaints")

        st.plotly_chart(
            px.pie(
                hospital_df,
                names="Hospital",
                values="Complaints",
                hole=0.45,
                title="Hospital Complaint Distribution"
            ),
            use_container_width=True
        )


# =========================================================
# DISPLAY THE SELECTED PAGE
# =========================================================

if page == "District Dashboard":
    show_dashboard()

elif page == "Hospital Dashboard":
    show_dashboard(st.session_state.hospital)


elif page == "Manage Hospitals":
    st.header("🏥 Manage Hospitals")

    with st.form("add_hospital_form"):
        hospital_name = st.text_input("Hospital Name")
        district_name = st.text_input("District")

        add_hospital = st.form_submit_button("Add Hospital")

        if add_hospital:
            if not hospital_name.strip():
                st.error("Enter a hospital name.")
            else:
                connection = get_db()

                try:
                    connection.execute("""
                        INSERT INTO hospitals (name, district)
                        VALUES (?, ?)
                    """, (hospital_name.strip(), district_name.strip()))

                    connection.commit()
                    st.success("Hospital added successfully.")
                    st.rerun()

                except sqlite3.IntegrityError:
                    st.error("This hospital already exists.")

                finally:
                    connection.close()

    connection = get_db()
    hospitals = connection.execute(
        "SELECT * FROM hospitals ORDER BY name"
    ).fetchall()
    connection.close()

    st.subheader("Registered Hospitals")

    for hospital_record in hospitals:
        st.write(
            f"{hospital_record['name']} | "
            f"District: {hospital_record['district'] or 'Not specified'} | "
            f"Active: {'Yes' if hospital_record['active'] else 'No'}"
        )

        if hospital_record["active"]:
            if st.button(
                f"Deactivate {hospital_record['name']}",
                key=f"deactivate_{hospital_record['id']}"
            ):
                connection = get_db()
                connection.execute(
                    "UPDATE hospitals SET active=0 WHERE id=?",
                    (hospital_record["id"],)
                )
                connection.commit()
                connection.close()
                st.rerun()


# =========================================================
# MANAGE USERS
# =========================================================

elif page == "Manage Users":
    st.header("👥 User and Administrator Management")

    if st.session_state.role != "District Admin":
        st.error("Only District Admin can manage accounts.")
        st.stop()

    hospitals = get_hospitals()

    st.subheader("Create New Account")

    with st.form("create_user_form"):
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")

        new_role = st.selectbox(
            "Account Role",
            ["Hospital Admin", "District Admin"]
        )

        if new_role == "Hospital Admin" and hospitals:
            new_hospital = st.selectbox("Assign Hospital", hospitals)
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
                connection = get_db()

                try:
                    connection.execute("""
                        INSERT INTO users (username, password, role, hospital)
                        VALUES (?, ?, ?, ?)
                    """, (
                        new_username.strip(),
                        hash_password(new_password),
                        new_role,
                        new_hospital
                    ))
                    connection.commit()
                    st.success("Account created successfully.")
                    st.rerun()

                except sqlite3.IntegrityError:
                    st.error("This username already exists.")

                finally:
                    connection.close()

    st.divider()
    st.subheader("Registered Accounts")

    connection = get_db()
    users = connection.execute("""
        SELECT id, username, role, hospital
        FROM users ORDER BY username
    """).fetchall()
    connection.close()

    for user in users:
        with st.expander(f"{user['username']} | {user['role']}"):
            st.write("Hospital:", user["hospital"] or "All hospitals")

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
                        connection.execute(
                            "UPDATE users SET password=? WHERE id=?",
                            (hash_password(replacement_password), user["id"])
                        )
                        connection.commit()
                        connection.close()
                        st.success("Password updated successfully.")

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
                    st.rerun()


# =========================================================
# MANAGE DOCTORS AND MEDICAL SERVICES
# =========================================================

elif page == "Manage Doctors and Services":
    st.header("🩺 Manage Doctors and Medical Services")

    hospitals = get_hospitals()

    if st.session_state.role == "Hospital Admin":
        hospitals = [st.session_state.hospital] if st.session_state.hospital else []

    if not hospitals:
        st.warning("No active hospitals available.")
    else:
        with st.form("add_doctor_form"):
            doctor_name = st.text_input("Doctor / Service Name")
            hospital_name = st.selectbox("Hospital", hospitals)
            category = st.selectbox("Medical Category", CATEGORIES)

            service_type = st.text_input("Service Type")
            timing = st.text_input("Available Timings")

            next_date = st.date_input(
                "Next Available Date",
                value=date.today()
            )

            availability = st.selectbox("Availability", STATUSES)

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

    if hospitals:
        selected_hospital = st.selectbox(
            "Filter Hospital",
            hospitals,
            key="doctor_filter"
        )

        doctors = get_doctors(hospital=selected_hospital)

        for doctor in doctors:
            with st.expander(f"{doctor['name']} | {doctor['category']}"):
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

                if st.button("Update", key=f"update_doctor_{doctor['id']}"):
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
# DOCTOR AVAILABILITY
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


# =========================================================
# COMPLAINT MANAGEMENT
# =========================================================

elif page in ["All Complaints", "Hospital Complaints"]:
    st.header("📋 Complaint Management")

    connection = get_db()

    if st.session_state.role == "Hospital Admin":
        records = connection.execute("""
            SELECT * FROM complaints
            WHERE hospital=?
            ORDER BY date DESC
        """, (st.session_state.hospital,)).fetchall()
    else:
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

