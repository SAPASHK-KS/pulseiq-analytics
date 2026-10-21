from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "05_Starter" / "pulseiq.duckdb"
DIMENSIONS_SQL = ROOT / "docs" / "create_dimensions.sql"
FACTS_SQL = ROOT / "docs" / "create_facts.sql"

DIMENSIONS = [
    "dim_department", "dim_role", "dim_location", "dim_leave_type",
    "dim_account", "dim_client", "dim_vendor", "dim_team",
    "dim_sprint", "dim_employee", "dim_date",
]

FACTS = [
    "fact_payroll", "fact_attendance_monthly", "fact_leave",
    "fact_headcount_monthly", "fact_ledger", "fact_invoice",
    "fact_invoice_payment", "fact_expense", "fact_task",
    "fact_anomaly", "fact_attrition_risk", "fact_forecast",
]

def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DuckDB database not found: {DB_PATH}")

    for sql_file in [DIMENSIONS_SQL, FACTS_SQL]:
        if not sql_file.exists():
            raise FileNotFoundError(f"SQL file not found: {sql_file}")

    con = duckdb.connect(str(DB_PATH))
    try:
        raw_tables = {
            row[0]
            for row in con.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'raw'
            """).fetchall()
        }

        expected = set(DIMENSIONS + FACTS)
        missing = sorted(expected - raw_tables)
        if missing:
            raise RuntimeError(f"Missing raw source tables: {missing}")

        print("All 23 required raw source tables are present.")
        print("Creating warehouse tables...")

        con.execute(DIMENSIONS_SQL.read_text())
        con.execute(FACTS_SQL.read_text())

        for table in DIMENSIONS + FACTS:
            target = f"warehouse.{table}"
            source = f"raw.{table}"
            con.execute(f"INSERT INTO {target} BY NAME SELECT * FROM {source}")
            source_count = con.execute(
                f"SELECT COUNT(*) FROM {source}"
            ).fetchone()[0]
            target_count = con.execute(
                f"SELECT COUNT(*) FROM {target}"
            ).fetchone()[0]

            if source_count != target_count:
                raise RuntimeError(
                    f"{table}: raw={source_count}, warehouse={target_count}"
                )

            print(f"PASS {table}: {target_count:,} rows")

        print("\nWarehouse tables created and row counts verified.")
    finally:
        con.close()

if __name__ == "__main__":
    main()
