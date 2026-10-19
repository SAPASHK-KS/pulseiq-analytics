# PulseIQ — ETL Data Validation Pipeline

## 1. Project Overview

PulseIQ is a data engineering project that loads workforce analytics data, validates records against data contracts, and separates valid records from rejected records.

**Technology stack:** Python 3.12, Pandas, DuckDB, pytest, and Docker.

## 2. Project Structure

- `03_Data/` — Source dataset and CSV files.
- `05_Starter/` — DuckDB database, data loader, and dependencies.
- `src/etl.py` — ETL validation pipeline.
- `tests/test_etl.py` — Automated validation-rule tests.
- `data/clean/` — Validated records.
- `data/rejected/` — Quarantined records and validation reasons.
- `logs/` — ETL execution summaries.
- `Dockerfile` — Container configuration.

## 3. Environment Setup

Activate the Python virtual environment and install dependencies:

```bash
source .venv/bin/activate
python -m pip install -r 05_Starter/requirements.txt
python -m pip install pytest
```

## 4. Load Raw Data

Run the starter loader from the project root:

```bash
cd 05_Starter
python load_to_duckdb.py
cd ..
```

## 5. Run the ETL Pipeline

```bash
python src/etl.py
```

The pipeline validates four contract-covered tables: `fact_anomaly`, `fact_attrition_risk`, `fact_forecast`, and `fact_task`.

Clean records are written to `data/clean/`. Rejected records, including validation reasons, are written to `data/rejected/`.

Execution summaries are written to `logs/etl_summary.csv` and `logs/etl_summary.json`.

The pipeline checks that input rows equal passed rows plus quarantined rows.

## 6. Docker Execution

Build the image:

```bash
docker build -t pulseiq-etl .
```

Run the pipeline:

```bash
docker run --rm \
  -v "$PWD/05_Starter:/app/05_Starter:ro" \
  -v "$PWD/data/clean:/app/data/clean" \
  -v "$PWD/data/rejected:/app/data/rejected" \
  -v "$PWD/logs:/app/logs" \
  pulseiq-etl
```

## 7. Automated Tests

```bash
python -m pytest -v
```

The current test suite contains six rule-level tests covering anomaly scores, forecast bounds, task dates, task start-date rules, ID formats, and monthly periods.

These tests do not replace a full end-to-end integration test.

## 8. Latest Recorded Results

| Table | Input | Passed | Quarantined |
|---|---:|---:|---:|
| `fact_anomaly` | 405 | 405 | 0 |
| `fact_attrition_risk` | 430 | 425 | 5 |
| `fact_forecast` | 72 | 72 | 0 |
| `fact_task` | 28,868 | 28,848 | 20 |
| **Total** | **29,775** | **29,750** | **25** |

These are the results of the latest recorded run and should be updated if the source data or validation rules change.

## 9. Data Quality Decisions and Limitations

- Five attrition predictions dated `2026-03-31` are quarantined because the pipeline treats the latest available date, `2026-09-30`, as the batch date. The source does not provide a separate batch identifier, so this is an assumption requiring confirmation.
- Twenty task records are quarantined: twelve have completion dates earlier than their start dates, and eight have status `Done` without a completion date.
- The anomaly feature source datasets are not available in the loaded raw schema. Source-record existence for anomaly records therefore remains unverified.
- Unexpected columns are reported and preserved in outputs rather than automatically rejected. Missing required contract columns stop validation.
- Only the four tables with supplied contracts are validated by this ETL pipeline.

## 10. Submission Checklist

Before submission, verify the source files, clean outputs, quarantine outputs, summary logs, automated tests, Docker execution, and required GitHub evidence.
