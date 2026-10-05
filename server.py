"""
Gate 3 — Backend API
所有氣象資料都由 data.db (Gate 2) 讀出，這裡沒有任何 hard-code 的預報資料。
"""

import os
import sqlite3

from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"), static_url_path="")


def get_db_connection():
    # Vercel filesystem is read-only, so open SQLite in read-only mode.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@app.errorhandler(sqlite3.Error)
def handle_db_error(_exc):
    return jsonify({"error": "database unavailable — run gate1 and gate2 first"}), 503


@app.route("/")
def serve_index():
    return app.send_static_file("index.html")


@app.route("/api/periods")
def get_periods():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT forecast_start, MIN(forecast_end) AS forecast_end
            FROM weather_forecasts GROUP BY forecast_start ORDER BY forecast_start
            """
        ).fetchall()
        meta = conn.execute(
            "SELECT MAX(fetched_at) AS fetched_at, MAX(source) AS source FROM weather_forecasts"
        ).fetchone()
    finally:
        conn.close()
    return jsonify({
        "periods": [{"start": r["forecast_start"], "end": r["forecast_end"]} for r in rows],
        "fetched_at": meta["fetched_at"],
        "source": meta["source"],
    })


@app.route("/api/weather")
def get_weather():
    """Forecast of every location for one period (?start=..., default = earliest)."""
    start = request.args.get("start")
    conn = get_db_connection()
    try:
        if not start:
            start = conn.execute("SELECT MIN(forecast_start) FROM weather_forecasts").fetchone()[0]
        rows = conn.execute(
            """
            SELECT location_name, latitude, longitude, forecast_start, forecast_end,
                   weather, avg_temp, min_temp, max_temp, rain_probability
            FROM weather_forecasts WHERE forecast_start = ?
            ORDER BY location_name
            """,
            (start,),
        ).fetchall()
    finally:
        conn.close()
    return jsonify([
        {
            "location": r["location_name"],
            "lat": r["latitude"],
            "lon": r["longitude"],
            "start": r["forecast_start"],
            "end": r["forecast_end"],
            "weather": r["weather"],
            "avg_temp": r["avg_temp"],
            "min_temp": r["min_temp"],
            "max_temp": r["max_temp"],
            "pop": r["rain_probability"],
        }
        for r in rows
    ])


@app.route("/api/forecast/<location>")
def get_forecast(location):
    """All periods (7 days) for one location."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT forecast_start, forecast_end, weather, min_temp, max_temp, rain_probability
            FROM weather_forecasts WHERE location_name = ? ORDER BY forecast_start
            """,
            (location,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return jsonify({"error": "location not found"}), 404
    return jsonify([
        {
            "start": r["forecast_start"],
            "end": r["forecast_end"],
            "weather": r["weather"],
            "min_temp": r["min_temp"],
            "max_temp": r["max_temp"],
            "pop": r["rain_probability"],
        }
        for r in rows
    ])


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
