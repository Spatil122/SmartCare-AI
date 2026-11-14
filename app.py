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
