# KPI Forecasting & Alerting Dashboard

Day 4 of a daily AI-app build series, focused on Business Intelligence use cases.

A Flask API + browser dashboard that forecasts daily business KPIs (revenue, signups, churn rate), stores forecasts and history in SQLite, and backtests each metric to flag days where the actual value fell outside what the model expected — i.e. an alert.

## Why this is useful for BI work

"What do we expect this number to be next week, and should we be worried about what it did last week?" is a question BI teams answer constantly, for revenue, signups, churn, and dozens of other operational metrics. This app automates both halves of that question:

- **Forecasting** — three interchangeable models (moving average, OLS linear regression, Holt's linear trend/exponential smoothing) project each metric forward with a 95% confidence band, so a viewer can compare a stable baseline against trend-aware alternatives.
- **Alerting** — a walk-forward backtest trains each model on data up to N days ago, forecasts forward, and checks whether what actually happened fell inside the predicted range. Points outside the range are flagged and persisted as alerts, tagged high/medium severity by how far outside the band they landed.

This is the same "is this normal?" question Day 1's anomaly detector answered with `IsolationForest`, but approached differently: here "normal" is defined relative to a trained forecast rather than a static statistical model, and every forecast/alert is persisted so history survives a restart — closer to how this would run as a scheduled job feeding a real dashboard.

## Complexity tier: multi-component app with persistent storage

Step up from Day 3 (a config-driven CLI pipeline): this is a Flask **API + browser frontend** (Chart.js dashboard) backed by a **SQLite database** that persists history, every generated forecast, and every triggered alert across restarts, instead of writing one-off report files.

## Architecture

```
day04-kpi-forecast-dashboard/
  app.py                   Flask app: serves the dashboard + JSON API, seeds DB on boot
  src/
    database.py             SQLite schema + CRUD (kpi_history, forecasts, alerts tables)
    forecasting.py           moving_average / linear_regression / holt_linear models
                             + backtest_alerts() walk-forward anomaly check
    seed_data.py             Generates 180 days of synthetic revenue/signups/churn
                             data per metric, with an injected anomaly in the last week
  static/
    index.html               Dashboard shell
    app.js                   Fetches API data, renders Chart.js line chart + alerts table
    style.css                Dark dashboard theme
  data/
    kpi.db                   SQLite database (created on first run, not committed)
  tests/
    test_forecasting.py       Unit tests for all 3 models + backtest_alerts()
    test_database.py          Unit tests for the persistence layer
  requirements.txt
```

### Data flow

1. On first boot, `app.py` calls `seed_data.seed()`, which generates synthetic daily history for `daily_revenue`, `daily_signups`, and `churn_rate` (180 days each, with a deliberate revenue dip in the final week) and writes it to `data/kpi.db` via `database.upsert_history`.
2. The dashboard calls `GET /api/history/<metric>` to draw the actuals line, and `GET /api/forecast/<metric>?method=...&horizon=...` to compute (and persist) a forecast with confidence bounds using the selected model.
3. Clicking **Refresh forecasts & alerts** calls `POST /api/refresh`, which regenerates the forecast for every metric and re-runs `forecasting.backtest_alerts()` — training on all data up to 7 days ago, forecasting those 7 days, and comparing against what actually happened. Any breach is saved to the `alerts` table and shown in the table below the chart.

## How to run

```bash
cd day04-kpi-forecast-dashboard
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in a browser. The database is created and seeded automatically on first run (`data/kpi.db`). Pick a metric and forecast method, then click **Refresh forecasts & alerts** to populate the alerts table (the sample data has an injected anomaly in `daily_revenue`'s last week, so that metric should show at least one alert immediately).

## Tests

```bash
python -m pytest tests/ -v
```

Covers all three forecasting models (shape, trend extrapolation, confidence bounds), the backtest alerting logic (both an injected-anomaly case and a stable-series case), and the SQLite persistence layer (upsert/idempotency, forecast storage, alert storage/clearing).

## Next in this series

Day 1 was a single-script anomaly detector. Day 2 added a Flask web UI with a modular parser/DB split. Day 3 stepped up to a config-driven, multi-stage CLI pipeline with a broader test suite. Day 4 adds the two things Day 3's own notes flagged as next: **persistent storage** (SQLite, surviving restarts) and a **browser dashboard** (Chart.js) — plus backtested alerting as a second connected feature on top of forecasting. Future days will keep escalating: more integrated features, more robust error handling/deployment config, and eventually agentic multi-step BI workflows.
