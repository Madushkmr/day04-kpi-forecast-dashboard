import math
from datetime import datetime, timedelta

import pytest

from src import forecasting


def make_series(days=60, start_value=100.0, slope=1.0, noise=0.0, seed=0):
    import random
    rng = random.Random(seed)
    start = datetime(2025, 1, 1)
    out = []
    for i in range(days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        v = start_value + slope * i + rng.gauss(0, noise)
        out.append((d, v))
    return out


def test_moving_average_shape_and_flatness():
    history = make_series(days=30, slope=0.0, noise=0.0)
    result = forecasting.moving_average(history, horizon=5, window=7)
    assert len(result) == 5
    values = [r[1] for r in result]
    # flat series -> forecast should be (near) constant
    assert max(values) - min(values) < 1e-6
    for date, fv, lo, hi in result:
        assert lo <= fv <= hi


def test_linear_regression_extends_trend():
    history = make_series(days=30, start_value=0.0, slope=2.0, noise=0.0)
    result = forecasting.linear_regression(history, horizon=5)
    # last historical value is 2*29=58, next should be ~60
    first_forecast_value = result[0][1]
    assert math.isclose(first_forecast_value, 60.0, abs_tol=0.5)
    # values should keep increasing by ~2/day
    diffs = [result[i + 1][1] - result[i][1] for i in range(len(result) - 1)]
    for d in diffs:
        assert math.isclose(d, 2.0, abs_tol=0.5)


def test_holt_linear_shape():
    history = make_series(days=40, start_value=50.0, slope=1.5, noise=1.0, seed=1)
    result = forecasting.holt_linear(history, horizon=10)
    assert len(result) == 10
    dates = [r[0] for r in result]
    assert dates == sorted(dates)
    for date, fv, lo, hi in result:
        assert lo <= fv <= hi


def test_forecast_dispatch_unknown_method():
    history = make_series(days=10)
    with pytest.raises(ValueError):
        forecasting.forecast("not_a_method", history)


def test_forecast_requires_min_history():
    with pytest.raises(ValueError):
        forecasting.forecast("holt_linear", [("2025-01-01", 1.0), ("2025-01-02", 2.0)])


def test_backtest_alerts_flags_injected_anomaly():
    # Build a stable series then inject a sharp drop in the last 3 days.
    history = make_series(days=40, start_value=1000.0, slope=5.0, noise=5.0, seed=2)
    history = list(history)
    for i in range(len(history) - 3, len(history)):
        date, value = history[i]
        history[i] = (date, value * 0.3)  # sharp anomalous drop

    alerts = forecasting.backtest_alerts(history, method="holt_linear", train_days=14, test_days=7)
    assert len(alerts) >= 1
    assert all(a["severity"] in ("high", "medium") for a in alerts)


def test_backtest_alerts_quiet_on_stable_series():
    history = make_series(days=40, start_value=500.0, slope=1.0, noise=0.5, seed=3)
    alerts = forecasting.backtest_alerts(history, method="linear_regression", train_days=14, test_days=7)
    # A stable, low-noise, on-trend series should trigger few or no alerts
    assert len(alerts) <= 1
