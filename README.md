# Taiwan Weather GIS Dashboard
## AIoT L3 — CWA HW1（7115056010）

> **CWA Open Data → Database → Taiwan GIS → GitHub → Vercel**

本作業以中央氣象署（CWA）真實 Open Data 為資料來源，從 API 取得資料開始，經過 ETL 與 SQLite 儲存，再建立本機 Taiwan GIS Web，最後推送 GitHub 並由 Vercel 自動部署。

## 五大 Gate — 進度追蹤

| Gate | 主題 | 狀態 | 備註 |
|---|---|---|---|
| 1 | CWA API | ⏳ 待執行 | 程式完成（`gate1_cwa_api.py`），需先在 `.env` 填入 CWA 授權碼 |
| 2 | Database | ⏳ 待執行 | 程式完成（`gate2_database.py`），需 Gate 1 的 `gate1_output.json` |
| 3 | Taiwan GIS Web | ⏳ 待執行 | 程式完成（`server.py` + `static/`），需 Gate 2 的 `data.db` |
| 4 | GitHub | ⏳ 待執行 | `.gitignore` 已設定，尚未建立 repository |
| 5 | Vercel | ⏳ 待執行 | `vercel.json` 與 `api/index.py` 已設定，尚未部署 |

> 每個 Gate 實際執行並看到 `GATE n = PASS` 後，再把上表改成 ✅ PASS 並填上日期。

## 核心流程

```text
CWA Government Open Data
        ↓
     REST API                gate1_cwa_api.py
        ↓
       JSON                  gate1_output.json
        ↓
 Parse / Clean / Transform   gate2_database.py
        ↓
      SQLite                 data.db
        ↓
   Backend API               server.py (Flask)
        ↓
Taiwan GIS Web               static/ (Leaflet + OpenStreetMap + GeoJSON)
        ↓
      GitHub
        ↓
      Vercel                 vercel.json + api/index.py
        ↓
   Public Website
```

## 專案結構

```text
CWA_7115056010/
├── gate1_cwa_api.py        Gate 1：呼叫 CWA API、檢查 schema、輸出 gate1_output.json
├── gate2_database.py       Gate 2：ETL → SQLite (data.db) 並以 SQL 驗證
├── server.py               Gate 3：Flask 後端，資料全部讀自 data.db
├── static/
│   ├── index.html          Dashboard 頁面
│   ├── style.css
│   ├── script.js           Leaflet 地圖、Marker、Popup、圖層切換
│   └── taiwan_counties.geojson   22 縣市界
├── api/index.py            Gate 5：Vercel Serverless 進入點
├── vercel.json
├── requirements.txt
├── .env.example
└── .gitignore
```

## 環境準備

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # 然後把 .env 裡的 CWA_API_KEY 換成自己的授權碼
```

CWA 授權碼申請：<https://opendata.cwa.gov.tw/> → 登入會員 → 取得授權碼。

## Gate 1 — CWA API

**Dataset：** `F-D0047-091`（臺灣各縣市未來 1 週天氣預報）

```bash
python gate1_cwa_api.py
```

腳本會：

1. 從 `.env` 讀取 `CWA_API_KEY`（任何輸出都不顯示 key）。
2. 對 CWA 發送真實 HTTP request，檢查 HTTP 200 與 `success = true`。
3. 把原始回應存成 `gate1_raw_response.json`（已列入 `.gitignore`），並印出實際 JSON schema。
4. 依實際 schema 解析 `T / MaxT / MinT / Wx / PoP`。
5. 輸出不含 secret 的 `gate1_output.json` 供 Gate 2 使用。

**JSON Schema：**
```text
records.Locations[0].Location[]
  └── LocationName
  └── WeatherElement[]
        ├── 平均溫度        (T)    — 14 periods × 12hr = 7 days
        ├── 最高溫度        (MaxT)
        ├── 最低溫度        (MinT)
        ├── 天氣現象        (Wx)
        └── 12小時降雨機率  (PoP)
