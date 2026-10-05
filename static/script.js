// Initialize Map
const TAIWAN_BOUNDS = [[21.8, 119.3], [25.4, 122.1]];

const map = L.map('map', {
    zoomControl: false // Hide default zoom control to not overlap with panels
}).fitBounds(TAIWAN_BOUNDS);

L.control.zoom({ position: 'bottomleft' }).addTo(map);

// Tile Layers — both are OpenStreetMap; the dark one is the same tiles darkened by a CSS filter
const OSM_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const darkTiles = L.tileLayer(OSM_URL, { attribution: OSM_ATTRIBUTION, maxZoom: 19, className: 'tiles-dark' });
const streetTiles = L.tileLayer(OSM_URL, { attribution: OSM_ATTRIBUTION, maxZoom: 19 });

darkTiles.addTo(map); // Default

// State
let currentLayer = 'temp'; // 'temp' or 'rain'
let showLabels = true;
let showGeojson = true;
let periods = [];
let weatherData = [];
let countyLayer = null;
const markerGroup = L.layerGroup().addTo(map);

// Color scales (bins: [lower bound, color, legend label])
const SCALES = {
    temp: {
        title: '最高溫 °C',
        bins: [
            [32, '#ef4444', '≥32'],
            [28, '#f59e0b', '28–31'],
            [24, '#10b981', '24–27'],
            [20, '#0ea5e9', '20–23'],
            [-Infinity, '#3b82f6', '<20']
        ]
    },
    rain: {
        title: '降雨機率 %',
        bins: [
            [80, '#1d4ed8', '≥80'],
            [50, '#3b82f6', '50–79'],
            [20, '#7dd3fc', '20–49'],
            [-Infinity, '#94a3b8', '<20']
        ]
    }
};
const NO_DATA_COLOR = '#475569';

function layerValue(d) {
    return currentLayer === 'temp' ? d.max_temp : d.pop;
}

function colorFor(value) {
    if (value === null || value === undefined) return NO_DATA_COLOR;
    return SCALES[currentLayer].bins.find(b => value >= b[0])[1];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.innerText = text === null || text === undefined ? '-' : String(text);
    return div.innerHTML;
}

function formatPeriod(startIso, endIso) {
    const start = new Date(startIso);
    const weekday = ['日', '一', '二', '三', '四', '五', '六'][start.getDay()];
    const hh = iso => iso.substring(11, 16);
    const slot = start.getHours() >= 18 || start.getHours() < 6 ? '夜晚' : '白天';
    return `${startIso.substring(5, 10).replace('-', '/')} (${weekday}) ${slot} ${hh(startIso)}–${hh(endIso)}`;
}

function showError(message) {
    const box = document.getElementById('error-box');
    box.innerText = message;
    box.hidden = false;
}

async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
    return res.json();
}

// Dashboard stats
function updateDashboard() {
    let maxTemp = null, minTemp = null, maxRain = null;
    const weatherCounts = {};

    weatherData.forEach(d => {
        if (d.max_temp !== null && (maxTemp === null || d.max_temp > maxTemp.max_temp)) maxTemp = d;
        if (d.min_temp !== null && (minTemp === null || d.min_temp < minTemp.min_temp)) minTemp = d;
        if (d.pop !== null && (maxRain === null || d.pop > maxRain.pop)) maxRain = d;
        if (d.weather) weatherCounts[d.weather] = (weatherCounts[d.weather] || 0) + 1;
    });

    document.getElementById('max-temp').innerText = maxTemp ? maxTemp.max_temp : '-';
    document.getElementById('max-temp-loc').innerText = maxTemp ? maxTemp.location : '-';
    document.getElementById('min-temp').innerText = minTemp ? minTemp.min_temp : '-';
    document.getElementById('min-temp-loc').innerText = minTemp ? minTemp.location : '-';
    document.getElementById('max-rain').innerText = maxRain ? maxRain.pop : '-';
    document.getElementById('max-rain-loc').innerText = maxRain ? maxRain.location : '-';

    const common = Object.keys(weatherCounts).sort((a, b) => weatherCounts[b] - weatherCounts[a])[0];
    document.getElementById('common-weather').innerText = common || '-';
    document.getElementById('loc-count').innerText = `${weatherData.length} 縣市`;
}

function renderLegend() {
    const scale = SCALES[currentLayer];
    document.getElementById('legend-title').innerText = scale.title;
    document.getElementById('legend-swatches').innerHTML = scale.bins.slice().reverse()
        .map(b => `<div class="legend-item"><span class="legend-color" style="background:${b[1]}"></span>${b[2]}</div>`)
        .join('');
}

function popupHtml(d) {
    return `
        <div class="popup-custom">
            <h3>${escapeHtml(d.location)}</h3>
            <p>天氣：${escapeHtml(d.weather)}</p>
            <p>氣溫：${escapeHtml(d.min_temp)}°C ~ ${escapeHtml(d.max_temp)}°C</p>
            <p>降雨機率：${d.pop !== null ? escapeHtml(d.pop) + '%' : '-'}</p>
            <div class="popup-forecast" data-location="${escapeHtml(d.location)}">載入 7 天預報...</div>
        </div>`;
}

