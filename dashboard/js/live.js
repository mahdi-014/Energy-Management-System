// DCEMS Live Telemetry Dashboard Client (Phase 1)
// Local LAN polling, zero internet/CDN dependencies.

const POLL_INTERVAL_MS = 3000;

function formatRelativeTime(epochSec) {
    if (!epochSec || epochSec === 0) return "Never";
    const now = Math.floor(Date.now() / 1000);
    const diff = Math.max(0, now - epochSec);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
}

function updateElementText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

async function fetchLiveTelemetry() {
    try {
        const response = await fetch('/api/live', { cache: 'no-cache' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderLiveTelemetry(data);
    } catch (err) {
        renderErrorState(err.message);
    }
}

function renderLiveTelemetry(data) {
    const now = Math.floor(Date.now() / 1000);

    // 1. Connection & Controller Badges
    const connBadge = document.getElementById('connection-status-badge');
    if (connBadge) {
        if (data.is_online) {
            connBadge.className = 'badge badge-success';
            connBadge.textContent = 'Broker Online';
        } else {
            connBadge.className = 'badge badge-danger';
            connBadge.textContent = 'Offline';
        }
    }

    const modeBadge = document.getElementById('controller-mode-badge');
    if (modeBadge) {
        modeBadge.textContent = `Mode: ${data.mode || 'AUTO'}`;
    }

    updateElementText('last-sync-text', `Last Sync: ${new Date().toLocaleTimeString()}`);

    // 2. Offline / Staleness Alert Banner
    const banner = document.getElementById('status-banner');
    const bannerText = document.getElementById('status-banner-text');
    if (banner && bannerText) {
        if (!data.is_online) {
            banner.style.display = 'flex';
            banner.className = 'alert-banner banner-danger';
            bannerText.textContent = 'Controller Offline: The ESP8266 or MQTT broker connection is down. Automatic rules will pause.';
        } else if (data.is_stale) {
            banner.style.display = 'flex';
            banner.className = 'alert-banner banner-warning';
            bannerText.textContent = 'Telemetry Stale: No sensor updates received within the last 60 seconds.';
        } else {
            banner.style.display = 'none';
        }
    }

    // 3. Sensor Cards
    const sensor = data.sensor;
    if (sensor) {
        // Temperature
        if (sensor.temperature_c !== null && sensor.temperature_c !== undefined) {
            const tempVal = document.getElementById('val-temp');
            if (tempVal) tempVal.innerHTML = `${Number(sensor.temperature_c).toFixed(1)} <span class="unit">°C</span>`;
            updateElementText('val-temp-status', `Quality: ${sensor.sensor_quality || 'ok'}`);
        } else {
            const tempVal = document.getElementById('val-temp');
            if (tempVal) tempVal.innerHTML = `--.- <span class="unit">°C</span>`;
            updateElementText('val-temp-status', 'Sensor: Fault / Disconnected');
        }

        // Humidity
        if (sensor.humidity_pct !== null && sensor.humidity_pct !== undefined) {
            const humVal = document.getElementById('val-hum');
            if (humVal) humVal.innerHTML = `${Math.round(sensor.humidity_pct)} <span class="unit">%</span>`;
            updateElementText('val-hum-status', 'Comfort: Normal');
        } else {
            const humVal = document.getElementById('val-hum');
            if (humVal) humVal.innerHTML = `-- <span class="unit">%</span>`;
            updateElementText('val-hum-status', 'Sensor: Fault / Disconnected');
        }

        // Ambient Light
        if (sensor.ldr_raw !== null && sensor.ldr_raw !== undefined) {
            const lightVal = document.getElementById('val-light');
            const pct = sensor.ambient_light_level !== null ? sensor.ambient_light_level : Math.round((sensor.ldr_raw / 1023) * 100);
            if (lightVal) lightVal.innerHTML = `${pct} <span class="unit">%</span>`;
            updateElementText('val-ldr-raw', `Raw ADC: ${sensor.ldr_raw} / 1023`);
        } else {
            const lightVal = document.getElementById('val-light');
            if (lightVal) lightVal.innerHTML = `-- <span class="unit">%</span>`;
            updateElementText('val-ldr-raw', 'LDR: Fault / Disconnected');
        }

        // Occupancy Inference
        const occEl = document.getElementById('val-occupancy');
        const occState = sensor.occupancy_state || 'unknown';
        if (occEl) {
            occEl.className = 'card-value occupancy-badge';
            if (occState === 'occupied_recently') {
                occEl.classList.add('occupied');
                occEl.textContent = 'Occupied (Recent Motion)';
            } else if (occState === 'vacancy_candidate') {
                occEl.classList.add('candidate');
                occEl.textContent = 'Vacancy Candidate';
            } else if (occState === 'vacant_confirmed') {
                occEl.classList.add('vacant');
                occEl.textContent = 'Vacant Confirmed';
            } else {
                occEl.classList.add('unknown');
                occEl.textContent = 'Unknown (Awaiting Motion)';
            }
        }

        updateElementText('val-last-motion', `Last motion: ${formatRelativeTime(sensor.last_motion_at)}`);
    }

    // 4. Commanded Appliance States
    const devices = data.devices || {};
    renderDeviceState('state-light', devices.light_01);
    renderDeviceState('state-fan', devices.fan_01);
    renderDeviceState('state-ac', devices.ac_01);
    renderDeviceState('state-pc', devices.pc_01);
}

function renderDeviceState(elementId, state) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const isON = (state === 'ON');
    el.textContent = isON ? 'ON' : 'OFF';
    el.className = isON ? 'appliance-state state-on' : 'appliance-state state-off';
}

function renderErrorState(errorMsg) {
    const connBadge = document.getElementById('connection-status-badge');
    if (connBadge) {
        connBadge.className = 'badge badge-danger';
        connBadge.textContent = 'API Error';
    }

    const banner = document.getElementById('status-banner');
    const bannerText = document.getElementById('status-banner-text');
    if (banner && bannerText) {
        banner.style.display = 'flex';
        banner.className = 'alert-banner banner-danger';
        bannerText.textContent = `Backend Communication Error: ${errorMsg}`;
    }
}

// Initial fetch and polling loop
document.addEventListener('DOMContentLoaded', () => {
    fetchLiveTelemetry();
    setInterval(fetchLiveTelemetry, POLL_INTERVAL_MS);
});

