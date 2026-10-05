"""
Gate 1 — CWA API
Dataset : F-D0047-091（臺灣各縣市鄉鎮未來1週天氣預報，縣市層級）
Flow    : .env key → real HTTP request → inspect real JSON schema → parse → gate1_output.json
Rules   :
  - API key 只從 .env / 環境變數讀取，任何輸出都不顯示 key
  - 不使用 mock/fake data
  - 本 Gate 不碰 Database / GIS / GitHub / Vercel
"""

import json
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_ID = "F-D0047-091"
BASE_URL = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{DATASET_ID}"
RAW_FILE = os.path.join(BASE_DIR, "gate1_raw_response.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "gate1_output.json")

# CWA ElementName → (short key, ElementValue 內實際的值欄位)
ELEMENT_MAP = {
    "平均溫度": ("T", "Temperature"),
    "最高溫度": ("MaxT", "MaxTemperature"),
    "最低溫度": ("MinT", "MinTemperature"),
    "天氣現象": ("Wx", "Weather"),
    "12小時降雨機率": ("PoP", "ProbabilityOfPrecipitation"),
}
REQUIRED = ["T", "MaxT", "MinT", "Wx", "PoP"]
EXPECTED_COUNTIES = 22


def fail(message: str) -> None:
    print(f"\n[FAIL] {message}")
    print("GATE 1 = FAIL -- fix before Gate 2")
    sys.exit(1)


def load_key() -> str:
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    key = (os.getenv("CWA_API_KEY") or "").strip()
    if not key or key == "YOUR_CWA_API_KEY":
        fail("CWA_API_KEY not found. Copy .env.example to .env and fill in your key.")
    return key


def fetch_all(api_key: str) -> dict:
    """Fetch F-D0047-091 for all Taiwan counties (no location filter)."""
    try:
        resp = requests.get(
            BASE_URL,
            params={"Authorization": api_key, "format": "JSON"},
            timeout=60,
        )
    except requests.RequestException as exc:
        # requests 的例外訊息會帶完整 URL（含 key），所以只印例外類別
        fail(f"CWA request failed: {type(exc).__name__}")
    print(f"[STEP 2] HTTP status     : {resp.status_code}")
    if resp.status_code != 200:
        fail(f"CWA API returned HTTP {resp.status_code} (401 = key 無效)")
    try:
        return resp.json()
    except ValueError:
        fail("CWA response is not valid JSON")


def parse_county(county: dict) -> dict:
    elements = {}
    for elem in county.get("WeatherElement", []):
        mapped = ELEMENT_MAP.get(elem.get("ElementName"))
        if not mapped:
            continue
        key, value_field = mapped
        periods = []
        for t in elem.get("Time", []):
            ev = (t.get("ElementValue") or [{}])[0]
            value = ev.get(value_field)
            if value is None and ev:
                value = next(iter(ev.values()))
            periods.append({
                "start": t.get("StartTime"),
                "end": t.get("EndTime"),
                "value": value,
            })
        elements[key] = periods
    return {
        "location": county.get("LocationName"),
        "lat": county.get("Latitude"),
        "lon": county.get("Longitude"),
        "elements": elements,
    }


def main() -> None:
    api_key = load_key()
    print("[STEP 1] API key loaded  : ******** (masked)")
    print(f"[STEP 1] Dataset         : {DATASET_ID}")
    print(f"[STEP 1] Endpoint        : {BASE_URL}")

    data = fetch_all(api_key)
    success = str(data.get("success")).lower() == "true"
    print(f"[STEP 2] success field   : {data.get('success')}")
    if not success:
        fail("CWA response success != true")

    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Inspect the real schema before parsing ──────────────────────────────
    records = data.get("records", {})
    groups = records.get("Locations", [])
    print(f"[STEP 3] Top-level keys  : {list(data.keys())}")
    print(f"[STEP 3] records keys    : {list(records.keys())}")
    if not groups:
        fail("records.Locations is empty — schema differs from expectation")
    county_list = groups[0].get("Location", [])
    print(f"[STEP 3] LocationsName   : {groups[0].get('LocationsName')}")
    print(f"[STEP 3] Counties found  : {len(county_list)}")
    if not county_list:
        fail("No Location entries in response")
    sample_raw = county_list[0]
    print(f"[STEP 3] Location keys   : {list(sample_raw.keys())}")
    for elem in sample_raw.get("WeatherElement", []):
        times = elem.get("Time", [])
        value_keys = list((times[0].get("ElementValue") or [{}])[0].keys()) if times else []
        print(f"           {elem.get('ElementName'):10s} periods={len(times):2d} value keys={value_keys}")

    # ── Parse ──────────────────────────────────────────────────────────────
    forecasts = [parse_county(c) for c in county_list]

    sample = next((f for f in forecasts if f["location"] == "臺中市"), forecasts[0])
    el = sample["elements"]
    n = min((len(el.get(k, [])) for k in REQUIRED), default=0)
    print(f"\n[STEP 4] Sample: {sample['location']} ({n} periods)")
    print(f"  {'Start':16s}  {'End':16s}  {'T':>3s} {'MaxT':>4s} {'MinT':>4s} {'PoP':>4s}  Wx")
    for i in range(n):
        print(
            f"  {el['MaxT'][i]['start'][:16]}  {el['MaxT'][i]['end'][:16]}  "
            f"{el['T'][i]['value']:>3s} {el['MaxT'][i]['value']:>4s} {el['MinT'][i]['value']:>4s} "
            f"{el['PoP'][i]['value']:>4s}  {el['Wx'][i]['value']}"
        )

    span_days = 0.0
    if n:
        first = datetime.fromisoformat(el["MaxT"][0]["start"])
        last = datetime.fromisoformat(el["MaxT"][n - 1]["end"])
        span_days = (last - first).total_seconds() / 86400
    print(f"  Forecast span: {span_days:.1f} days")

    # ── Coverage ───────────────────────────────────────────────────────────
    incomplete = [
        f["location"] for f in forecasts
        if not all(f["elements"].get(k) for k in REQUIRED)
    ]
    print(f"\n[STEP 5] Coverage: {len(forecasts) - len(incomplete)}/{len(forecasts)} counties with all fields")
    print("  " + "、".join(f["location"] for f in forecasts))
    if incomplete:
        print(f"  Missing fields: {incomplete}")

    # ── Clean output for Gate 2 (no secrets) ───────────────────────────────
    output = {
        "meta": {
            "dataset": DATASET_ID,
            "source": "CWA Open Data API",
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "forecasts": forecasts,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[STEP 6] gate1_output.json saved — {len(forecasts)} counties")

    with open(OUTPUT_FILE, encoding="utf-8") as f:
        key_leaked = api_key in f.read()

    checks = {
        f"Dataset = {DATASET_ID}": True,
        "CWA authentication success": success,
        "HTTP 200 OK, success = true": success,
        "Real JSON received": bool(county_list),
        "Actual JSON schema inspected": True,
        "7-day forecast confirmed (>= 6.5 days)": span_days >= 6.5,
        "T / MaxT / MinT / Wx / PoP all confirmed": all(k in el for k in REQUIRED),
        f"{EXPECTED_COUNTIES}/{EXPECTED_COUNTIES} Taiwan counties coverage confirmed":
            len(forecasts) == EXPECTED_COUNTIES and not incomplete,
        "No mock/fake data": True,
        "No API Key in gate1_output.json": not key_leaked,
    }
    print("\n" + "=" * 60)
    print("GATE 1 PASS CHECKLIST")
    print("=" * 60)
    for check, ok in checks.items():
        print(f"  {'[PASS]' if ok else '[FAIL]'}  {check}")
    print("=" * 60)
    if all(checks.values()):
        print("GATE 1 = PASS")
    else:
        print("GATE 1 = FAIL -- fix failing items before Gate 2")
        sys.exit(1)


if __name__ == "__main__":
    main()
