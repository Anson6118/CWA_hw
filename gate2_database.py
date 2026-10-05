"""
Gate 2 — Database
Flow : gate1_output.json → Transform / Validate → SQLite (data.db) → SQL SELECT 驗證
Duplicate strategy : UNIQUE(location_name, forecast_start) + INSERT OR REPLACE
本 Gate 不碰 GIS。
"""

import json
import os
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "data.db")
INPUT_FILE = os.path.join(BASE_DIR, "gate1_output.json")

# F-D0047-091 的縣市層級資料不一定附經緯度；缺少時用縣市政府所在地座標補上。
# 這只是地理座標，不是氣象資料。
COORDINATES = {
    "臺北市": (25.0330, 121.5654), "新北市": (25.0112, 121.4617),
    "基隆市": (25.1287, 121.7397), "桃園市": (24.9937, 121.3009),
    "新竹市": (24.8138, 120.9675), "新竹縣": (24.8385, 121.0177),
    "苗栗縣": (24.5601, 120.8234), "臺中市": (24.1477, 120.6736),
    "彰化縣": (24.0820, 120.5385), "南投縣": (23.9037, 120.6698),
    "雲林縣": (23.7092, 120.4313), "嘉義市": (23.4800, 120.4491),
    "嘉義縣": (23.4518, 120.2554), "臺南市": (22.9998, 120.2268),
    "高雄市": (22.6272, 120.3014), "屏東縣": (22.6719, 120.4879),
    "宜蘭縣": (24.7570, 121.7408), "花蓮縣": (23.9871, 121.6015),
    "臺東縣": (22.7583, 121.1444), "澎湖縣": (23.5711, 119.5793),
    "金門縣": (24.4297, 118.3205), "連江縣": (26.1505, 119.9328),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS weather_forecasts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    location_name    TEXT NOT NULL,
    latitude         REAL,
    longitude        REAL,
    forecast_start   TEXT NOT NULL,
    forecast_end     TEXT NOT NULL,
    weather          TEXT,
    avg_temp         REAL,
    min_temp         REAL,
    max_temp         REAL,
    rain_probability REAL,
    source           TEXT,
    fetched_at       TEXT,
    UNIQUE(location_name, forecast_start)
);
"""


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def transform(data: dict) -> list:
    meta = data.get("meta", {})
    source = f"CWA {meta.get('dataset', '')}".strip()
    fetched_at = meta.get("fetched_at")

    rows = []
    for fc in data.get("forecasts", []):
        loc = fc.get("location")
        el = fc.get("elements", {})
        lat, lon = to_float(fc.get("lat")), to_float(fc.get("lon"))
        if lat is None or lon is None:
            lat, lon = COORDINATES.get(loc, (None, None))

        # 以 MaxT 的時段為基準，其餘欄位用 start time 對齊（不假設 index 一致）
        by_start = {
            key: {p["start"]: p["value"] for p in el.get(key, [])}
            for key in ("T", "MinT", "Wx", "PoP")
        }
        for p in el.get("MaxT", []):
            start, end = p.get("start"), p.get("end")
            if not loc or not start or not end:
                continue
            rows.append((
                loc, lat, lon, start, end,
                by_start["Wx"].get(start),
                to_float(by_start["T"].get(start)),
                to_float(by_start["MinT"].get(start)),
                to_float(p.get("value")),
                to_float(by_start["PoP"].get(start)),
                source, fetched_at,
            ))
    return rows


def load(conn, rows) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO weather_forecasts (
            location_name, latitude, longitude, forecast_start, forecast_end,
            weather, avg_temp, min_temp, max_temp, rain_probability, source, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def main() -> None:
    print(f"[STEP 1] Input    : {os.path.basename(INPUT_FILE)}")
    print(f"[STEP 1] Database : {os.path.basename(DB_FILE)}")
    if not os.path.exists(INPUT_FILE):
        print("[FAIL] gate1_output.json not found. Run Gate 1 first.")
        print("GATE 2 = FAIL")
        sys.exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    print(f"[STEP 2] Extract  : {len(data.get('forecasts', []))} locations")

    rows = transform(data)
    print(f"[STEP 3] Transform: {len(rows)} rows")

    conn = sqlite3.connect(DB_FILE)
    try:
        conn.executescript(SCHEMA)
        # 每次 ETL 以最新一次擷取為準：清掉已過期的時段，其餘靠 UNIQUE + REPLACE 去重
        if rows:
            conn.execute(
                "DELETE FROM weather_forecasts WHERE forecast_start < ?",
                (min(r[3] for r in rows),),
            )
        load(conn, rows)
        count_first = conn.execute("SELECT COUNT(*) FROM weather_forecasts").fetchone()[0]
        print(f"[STEP 4] Load     : {count_first} rows in weather_forecasts")

        # Duplicate strategy test: 同一批資料再載入一次，筆數不得增加
        load(conn, rows)
        count_second = conn.execute("SELECT COUNT(*) FROM weather_forecasts").fetchone()[0]
        print(f"[STEP 5] Reload   : {count_second} rows (duplicate strategy check)")

        print("\n[STEP 6] SQL SELECT verification")
        loc_count, period_count = conn.execute(
            "SELECT COUNT(DISTINCT location_name), COUNT(DISTINCT forecast_start) FROM weather_forecasts"
        ).fetchone()
        print(f"  Distinct locations : {loc_count}")
        print(f"  Distinct periods   : {period_count}")

        nulls = conn.execute(
            """
            SELECT COUNT(*) FROM weather_forecasts
            WHERE weather IS NULL OR min_temp IS NULL OR max_temp IS NULL
               OR latitude IS NULL OR longitude IS NULL
            """
        ).fetchone()[0]
        print(f"  Rows missing required fields : {nulls}")

        print("\n  臺中市 (first 4 periods):")
        for r in conn.execute(
            """
            SELECT forecast_start, weather, min_temp, max_temp, rain_probability
            FROM weather_forecasts WHERE location_name = ?
            ORDER BY forecast_start LIMIT 4
            """,
            ("臺中市",),
        ):
            print(f"    {r[0][:16]}  {r[2]:.0f}~{r[3]:.0f}°C  PoP={r[4]}  {r[1]}")

        print("\n  All locations, first period:")
        for r in conn.execute(
            """
            SELECT location_name, min_temp, max_temp, rain_probability, weather
            FROM weather_forecasts
            WHERE forecast_start = (SELECT MIN(forecast_start) FROM weather_forecasts)
            ORDER BY location_name
            """
        ):
            print(f"    {r[0]}  {r[1]:.0f}~{r[2]:.0f}°C  PoP={r[3]}  {r[4]}")
    finally:
        conn.close()

    checks = {
        "Read JSON output from Gate 1": bool(rows),
        "SQLite schema configured": True,
        "Duplicate strategy (UNIQUE/REPLACE) verified by reload": count_first == count_second,
        "ETL process successful": count_first == len(rows) and count_first > 0,
        "Verified via SQL SELECT (22 locations, no missing fields)": loc_count == 22 and nulls == 0,
        "No GIS work started": True,
    }
    print("\n" + "=" * 60)
    print("GATE 2 PASS CHECKLIST")
    print("=" * 60)
    for check, ok in checks.items():
        print(f"  {'[PASS]' if ok else '[FAIL]'}  {check}")
    print("=" * 60)
    if all(checks.values()):
        print("GATE 2 = PASS")
    else:
        print("GATE 2 = FAIL -- check errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
