# Payroll Employee-Key Exceptions

Validation date: 2026-10-21

Two payroll rows have employee_key = -1, which does not match
a row in warehouse.dim_employee.

| Payroll item | Employee ID | Period end | Employee key |
|---|---|---|---:|
| PI-X0003 | EMP-9001 | 2026-04-30 | -1 |
| PI-X0004 | EMP-9002 | 2025-12-31 | -1 |

Treatment:
- Preserve both payroll rows.
- Do not invent employee dimension mappings.
- Investigate the unknown-key assignment in the source/ETL mapping.
- Keep these rows documented as exceptions until resolved.

Current employee-key orphan counts:
- fact_payroll: 2
- fact_attendance_monthly: 0
- fact_attrition_risk: 0
