from pathlib import Path
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
DB = ROOT / "05_Starter" / "pulseiq.duckdb"

st.set_page_config(
    page_title="PulseIQ Analytics",
    page_icon="📊",
    layout="wide",
)

st.title("📊 PulseIQ Analytics")
st.caption("Workforce • Finance • Operations • AI insights")

@st.cache_data(ttl=60)
def load_data(query):
    con = duckdb.connect(str(DB), read_only=True)
    try:
        return con.execute(query).df()
    finally:
        con.close()

if not DB.exists():
    st.error(f"Database not found: {DB}")
    st.stop()

try:
    headcount = load_data("""
        SELECT month_start_date, department_id,
               headcount_start, headcount_end, hires, exits,
               voluntary_exits, attrition_rate_monthly_pct
        FROM raw.fact_headcount_monthly
        ORDER BY month_start_date
    """)

    payroll = load_data("""
        SELECT month_start_date, department_id,
               employees_paid, employer_cost
        FROM metrics.m10
        JOIN (
            SELECT date_trunc('month', period_end_date)::DATE
                       AS month_start_date,
                   department_id,
                   COUNT(DISTINCT employee_id) AS employees_paid,
                   SUM(employer_cost) AS employer_cost
            FROM raw.fact_payroll
            GROUP BY 1, 2
            HAVING COUNT(DISTINCT employee_id) >= 5
        ) USING (month_start_date, department_id)
    """)

    attendance = load_data("""
        SELECT period_end_date, department_id,
               SUM(present_days) AS present_days,
               SUM(scheduled_days) AS scheduled_days,
               COUNT(DISTINCT employee_id) AS employees
        FROM raw.fact_attendance_monthly
        GROUP BY 1, 2
        HAVING COUNT(DISTINCT employee_id) >= 5
        ORDER BY period_end_date
    """)

    tasks = load_data("""
        SELECT team_id, sprint_id,
               COUNT(*) FILTER (WHERE status='Done') AS completed_tasks,
               COUNT(*) FILTER (WHERE status <> 'Cancelled') AS active_tasks,
               SUM(story_points) FILTER (WHERE status='Done') AS velocity
        FROM raw.fact_task
        GROUP BY 1, 2
        HAVING COUNT(*) FILTER (WHERE status <> 'Cancelled') >= 5
    """)

    anomalies = load_data("""
        SELECT period, source_dataset,
               COUNT(*) AS total_records,
               COUNT(*) FILTER (WHERE flagged='Y') AS flagged_records
        FROM raw.fact_anomaly
        GROUP BY 1, 2
        ORDER BY period
    """)

    revenue = load_data("""
        SELECT date_trunc('month', entry_date)::DATE AS month,
               -SUM(signed_amount_debit_positive) AS revenue
        FROM raw.fact_ledger
        WHERE account_code BETWEEN 4001 AND 4004
        GROUP BY 1
        ORDER BY 1
    """)

except Exception as exc:
    st.error("A dashboard query failed.")
    st.exception(exc)
    st.info("Check that the metric views were built using src/build_metric_views.py.")
    st.stop()

if headcount.empty:
    st.warning("No headcount data is available.")
    st.stop()

departments = sorted(headcount["department_id"].dropna().unique())
selected = st.sidebar.multiselect(
    "Departments",
    departments,
    default=departments,
)
st.sidebar.caption("Small-group safeguards apply to selected workforce metrics.")

filtered_hc = headcount[headcount["department_id"].isin(selected)]
filtered_payroll = payroll[payroll["department_id"].isin(selected)]
filtered_attendance = attendance[
    attendance["department_id"].isin(selected)
]

latest = filtered_hc.sort_values("month_start_date")
latest_month = latest["month_start_date"].max()
latest_rows = latest[latest["month_start_date"] == latest_month]

if latest_rows.empty:
    st.warning("No records match the selected departments.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest headcount", f"{latest_rows['headcount_end'].sum():,.0f}")
