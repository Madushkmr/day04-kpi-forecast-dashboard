"""
Forecasting methods for daily business KPIs.

Three lightweight, dependency-free (numpy-only) forecasters are provided so
the dashboard can compare them side by side:

- moving_average:   flat forecast at the trailing N-day average. Good
                     baseline for a noisy, non-trending metric.
- linear_regression: ordinary least squares trend line projected forward.
                     Good for a metric with a steady trend.
- holt_linear:       Holt's double exponential smoothing (level + trend).
                     Adapts faster to recent changes than OLS.

Each function returns a list of (date, forecast_value, lower_bound,
upper_bound) tuples. Confidence bounds come from the in-sample residual
standard deviation of the fitted model, widened with the forecast horizon
so uncertainty grows the further out the forecast goes.
"""

from datetime import datetime, timedelta

import numpy as np

Z_95 = 1.96


def _parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d")


def _future_dates(last_date_str, horizon):
    last = _parse_date(last_date_str)
    return [(last + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, horizon + 1)]


def moving_average(history, horizon=14, window=7):
    """history: list of (date, value) sorted ascending."""
    dates, values = zip(*history)
    values = np.array(values, dtype=float)
    window = min(window, len(values))
    trailing = values[-window:]
    level = trailing.mean()
    resid_std = trailing.std(ddof=0) if window > 1 else 0.0

    future = _future_dates(dates[-1], horizon)
    out = []
    for step, d in enumerate(future, start=1):
        spread = Z_95 * resid_std * np.sqrt(step)
        out.append((d, float(level), float(level - spread), float(level + spread)))
    return out


def linear_regression(history, horizon=14, lookback=60):
    dates, values = zip(*history)
    values = np.array(values, dtype=float)
    n = min(lookback, len(values))
    y = values[-n:]
    x = np.arange(n)

    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    resid_std = float(np.std(y - fitted, ddof=max(1, n - 2)) if n > 2 else np.std(y - fitted))

    future = _future_dates(dates[-1], horizon)
    out = []
    for step, d in enumerate(future, start=1):
        x_future = n - 1 + step
        forecast_value = slope * x_future + intercept
        spread = Z_95 * resid_std * np.sqrt(1 + step / n)
        out.append((d, float(forecast_value), float(forecast_value - spread), float(forecast_value + spread)))
    return out


def holt_linear(history, horizon=14, alpha=0.4, beta=0.15):
    """Holt's linear (double exponential smoothing) trend model."""
    dates, values = zip(*history)
    values = np.array(values, dtype=float)

    level = values[0]
    trend = values[1] - values[0] if len(values) > 1 else 0.0
    fitted = [level]

    for t in range(1, len(values)):
        value = values[t]
        last_level = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - last_level) + (1 - beta) * trend
        fitted.append(level)

    fitted = np.array(fitted)
    resid_std = float(np.std(values - fitted))

    future = _future_dates(dates[-1], horizon)
    out = []
    for step, d in enumerate(future, start=1):
        forecast_value = level + step * trend
        spread = Z_95 * resid_std * np.sqrt(step)
        out.append((d, float(forecast_value), float(forecast_value - spread), float(forecast_value + spread)))
    return out


METHODS = {
    "moving_average": moving_average,
    "linear_regression": linear_regression,
    "holt_linear": holt_linear,
}


def forecast(method, history, horizon=14, **kwargs):
    if method not in METHODS:
        raise ValueError(f"Unknown method '{method}'. Options: {list(METHODS)}")
    if len(history) < 3:
        raise ValueError("Need at least 3 historical points to forecast")
    return METHODS[method](history, horizon=horizon, **kwargs)


def backtest_alerts(history, method="holt_linear", train_days=14, test_days=7):
    """
    Walk-forward backtest used to power the Alerts view.

    Trains the given method on all history up to `test_days` ago, forecasts
    forward `test_days`, then compares the forecast's confidence band against
    what actually happened. Any actual value outside its predicted band is
    flagged as a deviation (mirrors how the Day 1 anomaly detector flagged
    outliers, but here the "expected" range comes from a forecast rather
    than a static statistical model).

    Returns a list of alert dicts.
    """
    dates, values = zip(*history)
    if len(history) < train_days + test_days + 1:
        return []

    split = len(history) - test_days
    train = history[:split]
    actual_test = history[split:]

    preds = forecast(method, train, horizon=test_days)

    alerts = []
    for (pred_date, fv, lo, hi), (actual_date, actual_value) in zip(preds, actual_test):
        if actual_date != pred_date:
            continue
        if actual_value < lo or actual_value > hi:
            band_width = max(hi - lo, 1e-9)
            miss = min(abs(actual_value - lo), abs(actual_value - hi))
            severity = "high" if miss > band_width * 0.5 else "medium"
            alerts.append({
                "date": actual_date,
                "actual_value": actual_value,
                "forecast_value": fv,
                "lower_bound": lo,
                "upper_bound": hi,
                "severity": severity,
                "method": method,
            })
    return alerts