```

**Gate 1 PASS Checklist：**
```text
[ ] Dataset = F-D0047-091
[ ] CWA authentication success
[ ] HTTP 200 OK, success = true
[ ] Real JSON received
[ ] Actual JSON schema inspected
[ ] 7-day forecast confirmed
[ ] T / MaxT / MinT / Wx / PoP all confirmed
[ ] 22/22 Taiwan counties coverage confirmed
[ ] No mock/fake data
[ ] No API Key in gate1_output.json
```

## Gate 2 — Database

**資料庫檔案：** `data.db`（SQLite）　**資料表：** `weather_forecasts`

```bash
python gate2_database.py
```

| Field | Type | Purpose |
|---|---|---|
| id | INTEGER | Primary key |
| location_name | TEXT | 縣市 |
| latitude / longitude | REAL | 座標（CWA 未提供時以縣市政府所在地補上） |
| forecast_start / forecast_end | TEXT | 預報時段 |
| weather | TEXT | 天氣現象 |
| avg_temp / min_temp / max_temp | REAL | 平均 / 最低 / 最高溫 |
| rain_probability | REAL | 12 小時降雨機率，可空 |
| source | TEXT | CWA dataset |
| fetched_at | TEXT | 擷取時間 |

- **Duplicate strategy：** `UNIQUE(location_name, forecast_start)` + `INSERT OR REPLACE`。腳本會把同一批資料載入兩次，確認筆數不增加。
- 各欄位以 `forecast_start` 對齊，不假設各氣象要素的時段 index 一致。
- 預期筆數：22 縣市 × 14 時段 = 308 筆。

**Gate 2 PASS Checklist：**
```text
[ ] Read JSON output from Gate 1
[ ] SQLite schema configured
[ ] Duplicate strategy (UNIQUE/REPLACE) verified by reload
[ ] ETL process successful
[ ] Verified via SQL SELECT (22 locations, no missing fields)
[ ] No GIS work started
```

## Gate 3 — Local Taiwan GIS Web

**技術：** Python Flask (API) + Vanilla JS / Leaflet (前端) + OpenStreetMap + Taiwan GeoJSON

```bash
python server.py
# 然後開啟 http://127.0.0.1:5000
```

| API | 說明 |
|---|---|
| `GET /api/periods` | 資料庫中所有預報時段、資料來源與擷取時間 |
| `GET /api/weather?start=<forecast_start>` | 指定時段全部縣市的預報（預設最早時段） |
| `GET /api/forecast/<縣市>` | 單一縣市 7 天預報 |

功能：

1. **Taiwan Map：** Leaflet + OpenStreetMap，深色 / 街道圖兩種底圖。
2. **Marker & Popup：** 22 縣市 Pill Marker；點擊顯示天氣、最高 / 最低溫、降雨機率與該縣市 7 天預報。
3. **Taiwan GeoJSON：** 縣市界依氣溫或降雨機率著色。
4. **Database Integration：** 畫面上的氣象數值全部由 Flask 從 `data.db` 讀出，沒有 hard-code 的預報資料。
5. **Interactive Dashboard：** 時段滑桿（14 個 12 小時時段）、氣溫 / 降雨機率圖層切換、統計卡片與圖例。

**Gate 3 PASS Checklist：**
```text
[ ] Local map displaying Taiwan
[ ] 22 locations shown on map
[ ] Popups showing correct Weather & Temperature
[ ] Data read from SQLite Gate 2 DB
[ ] GeoJSON layer + interactive dashboard working
```

## Gate 4 — GitHub

```bash
git init
git add .
git status                 # 確認清單中沒有 .env
git commit -m "AIoT L3 CWA HW1"
git branch -M main
git remote add origin https://github.com/<帳號>/<repo>.git
git push -u origin main
```

- `.env`、`.venv/`、`gate1_raw_response.json` 已被 `.gitignore` 排除。
- `data.db` **會** 一起 commit：Vercel 沒有執行 ETL 的步驟，網站需要這份唯讀資料庫才有資料。

## Gate 5 — Vercel Auto Deployment

1. 到 <https://vercel.com/> 以 GitHub 登入，**Add New → Project**，選擇本 repository 後 Deploy。
2. `vercel.json` 以 `@vercel/python` 建置 `api/index.py`，並把 `server.py`、`data.db`、`static/` 一併打包。
3. `api/index.py` 是 Serverless Function 進入點，負責載入 Flask `app`。
4. `server.py` 以絕對路徑與 SQLite read-only 模式開啟 `data.db`，因為 Vercel 檔案系統是唯讀的。

之後每次 `git push`，Vercel 會自動重新部署。要更新線上資料：重新執行 Gate 1、Gate 2，再 commit 新的 `data.db`。

> Local `data.db` 隨程式碼部署，作為唯讀資料庫；若需要線上持續寫入，應另接 Cloud Database。網站本身不呼叫 CWA API，所以 Vercel 上不需要設定 `CWA_API_KEY`。

## Security

真正的 CWA Key 只能存在 Local `.env`。

```env
CWA_API_KEY=YOUR_CWA_API_KEY
```

若 Secret 曾被 commit，必須視為 exposed 並到 CWA 重新產生，不能只刪檔案。

## Development Rule

**DO NOT BUILD EVERYTHING AT ONCE.**

```text
BUILD → RUN → TEST → VERIFY → PASS → NEXT GATE
```

Gate FAIL 就停在該 Gate 修正，不得自行跳到下一 Gate。禁止使用 mock/fake weather data，畫面資料必須可追溯：

```text
GIS → Backend → Database → ETL → CWA API
```

## 資料來源與授權

- 氣象資料：中央氣象署開放資料平臺 `F-D0047-091`
- 底圖：© OpenStreetMap contributors
- 縣市界：[taiwan-atlas](https://github.com/dkaoster/taiwan-atlas)（源自內政部國土測繪中心開放資料），轉為 GeoJSON