// Fill the popup with the 7-day forecast of that county (also from the database)
async function loadPopupForecast(popup) {
    const el = popup.getElement().querySelector('.popup-forecast');
    if (!el) return;
    try {
        const rows = await fetchJson(`/api/forecast/${encodeURIComponent(el.dataset.location)}`);
        el.innerHTML = '<table>' + rows.map(r => `
            <tr>
                <td>${escapeHtml(formatPeriod(r.start, r.end).substring(0, 12))}</td>
                <td>${escapeHtml(r.min_temp)}~${escapeHtml(r.max_temp)}°</td>
                <td>${r.pop !== null ? escapeHtml(r.pop) + '%' : '-'}</td>
                <td>${escapeHtml(r.weather)}</td>
            </tr>`).join('') + '</table>';
        popup.update();
    } catch (e) {
        el.innerText = '7 天預報載入失敗';
    }
}
map.on('popupopen', e => loadPopupForecast(e.popup));

function renderMarkers() {
    markerGroup.clearLayers();
    const suffix = currentLayer === 'temp' ? '°C' : '%';

    weatherData.forEach(d => {
        if (d.lat === null || d.lon === null) return;
        const value = layerValue(d);
        const color = colorFor(value);
        const text = `${escapeHtml(d.location)} ${value !== null ? value + suffix : '-'}`;

        const icon = showLabels
            ? L.divIcon({
                html: `<div class="custom-pill-label" style="border-left: 4px solid ${color};">${text}</div>`,
                className: 'pill-wrapper',
                iconSize: [0, 0]
            })
            : L.divIcon({
                html: `<div class="custom-dot" style="background:${color};"></div>`,
                className: '',
                iconSize: [16, 16],
                iconAnchor: [8, 8]
            });

        L.marker([d.lat, d.lon], { icon: icon })
            .bindPopup(popupHtml(d), { maxWidth: 340 })
            .addTo(markerGroup);
    });
}

function styleCounties() {
    if (!countyLayer) return;
    const byName = Object.fromEntries(weatherData.map(d => [d.location, d]));
    countyLayer.eachLayer(layer => {
        const d = byName[layer.feature.properties.name];
        layer.setStyle({
            color: 'rgba(255,255,255,0.45)',
            weight: 1,
            fillColor: colorFor(d ? layerValue(d) : null),
            fillOpacity: 0.45
        });
        if (d) layer.bindPopup(popupHtml(d), { maxWidth: 340 });
    });
}

function render() {
    updateDashboard();
    renderLegend();
    styleCounties();
    renderMarkers();
}

async function loadPeriod(index) {
    const p = periods[index];
    document.getElementById('period-label').innerText = formatPeriod(p.start, p.end);
    try {
        weatherData = await fetchJson(`/api/weather?start=${encodeURIComponent(p.start)}`);
        render();
    } catch (e) {
        console.error(e);
        showError('無法讀取天氣資料：' + e.message);
    }
}

async function boot() {
    renderLegend();

    // Taiwan county boundaries (GeoJSON) — geometry only, colors come from the database values
    try {
        const geojson = await fetchJson('taiwan_counties.geojson');
        countyLayer = L.geoJSON(geojson).addTo(map);
    } catch (e) {
        console.error(e);
        showError('縣市界 GeoJSON 載入失敗');
    }

    try {
        const meta = await fetchJson('/api/periods');
        periods = meta.periods;
        document.getElementById('source').innerText = meta.source || '-';
        document.getElementById('fetched-at').innerText =
            meta.fetched_at ? meta.fetched_at.substring(0, 16).replace('T', ' ') : '-';
        if (periods.length === 0) {
            showError('資料庫沒有預報資料，請先執行 Gate 1 與 Gate 2。');
            return;
        }
        document.getElementById('period-slider').max = periods.length - 1;
        await loadPeriod(0);
    } catch (e) {
        console.error(e);
        showError('無法連線後端 API：' + e.message);
    }
}

// Events
function setLayer(layer) {
    currentLayer = layer;
    document.getElementById('btn-temp').classList.toggle('active', layer === 'temp');
    document.getElementById('btn-rain').classList.toggle('active', layer === 'rain');
    render();
}
document.getElementById('btn-temp').addEventListener('click', () => setLayer('temp'));
document.getElementById('btn-rain').addEventListener('click', () => setLayer('rain'));

document.getElementById('period-slider').addEventListener('input', e => {
    loadPeriod(Number(e.target.value));
});

document.getElementById('toggle-marker').addEventListener('change', e => {
    showLabels = e.target.checked;
    renderMarkers();
});

document.getElementById('toggle-geojson').addEventListener('change', e => {
    showGeojson = e.target.checked;
    if (!countyLayer) return;
    if (showGeojson) countyLayer.addTo(map); else map.removeLayer(countyLayer);
});

function setBase(dark) {
    document.getElementById('base-dark').classList.toggle('active', dark);
    document.getElementById('base-street').classList.toggle('active', !dark);
    map.removeLayer(dark ? streetTiles : darkTiles);
    (dark ? darkTiles : streetTiles).addTo(map);
}
document.getElementById('base-dark').addEventListener('click', () => setBase(true));
document.getElementById('base-street').addEventListener('click', () => setBase(false));

document.getElementById('btn-locate').addEventListener('click', () => {
    map.fitBounds(TAIWAN_BOUNDS);
});

// Boot
boot();
