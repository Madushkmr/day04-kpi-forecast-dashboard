"""
KPI Forecasting & Alerting Dashboard
=====================================

Flask API + static JS frontend backed by SQLite.

Endpoints:
    GET  /api/metrics
    GET  /api/history/<metric>?limit=90
    GET  /api/forecast/<metric>?method=holt_linear&horizon=14
    GET  /api/alerts?metric=daily_revenue
    POST /api/refresh                 -> regenerate forecasts + alerts for all metrics

Run:
    python app.py
    (serves on http://127.0.0.1:5000, seeding the DB on first run)
"""

import os

from flask import Flask, jsonify, request, send_from_directory

from src import database, forecasting, seed_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "kpi.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")


def ensure_seeded():
    seed_data.seed(DB_PATH)


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/metrics")
def api_metrics():
    with database.connect(DB_PATH) as conn:
        metrics = database.get_metrics(conn)
    return jsonify({"metrics": metrics})


@app.route("/api/history/<metric>")
def api_history(metric):
    limit = request.args.get("limit", default=180, type=int)
    with database.connect(DB_PATH) as conn:
        rows = database.get_history(conn, metric, limit=limit)
    if not rows:
        return jsonify({"error": f"no history for metric '{metric}'"}), 404
    return jsonify({
        "metric": metric,
        "history": [{"date": d, "value": v} for d, v in rows],
    })


@app.route("/api/forecast/<metric>")
def api_forecast(metric):
    method = request.args.get("method", default="holt_linear")
    horizon = request.args.get("horizon", default=14, type=int)

    with database.connect(DB_PATH) as conn:
        history = database.get_history(conn, metric)
        if not history:
            return jsonify({"error": f"no history for metric '{metric}'"}), 404
        try:
            rows = forecasting.forecast(method, history, horizon=horizon)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        database.save_forecast(conn, metric, method, rows)

    return jsonify({
        "metric": metric,
        "method": method,
        "horizon": horizon,
        "forecast": [
            {"date": d, "forecast_value": fv, "lower_bound": lo, "upper_bound": hi}
            for d, fv, lo, hi in rows
        ],
    })


@app.route("/api/alerts")
def api_alerts():
    metric = request.args.get("metric")
    with database.connect(DB_PATH) as conn:
        alerts = database.get_alerts(conn, metric=metric)
    return jsonify({"alerts": alerts})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    method = request.args.get("method", default="holt_linear")
    summary = {}
    with database.connect(DB_PATH) as conn:
        metrics = database.get_metrics(conn)
        database.clear_alerts(conn)
        for metric in metrics:
            history = database.get_history(conn, metric)
            forecast_rows = forecasting.forecast(method, history, horizon=14)
            database.save_forecast(conn, metric, method, forecast_rows)

            new_alerts = forecasting.backtest_alerts(history, method=method)
            for a in new_alerts:
                a["metric"] = metric
            if new_alerts:
                database.save_alerts(conn, new_alerts)

            summary[metric] = {"forecast_points": len(forecast_rows), "alerts": len(new_alerts)}

    return jsonify({"method": method, "summary": summary})


ensure_seeded()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
