"""Build and verify the 28 PulseIQ metric views in DuckDB."""

from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "05_Starter" / "pulseiq.duckdb"

VIEWS = {
"M01": """
SELECT month_start_date, department_id, headcount_end AS headcount
FROM raw.fact_headcount_monthly
WHERE headcount_end >= 5
""",
"M02": """
SELECT date_trunc('month', hire_date)::DATE AS month_start_date,
       department_id, COUNT(DISTINCT employee_id) AS hires
FROM raw.dim_employee
WHERE hire_date IS NOT NULL AND is_current = 'Y'
GROUP BY 1,2 HAVING COUNT(DISTINCT employee_id) >= 5
""",
"M03": """
SELECT date_trunc('month', exit_date)::DATE AS month_start_date,
       department_id, COUNT(DISTINCT employee_id) AS exits
FROM raw.dim_employee
WHERE exit_date IS NOT NULL AND is_current = 'Y'
GROUP BY 1,2 HAVING COUNT(DISTINCT employee_id) >= 5
""",
"M04": """
SELECT month_start_date, department_id,
       100.0 * exits / NULLIF(headcount_start,0) AS attrition_rate_pct
FROM raw.fact_headcount_monthly
WHERE headcount_start >= 10
""",
"M05": """
SELECT month_start_date, department_id,
       100.0 * SUM(exits) OVER (
           PARTITION BY department_id ORDER BY month_start_date
           ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
       ) / NULLIF(AVG(headcount_end) OVER (
           PARTITION BY department_id ORDER BY month_start_date
           ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
       ),0) AS rolling_12m_attrition_pct
FROM raw.fact_headcount_monthly
QUALIFY COUNT(*) OVER (
    PARTITION BY department_id ORDER BY month_start_date
    ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
) = 12
AND AVG(headcount_end) OVER (
    PARTITION BY department_id ORDER BY month_start_date
    ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
) >= 10
""",
"M06": """
SELECT month_start_date, department_id,
       100.0 * SUM(voluntary_exits) OVER (
           PARTITION BY department_id ORDER BY month_start_date
           ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
       ) / NULLIF(AVG(headcount_end) OVER (
           PARTITION BY department_id ORDER BY month_start_date
           ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
       ),0) AS rolling_12m_voluntary_attrition_pct
FROM raw.fact_headcount_monthly
QUALIFY COUNT(*) OVER (
    PARTITION BY department_id ORDER BY month_start_date
    ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
) = 12
AND AVG(headcount_end) OVER (
    PARTITION BY department_id ORDER BY month_start_date
    ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
) >= 10
""",
"M07": """
SELECT date_trunc('month',period_end_date)::DATE AS month_start_date,
       employee_id, SUM(gross_pay) AS gross_pay
FROM raw.fact_payroll
GROUP BY 1,2
""",
"M08": """
SELECT date_trunc('month',period_end_date)::DATE AS month_start_date,
       employee_id, SUM(net_pay) AS net_pay
FROM raw.fact_payroll
GROUP BY 1,2
""",
"M09": """
SELECT date_trunc('month',period_end_date)::DATE AS month_start_date,
       employee_id, SUM(employer_cost) AS employer_cost
FROM raw.fact_payroll
GROUP BY 1,2
""",
"M10": """
SELECT date_trunc('month',period_end_date)::DATE AS month_start_date,
       department_id, SUM(employer_cost)/NULLIF(COUNT(DISTINCT employee_id),0)
       AS cost_per_head
FROM raw.fact_payroll
GROUP BY 1,2 HAVING COUNT(DISTINCT employee_id) >= 5
""",
"M11": """
SELECT date_trunc('month',period_end_date)::DATE AS month_start_date,
       department_id, 100.0*SUM(overtime_pay)/NULLIF(SUM(employer_cost),0)
       AS overtime_share_pct
FROM raw.fact_payroll
GROUP BY 1,2 HAVING COUNT(DISTINCT employee_id) >= 5
""",
"M12": """
SELECT date_trunc('month',period_end_date)::DATE AS month_start_date,
       department_id, 100.0*SUM(variable_pay)/NULLIF(SUM(gross_pay),0)
       AS variable_pay_share_pct
FROM raw.fact_payroll
GROUP BY 1,2 HAVING COUNT(DISTINCT employee_id) >= 5
""",
"M13": """
SELECT period_end_date, department_id,
       (SUM(present_days)+0.5*SUM(half_days_unpaid))
       / NULLIF(SUM(scheduled_days),0) AS attendance_rate
FROM raw.fact_attendance_monthly
GROUP BY 1,2 HAVING COUNT(DISTINCT employee_id) >= 5
""",
"M14": """
SELECT period_end_date, department_id,
       SUM(late_arrivals)/NULLIF(SUM(present_days),0) AS late_arrival_rate
FROM raw.fact_attendance_monthly
GROUP BY 1,2 HAVING COUNT(DISTINCT employee_id) >= 5
""",
"M15": """
SELECT date_trunc('month',period_end_date)::DATE AS month_start_date,
       employee_id, SUM(lop_days) AS leave_without_pay_days
FROM raw.fact_payroll
GROUP BY 1,2
""",
"M16": """
SELECT date_trunc('month',entry_date)::DATE AS month_start_date,
       account_code, -SUM(signed_amount_debit_positive) AS revenue
FROM raw.fact_ledger
WHERE account_code BETWEEN 4001 AND 4004
GROUP BY 1,2
""",
"M17": """
SELECT date_trunc('month',entry_date)::DATE AS month_start_date,
       -SUM(signed_amount_debit_positive) AS net_profit
FROM raw.fact_ledger
WHERE (account_code BETWEEN 4000 AND 4999)
   OR (account_code BETWEEN 5000 AND 5999)
GROUP BY 1
""",
"M18": """
WITH x AS (
 SELECT date_trunc('month',entry_date)::DATE AS month_start_date,
        SUM(CASE WHEN account_code BETWEEN 4001 AND 4004
                 THEN -signed_amount_debit_positive ELSE 0 END) AS revenue,
        -SUM(CASE WHEN account_code BETWEEN 4000 AND 4999
                       OR account_code BETWEEN 5000 AND 5999
                  THEN signed_amount_debit_positive ELSE 0 END) AS profit
 FROM raw.fact_ledger GROUP BY 1
)
SELECT month_start_date, profit/NULLIF(revenue,0)*100 AS operating_margin_pct
FROM x
""",
"M19": """
WITH p AS (
 SELECT date_trunc('month',period_end_date)::DATE AS month_start_date,
        SUM(employer_cost) AS payroll_cost
 FROM raw.fact_payroll GROUP BY 1
), r AS (
 SELECT date_trunc('month',entry_date)::DATE AS month_start_date,
        -SUM(signed_amount_debit_positive) AS revenue
 FROM raw.fact_ledger WHERE account_code BETWEEN 4001 AND 4004
 GROUP BY 1
)
SELECT p.month_start_date, p.payroll_cost,
       r.revenue, 100.0*p.payroll_cost/NULLIF(r.revenue,0) AS payroll_pct_revenue
FROM p JOIN r USING(month_start_date)
""",
"M20": """
WITH receivables AS (
 SELECT date_trunc('month',invoice_date)::DATE AS month_start_date,
        SUM(balance_due) AS closing_receivables
 FROM raw.fact_invoice
 WHERE status NOT IN ('DRAFT','CANCELLED')
 GROUP BY 1
), revenue AS (
 SELECT date_trunc('month',entry_date)::DATE AS month_start_date,
        -SUM(signed_amount_debit_positive) AS revenue
 FROM raw.fact_ledger WHERE account_code BETWEEN 4001 AND 4004
 GROUP BY 1
)
SELECT r.month_start_date, r.closing_receivables,
       v.revenue,
       90.0*r.closing_receivables/NULLIF(v.revenue,0) AS dso_days
FROM receivables r JOIN revenue v USING(month_start_date)
""",
"M21": """
SELECT CAST(current_date AS DATE) AS report_date, client_id,
       SUM(balance_due) AS overdue_receivables
FROM raw.fact_invoice
WHERE due_date < current_date
  AND status NOT IN ('DRAFT','CANCELLED')
GROUP BY client_id
""",
"M22": """
SELECT team_id, sprint_id,
       COUNT(*) FILTER(WHERE status='Done')*1.0
       / NULLIF(COUNT(*) FILTER(WHERE status<>'Cancelled'),0)
       AS task_completion_rate
FROM raw.fact_task
GROUP BY 1,2
HAVING COUNT(*) FILTER(WHERE status<>'Cancelled') >= 5
""",
"M23": """
SELECT team_id, sprint_id,
       COUNT(*) FILTER(WHERE completed_on_time='Y')*1.0
       / NULLIF(COUNT(*) FILTER(WHERE status='Done'),0) AS on_time_rate
FROM raw.fact_task
GROUP BY 1,2
HAVING COUNT(*) FILTER(WHERE status='Done') >= 5
""",
"M24": """
SELECT team_id, sprint_id,
       SUM(story_points) FILTER(WHERE status='Done') AS velocity
FROM raw.fact_task
GROUP BY 1,2
""",
"M25": """
SELECT team_id, sprint_id,
       AVG(date_diff('day',started_date,completed_date)) AS average_cycle_time_days
FROM raw.fact_task
WHERE status='Done' AND started_date IS NOT NULL
  AND completed_date IS NOT NULL
GROUP BY 1,2 HAVING COUNT(*) >= 5
""",
"M26": """
SELECT date_trunc('month',period)::DATE AS month_start_date,
       source_dataset,
       AVG(CASE WHEN flagged='Y' THEN 1.0 ELSE 0.0 END) AS anomaly_flag_rate
FROM raw.fact_anomaly
GROUP BY 1,2
""",
"M27": """
SELECT department_id,
       COUNT(*) FILTER(WHERE risk_band='High')*1.0/NULLIF(COUNT(*),0)
       AS high_risk_share
FROM raw.fact_attrition_risk
GROUP BY department_id HAVING COUNT(DISTINCT employee_id) >= 10
""",
"M28": """
WITH actual AS (
 SELECT month_start_date, department_id, headcount_end AS actual_value
 FROM raw.fact_headcount_monthly
), forecasts AS (
 SELECT forecast_month::DATE AS month_start_date, department_id, forecast_value
 FROM raw.fact_forecast WHERE metric='headcount_end'
)
SELECT f.month_start_date, f.department_id, f.forecast_value, a.actual_value,
       AVG(ABS(a.actual_value-f.forecast_value)
           / NULLIF(ABS(a.actual_value),0))*100 AS forecast_mape_pct
FROM forecasts f JOIN actual a
  ON f.month_start_date=a.month_start_date
 AND (f.department_id=a.department_id OR f.department_id='ALL')
GROUP BY 1,2,3,4
""",
}

def main():
    con = duckdb.connect(str(DB))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS metrics")
        for metric_id, query in VIEWS.items():
            view_name = f"metrics.{metric_id.lower()}"
            con.execute(f"CREATE OR REPLACE VIEW {view_name} AS {query}")
            con.execute(f"SELECT * FROM {view_name} LIMIT 1").fetchall()
            print(f"PASS {metric_id}: {view_name}")

        view_count = con.execute("""
            SELECT COUNT(*)
            FROM information_schema.views
            WHERE table_schema='metrics'
        """).fetchone()[0]

        if view_count != 28:
            raise RuntimeError(f"Expected 28 views, found {view_count}")

        print(f"\nSUCCESS: {view_count} metric views created and queried.")
        print("Note: M07-M09 are employee-level payroll views; do not expose")
        print("them to managers until the minimum-group policy is resolved.")
        print("M20 and M21 use simplified as-of logic; review before sign-off.")
    finally:
        con.close()

if __name__ == "__main__":
    main()
