"""Run the PulseIQ DQ catalog against the local DuckDB raw data."""

from pathlib import Path
import json
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "05_Starter" / "pulseiq.duckdb"
OUT = ROOT / "logs"
OUT.mkdir(exist_ok=True)

def main():
    con = duckdb.connect(str(DB), read_only=True)
    results = []

    def run(check_id, name, sql, note=""):
        try:
            count = con.execute(
                f"SELECT COUNT(*) FROM ({sql}) AS violations"
            ).fetchone()[0]
            results.append({
                "check_id": check_id,
                "check_name": name,
                "status": "PASS" if count == 0 else "FAIL",
                "violations": int(count),
                "details": note or (
                    "No violations found" if count == 0
                    else f"{count} violating row(s) found"
                ),
            })
        except Exception as exc:
            results.append({
                "check_id": check_id,
                "check_name": name,
                "status": "BLOCKED",
                "violations": None,
                "details": f"Could not evaluate check: {exc}",
            })

    try:
        # DQ-C01: Monthly payroll employer cost vs salary-related ledger.
        run("DQ-C01", "Payroll equals ledger", """
            WITH p AS (
                SELECT date_trunc('month', period_end_date) AS month,
                       SUM(employer_cost) AS cost
                FROM raw.fact_payroll
                GROUP BY 1
            ),
            l AS (
                SELECT date_trunc('month', entry_date) AS month,
                       SUM(signed_amount_debit_positive) AS exp
                FROM raw.fact_ledger
                WHERE account_code BETWEEN 5001 AND 5005
                GROUP BY 1
            )
            SELECT COALESCE(p.month, l.month) AS month
            FROM p FULL OUTER JOIN l USING (month)
            WHERE ABS(COALESCE(p.cost, 0) - COALESCE(l.exp, 0)) > 0.01
        """, "Assumes ledger debit-positive amounts represent salary expense.")

        # DQ-C02: Journal entry debit/credit balance.
        run("DQ-C02", "Ledger balanced", """
            SELECT entry_id
            FROM raw.fact_ledger
            GROUP BY entry_id
            HAVING ABS(SUM(debit) - SUM(credit)) > 0.005
        """)

        # DQ-C03: One payroll row per employee/run.
        run("DQ-C03", "Unique payroll rows", """
            SELECT employee_id, run_id
            FROM raw.fact_payroll
            GROUP BY employee_id, run_id
            HAVING COUNT(*) > 1
        """)

        # DQ-C04: Employee identifiers in employee-related facts.
        run("DQ-C04", "No orphan employees", """
            WITH fact_ids AS (
                SELECT employee_id FROM raw.fact_payroll
                UNION ALL
                SELECT employee_id FROM raw.fact_attendance_monthly
                UNION ALL
                SELECT employee_id FROM raw.fact_leave
                UNION ALL
                SELECT employee_id FROM raw.fact_attrition_risk
                UNION ALL
                SELECT employee_id FROM raw.fact_anomaly
                UNION ALL
                SELECT assignee_employee_id AS employee_id
                FROM raw.fact_task
            )
            SELECT DISTINCT f.employee_id
            FROM fact_ids f
            LEFT JOIN raw.dim_employee d
              ON f.employee_id = d.employee_id
            WHERE f.employee_id IS NOT NULL
              AND d.employee_id IS NULL
        """)

        # DQ-C05: Attendance after an employee's exit month.
        run("DQ-C05", "No attendance after exit", """
            SELECT a.attendance_fact_id
            FROM raw.fact_attendance_monthly a
            JOIN raw.dim_employee d
              ON a.employee_id = d.employee_id
             AND d.is_current = 'Y'
            WHERE d.exit_date IS NOT NULL
              AND a.period_end_date > last_day(d.exit_date)
        """)

        # DQ-C06: Unpaid absences vs payroll loss-of-pay days.
        run("DQ-C06", "Unpaid leave deducted", """
            WITH a AS (
                SELECT employee_id,
                       date_trunc('month', period_end_date) AS month,
                       SUM(unpaid_absence_days) AS unpaid_days
                FROM raw.fact_attendance_monthly
                GROUP BY 1, 2
            ),
            p AS (
                SELECT employee_id,
                       date_trunc('month', period_end_date) AS month,
                       SUM(lop_days) AS lop_days
                FROM raw.fact_payroll
                GROUP BY 1, 2
            )
            SELECT a.employee_id, a.month
            FROM a JOIN p USING (employee_id, month)
            WHERE ABS(a.unpaid_days - p.lop_days) > 0.5
        """, "Only compares employee-months present in both feeds.")

        # DQ-C07: Invoice payment and balance arithmetic.
        run("DQ-C07", "Invoice arithmetic", """
            SELECT invoice_id
            FROM raw.fact_invoice
            WHERE amount_paid > total_amount + 0.01
               OR balance_due < -0.01
        """)

        # DQ-C08: Expense total equals net amount plus GST.
        run("DQ-C08", "Expense arithmetic", """
            SELECT expense_id
            FROM raw.fact_expense
            WHERE ABS(total_amount - (amount_excl_gst + gst_amount)) > 0.01
        """)

        # DQ-C09: Task completion dates.
        run("DQ-C09", "Task dates sensible", """
            SELECT task_id
            FROM raw.fact_task
            WHERE (completed_date IS NOT NULL
                   AND started_date IS NOT NULL
                   AND completed_date < started_date)
               OR (status = 'Done' AND completed_date IS NULL)
        """)

        # DQ-C10: Leave date ordering.
        run("DQ-C10", "Leave dates sensible", """
            SELECT leave_request_id
            FROM raw.fact_leave
            WHERE end_date < start_date
        """)

        # DQ-C11: Prediction recency; scoring timestamp is unavailable
        # in fact_attrition_risk, so the 24-hour scoring check is blocked.
        try:
            stale = con.execute("""
                SELECT COUNT(*)
                FROM raw.fact_attrition_risk
                WHERE as_of_date < (
                    SELECT MAX(as_of_date) - INTERVAL 7 DAY
                    FROM raw.fact_attrition_risk
                )
            """).fetchone()[0]
            results.append({
                "check_id": "DQ-C11",
                "check_name": "AI feeds are fresh",
                "status": "FAIL" if stale else "BLOCKED",
                "violations": int(stale),
                "details": (
                    f"{stale} stale prediction(s); scoring freshness "
                    "cannot be verified because the feed has no scored_at "
                    "or batch timestamp."
                    if stale else
                    "No stale as-of dates detected, but 24-hour scoring "
                    "freshness is unverified."
                ),
            })
        except Exception as exc:
            results.append({
                "check_id": "DQ-C11",
                "check_name": "AI feeds are fresh",
                "status": "BLOCKED",
                "violations": None,
                "details": str(exc),
            })

        # DQ-C12: Employee version date ranges must not overlap.
        run("DQ-C12", "Dimension history does not overlap", """
            SELECT a.employee_key
            FROM raw.dim_employee a
            JOIN raw.dim_employee b
              ON a.employee_id = b.employee_id
             AND a.employee_key < b.employee_key
            WHERE a.valid_from IS NOT NULL
              AND b.valid_from IS NOT NULL
              AND COALESCE(a.valid_to, DATE '9999-12-31') >= b.valid_from
        """)

        # DQ-C13 requires an ETL run log, not currently present in raw.
        has_run_log = con.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = 'etl_run_log'
        """).fetchone()[0]
        results.append({
            "check_id": "DQ-C13",
            "check_name": "Pipeline freshness",
            "status": "BLOCKED",
            "violations": None,
            "details": (
                "A load timestamp table exists but must be integrated."
                if has_run_log else
                "No etl_run_log found; successful load time cannot be verified."
            ),
        })

        # DQ-C14 is enforced at metric-query time, not as a single
        # database-wide query. Do not claim it passed until metric views
        # apply the catalog's minimum_group_size thresholds.
        results.append({
            "check_id": "DQ-C14",
            "check_name": "Minimum group size",
            "status": "BLOCKED",
            "violations": None,
            "details": (
                "Requires query-time enforcement in all governed metric "
                "views using raw.metric_dictionary.minimum_group_size."
            ),
        })

    finally:
        con.close()

    df = pd.DataFrame(results).sort_values("check_id")
    df.to_csv(OUT / "dq_results.csv", index=False)

    summary = {
        "total_checks": len(df),
        "passed": int((df.status == "PASS").sum()),
        "failed": int((df.status == "FAIL").sum()),
        "blocked": int((df.status == "BLOCKED").sum()),
        "results": results,
    }
    (OUT / "dq_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    print(df.to_string(index=False))
    print("\nSummary:", {
        key: summary[key]
        for key in ["total_checks", "passed", "failed", "blocked"]
    })
    print(f"Report: {OUT / 'dq_results.csv'}")
    print(f"Summary: {OUT / 'dq_summary.json'}")

if __name__ == "__main__":
    main()
