import pandas as pd


def test_anomaly_score_must_be_between_zero_and_one():
    scores = pd.Series([0.0, 0.5, 1.0, -0.1, 1.1])

    valid = scores.between(0, 1, inclusive="both")

    assert valid.tolist() == [True, True, True, False, False]


def test_forecast_bounds_must_contain_forecast_value():
    forecast = pd.Series([100.0, 50.0, 75.0])
    lower = pd.Series([80.0, 60.0, 70.0])
    upper = pd.Series([120.0, 90.0, 75.0])

    valid = (lower <= forecast) & (upper >= forecast)

    assert valid.tolist() == [True, False, True]


def test_task_completion_date_cannot_precede_start_date():
    started = pd.to_datetime(
        ["2026-01-10", "2026-01-10", "2026-01-10"]
    )
    completed = pd.to_datetime(
        ["2026-01-11", "2026-01-09", None]
    )

    valid = completed.isna() | (completed >= started)

    assert valid.tolist() == [True, False, True]


def test_task_started_date_can_be_blank_only_for_to_do():
    started = pd.to_datetime(
        [None, None, "2026-01-10"]
    )
    status = pd.Series(["To Do", "In Progress", "Done"])

    valid = started.notna() | status.eq("To Do")

    assert valid.tolist() == [True, False, True]


def test_contract_id_formats():
    anomaly_ids = pd.Series(["AN-0001", "AN-1234", "BAD-1234"])
    valid = anomaly_ids.str.fullmatch(r"AN-\d{4}", na=False)

    assert valid.tolist() == [True, True, False]


def test_month_start_or_month_end_period():
    periods = pd.to_datetime(
        ["2026-01-01", "2026-02-28", "2026-02-15"]
    )

    valid = periods.is_month_start | periods.is_month_end

    assert valid.tolist() == [True, True, False]
