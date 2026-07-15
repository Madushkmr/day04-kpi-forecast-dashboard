import os
import tempfile

import pytest

from src import database


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # let sqlite create it fresh
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_init_and_upsert_history(db_path):
    with database.connect(db_path) as conn:
        database.init_db(conn)
        database.upsert_history(conn, "metric_a", [("2025-01-01", 10.0), ("2025-01-02", 12.0)])
        rows = database.get_history(conn, "metric_a")
        assert rows == [("2025-01-01", 10.0), ("2025-01-02", 12.0)]


def test_upsert_is_idempotent_on_conflict(db_path):
    with database.connect(db_path) as conn:
        database.init_db(conn)
        database.upsert_history(conn, "metric_a", [("2025-01-01", 10.0)])
        database.upsert_history(conn, "metric_a", [("2025-01-01", 99.0)])  # update, not duplicate
        rows = database.get_history(conn, "metric_a")
        assert rows == [("2025-01-01", 99.0)]


def test_get_metrics_distinct(db_path):
    with database.connect(db_path) as conn:
        database.init_db(conn)
        database.upsert_history(conn, "a", [("2025-01-01", 1.0)])
        database.upsert_history(conn, "b", [("2025-01-01", 2.0)])
        assert database.get_metrics(conn) == ["a", "b"]


def test_save_and_get_latest_forecast(db_path):
    with database.connect(db_path) as conn:
        database.init_db(conn)
        rows = [("2025-02-01", 10.0, 8.0, 12.0), ("2025-02-02", 11.0, 9.0, 13.0)]
        database.save_forecast(conn, "metric_a", "holt_linear", rows)
        latest = database.get_latest_forecast(conn, "metric_a", "holt_linear")
        assert len(latest) == 2
        assert latest[0]["date"] == "2025-02-01"
        assert latest[0]["forecast_value"] == 10.0


def test_save_and_get_alerts(db_path):
    with database.connect(db_path) as conn:
        database.init_db(conn)
        alerts = [{
            "metric": "metric_a", "date": "2025-02-01", "actual_value": 5.0,
            "forecast_value": 10.0, "lower_bound": 8.0, "upper_bound": 12.0,
            "severity": "high", "method": "holt_linear",
        }]
        database.save_alerts(conn, alerts)
        fetched = database.get_alerts(conn, metric="metric_a")
        assert len(fetched) == 1
        assert fetched[0]["severity"] == "high"


def test_clear_alerts(db_path):
    with database.connect(db_path) as conn:
        database.init_db(conn)
        alerts = [{
            "metric": "metric_a", "date": "2025-02-01", "actual_value": 5.0,
            "forecast_value": 10.0, "lower_bound": 8.0, "upper_bound": 12.0,
            "severity": "high", "method": "holt_linear",
        }]
        database.save_alerts(conn, alerts)
        database.clear_alerts(conn, metric="metric_a")
        assert database.get_alerts(conn, metric="metric_a") == []