c2.metric("Hires in latest month", f"{latest_rows['hires'].sum():,.0f}")
c3.metric("Exits in latest month", f"{latest_rows['exits'].sum():,.0f}")
c4.metric("Departments selected", f"{len(selected):,}")

st.caption(f"Latest headcount month: {latest_month:%B %Y}")

tab1, tab2, tab3, tab4 = st.tabs([
    "👥 Workforce", "💰 Finance", "🛠️ Operations", "🤖 AI insights"
])

with tab1:
    st.subheader("Workforce trends")
    trend = filtered_hc.groupby("month_start_date", as_index=False).agg(
        headcount=("headcount_end", "sum"),
        hires=("hires", "sum"),
        exits=("exits", "sum"),
    )
    if not trend.empty:
        st.plotly_chart(
            px.line(trend, x="month_start_date", y="headcount",
                    markers=True, title="Month-end headcount"),
            use_container_width=True,
        )
        flows = trend.melt(
            id_vars="month_start_date",
            value_vars=["hires", "exits"],
            var_name="event", value_name="employees",
        )
        st.plotly_chart(
            px.bar(flows, x="month_start_date", y="employees",
                   color="event", barmode="group",
                   title="Monthly hires and exits"),
            use_container_width=True,
        )

    st.subheader("Department headcount")
    if not latest_rows.empty:
        st.plotly_chart(
            px.bar(latest_rows, x="department_id", y="headcount_end",
                   title="Headcount by department"),
            use_container_width=True,
        )

with tab2:
    st.subheader("Finance overview")
    if not revenue.empty:
        st.plotly_chart(
            px.line(revenue, x="month", y="revenue", markers=True,
                    title="Ledger-derived monthly revenue"),
            use_container_width=True,
        )
    if not filtered_payroll.empty:
        payroll_monthly = filtered_payroll.groupby(
            "month_start_date", as_index=False
        ).agg(employer_cost=("employer_cost", "sum"))
        st.plotly_chart(
            px.line(payroll_monthly, x="month_start_date",
                    y="employer_cost", markers=True,
                    title="Monthly employer payroll cost"),
            use_container_width=True,
        )
    st.caption(
        "Revenue uses accounts 4001–4004. Payroll cost is aggregated "
        "only for department-month groups with at least five employees."
    )

with tab3:
    st.subheader("Attendance")
    if not filtered_attendance.empty:
        attendance_monthly = filtered_attendance.groupby(
            "period_end_date", as_index=False
        ).agg(
            present_days=("present_days", "sum"),
            scheduled_days=("scheduled_days", "sum"),
        )
        attendance_monthly["attendance_pct"] = (
            100 * attendance_monthly["present_days"]
            / attendance_monthly["scheduled_days"].replace(0, pd.NA)
        )
        st.plotly_chart(
            px.line(attendance_monthly, x="period_end_date",
                    y="attendance_pct", markers=True,
                    title="Attendance rate (%)"),
            use_container_width=True,
        )

    st.subheader("Team delivery")
    if not tasks.empty:
        st.metric("Team/sprint groups", len(tasks))
        st.plotly_chart(
            px.bar(tasks, x="team_id", y="completed_tasks",
                   color="sprint_id", title="Completed tasks by team and sprint"),
            use_container_width=True,
        )
        st.dataframe(tasks, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Anomaly monitoring")
    if not anomalies.empty:
        anomalies["flag_rate_pct"] = (
            100 * anomalies["flagged_records"]
            / anomalies["total_records"].replace(0, pd.NA)
        )
        st.plotly_chart(
            px.line(anomalies, x="period", y="flag_rate_pct",
                    color="source_dataset", markers=True,
                    title="Anomaly flag rate (%)"),
            use_container_width=True,
        )
        st.metric("Flagged anomaly records", f"{anomalies['flagged_records'].sum():,.0f}")
        st.dataframe(anomalies, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "PulseIQ Analytics • Internal analytics prototype • "
    "Metrics should be validated against the approved business definitions "
    "before operational or management decisions."
)
