"""
Generates synthetic daily KPI history for a fictional SaaS business and
loads it into the SQLite database via src.database.

Three metrics, 180 days each:
- daily_revenue:  upward trend + weekly seasonality (weekday/weekend dip) + noise
- daily_signups:  slower upward trend + weekly seasonality + noise
- churn_rate:     roughly flat/slightly declining, bounded 0-100%, noisier

A deliberate anomaly (a sharp revenue drop) is injected into the last week
so the Alerts view has something real to detect on first run.
"""

import os
import random
from datetime import datetime, timedelta

from . import database

random.seed(42)

DAYS = 180


def _dates(end=None, days=DAYS):
    end = end or datetime.utcnow().date()
    start = end - timedelta(days=days - 1)
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]


def _weekly_factor(i, weekend_dip=0.18):
    # i=0 is arbitrary weekday offset; treat i % 7 in {5,6} as weekend
    return 1 - weekend_dip if (i % 7) in (5, 6) else 1.0


def gen_daily_revenue(days=DAYS):
    base = 8000.0
    growth_per_day = 22.0
    values = []
    for i in range(days):
        trend = base + growth_per_day * i
        seasonal = trend * (_weekly_factor(i) - 1)
        noise = random.gauss(0, trend * 0.04)
        values.append(max(0.0, trend + seasonal + noise))

    # Inject an anomalous dip in the last 6 days (e.g. a payment processor
    # outage) so the backtest alerting has a real event to catch.
    for offset in range(1, 6):
        values[-offset] *= 0.62

    return values


def gen_daily_signups(days=DAYS):
    base = 120.0
    growth_per_day = 0.35
    values = []
    for i in range(days):
        trend = base + growth_per_day * i
        seasonal = trend * (_weekly_factor(i, weekend_dip=0.30) - 1)
        noise = random.gauss(0, trend * 0.12)
        values.append(max(0.0, round(trend + seasonal + noise)))
    return values


def gen_churn_rate(days=DAYS):
    base = 4.5  # percent
    decline_per_day = -0.004
    values = []
    for i in range(days):
        trend = base + decline_per_day * i
        noise = random.gauss(0, 0.25)
        values.append(round(max(0.2, min(12.0, trend + noise)), 2))
    return values


GENERATORS = {
    "daily_revenue": gen_daily_revenue,
    "daily_signups": gen_daily_signups,
    "churn_rate": gen_churn_rate,
}


def seed(db_path, days=DAYS, force=False):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with database.connect(db_path) as conn:
        database.init_db(conn)
        existing = database.get_metrics(conn)
        if existing and not force:
            return {"seeded": False, "metrics": existing}

        date_list = _dates(days=days)
        for metric, gen in GENERATORS.items():
            values = gen(days)
            rows = list(zip(date_list, values))
            database.upsert_history(conn, metric, rows)

        return {"seeded": True, "metrics": list(GENERATORS.keys()), "days": days}


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    default_db = os.path.join(here, "..", "data", "kpi.db")
    result = seed(default_db, force=True)
    print(result)
