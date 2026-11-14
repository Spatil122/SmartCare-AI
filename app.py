
def show_dashboard(title, hospital_scope=None, allow_hospital_filter=False):
    """Hospital-wise complaint dashboard with existing update functionality."""

    st.header("📊 " + title)

    connection = get_connection()

    # Hospital selection
    if hospital_scope:
        hospital_filter = hospital_scope
        st.info("Showing data only for: " + hospital_scope)

    elif allow_hospital_filter:
        available = ["All Hospitals"] + fetch_hospitals()
        hospital_filter = st.selectbox(
            "Filter by Hospital",
            available,
            key="dashboard_hospital_filter"
        )
    else:
        hospital_filter = "All Hospitals"

    category_filter = st.selectbox(
        "Filter by Category",
        ["All Categories"] + CATEGORIES,
        key=f"category_{title.replace(' ', '_')}"
    )

    # Fetch complaints
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

    # Overall metrics
    total = len(records)
    pending = sum(r["status"] == "Pending" for r in records)
    in_progress = sum(r["status"] == "In Progress" for r in records)
    resolved = sum(r["status"] == "Resolved" for r in records)

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Complaints", total)
    c2.metric("Pending", pending)
    c3.metric("In Progress", in_progress)
    c4.metric("Resolved", resolved)

    st.divider()

    # Complaint analysis
    st.subheader("📈 Complaint Analysis")

    if records:
        chart_data = [dict(r) for r in records]

        left, middle, right = st.columns(3)

        with left:
            fig = px.pie(
                chart_data,
                names="category",
                hole=0.55,
                title="Complaints by Category"
            )
            st.plotly_chart(fig, use_container_width=True)

        with middle:
            fig = px.pie(
                chart_data,
                names="status",
                hole=0.55,
                title="Complaints by Status"
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            fig = px.pie(
                chart_data,
                names="hospital",
                hole=0.55,
                title="Complaints by Hospital"
            )
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No complaints found.")

    st.divider()

    # =====================================================
    # NEW FEATURE: HOSPITAL-WISE COMPLAINT ORGANIZATION
    # =====================================================

    st.subheader("🏥 Hospital-wise Complaint Records")

    hospital_groups = {}

    for record in records:
        hospital_name = record["hospital"] or "Unknown Hospital"

        if hospital_name not in hospital_groups:
            hospital_groups[hospital_name] = []

        hospital_groups[hospital_name].append(record)

    if not hospital_groups:
        st.info("No hospital complaints available.")

    # Display each hospital separately
    for hospital_name, hospital_records in sorted(hospital_groups.items()):

        hospital_total = len(hospital_records)

        hospital_pending = sum(
            r["status"] == "Pending" for r in hospital_records
        )

        hospital_progress = sum(
            r["status"] == "In Progress" for r in hospital_records
        )

        hospital_resolved = sum(
            r["status"] == "Resolved" for r in hospital_records
        )

        with st.expander(
            f"🏥 {hospital_name} | "
            f"Total: {hospital_total} | "
            f"Pending: {hospital_pending} | "
            f"Resolved: {hospital_resolved}",
            expanded=True
        ):

            m1, m2, m3, m4 = st.columns(4)

            m1.metric("Total", hospital_total)
            m2.metric("Pending", hospital_pending)
            m3.metric("In Progress", hospital_progress)
            m4.metric("Resolved", hospital_resolved)

            st.divider()

            # Individual hospital complaints
            for record in hospital_records:

                with st.container(border=True):

                    st.markdown(
                        f"**Complaint ID:** {record['id']}"
                    )

                    st.write("Patient:", record["name"])
                    st.write("Phone:", record["phone"])
                    st.write("Category:", record["category"])
                    st.write("AI Suggestion:", record["ai_category"] or "Not available")
                    st.write("Complaint:", record["complaint"])
                    st.write("Status:", record["status"])
                    st.write("Date:", record["date"])

                    # Existing interaction history
                    st.markdown("**Interaction History**")

                    history = connection.execute("""
                        SELECT author, author_role, message, created_at
                        FROM complaint_interactions
                        WHERE complaint_id=?
                        ORDER BY interaction_id
                    """, (record["id"],)).fetchall()

                    if history:
                        for item in history:
                            st.write(
                                f"{item['created_at']} - "
                                f"{item['author']} "
                                f"({item['author_role']}): "
                                f"{item['message']}"
                            )
                    else:
                        st.caption("No interaction history.")

    # =====================================================
    # EXISTING STATUS UPDATE AND PATIENT REPLY FUNCTION
    # =====================================================

    st.divider()
    st.subheader("✏️ Update Complaint and Reply to Patient")

    if not records:
        connection.close()
        return

    selected_id = st.selectbox(
        "Select Complaint ID",
        [r["id"] for r in records],
        key=f"selected_complaint_{title.replace(' ', '_')}"
    )

    selected_record = next(
        r for r in records if r["id"] == selected_id
    )

    new_status = st.selectbox(
        "Complaint Status",
        STATUSES,
        index=(
            STATUSES.index(selected_record["status"])
            if selected_record["status"] in STATUSES else 0
        ),
        key=f"status_{title.replace(' ', '_')}"
    )

    reply = st.text_area(
        "Write a reply or progress update for the patient",
        key=f"reply_{title.replace(' ', '_')}"
    )

    if st.button(
        "Save Status and Reply",
        type="primary",
        key=f"save_{title.replace(' ', '_')}"
    ):

        connection.execute(
            "UPDATE complaints SET status=? WHERE id=?",
            (new_status, selected_id)
        )

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
