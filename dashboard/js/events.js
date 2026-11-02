(function () {
    const navLive = document.getElementById("nav-live");
    const navEvents = document.getElementById("nav-events");
    const tabLive = document.getElementById("tab-live");
    const tabEvents = document.getElementById("tab-events");

    const filterDevice = document.getElementById("filter-device");
    const filterSource = document.getElementById("filter-source");
    const btnRefresh = document.getElementById("btn-refresh-events");

    const eventsTbody = document.getElementById("events-tbody");
    const sessionsTbody = document.getElementById("sessions-tbody");

    function switchTab(target) {
        const tabs = ["live", "events", "anomalies", "settings"];
        tabs.forEach(t => {
            const nav = document.getElementById("nav-" + t);
            const pane = document.getElementById("tab-" + t);
            if (nav) nav.classList.toggle("active", t === target);
            if (pane) pane.style.display = (t === target) ? "block" : "none";
        });
        if (target === "events") {
            refreshAllEventsData();
        }
    }

    if (navLive && navEvents) {
        navLive.addEventListener("click", function (e) {
            e.preventDefault();
            switchTab("live");
            window.location.hash = "live";
        });

        navEvents.addEventListener("click", function (e) {
            e.preventDefault();
            switchTab("events");
            window.location.hash = "events";
        });
    }

    // Check URL hash on initial load
    if (window.location.hash === "#events") {
        switchTab("events");
    }

    function formatTs(epochSec) {
        if (!epochSec) return "--";
        const d = new Date(epochSec * 1000);
        const utcStr = d.toISOString().replace("T", " ").substring(0, 19) + " UTC";
        const localStr = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        return `${utcStr} (${localStr})`;
    }

    function formatDuration(sec) {
        if (sec === null || sec === undefined) return "--";
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        if (m < 60) {
            return `${m}m ${s}s`;
        }
        const h = Math.floor(m / 60);
        const remM = m % 60;
        return `${h}h ${remM}m`;
    }

    async function loadRuntimeAnalysis() {
        try {
            const resp = await fetch("/api/analysis/runtime");
            if (!resp.ok) return;
            const data = await resp.json();
            const devs = data.devices || {};

            const map = {
                "light_01": { val: "rt-light-val", foot: "rt-light-foot" },
                "fan_01": { val: "rt-fan-val", foot: "rt-fan-foot" },
                "ac_01": { val: "rt-ac-val", foot: "rt-ac-foot" },
                "pc_01": { val: "rt-pc-val", foot: "rt-pc-foot" }
            };

            for (const [devId, elIds] of Object.entries(map)) {
                const info = devs[devId];
                const valEl = document.getElementById(elIds.val);
                const footEl = document.getElementById(elIds.foot);
                if (info && valEl) {
                    valEl.innerHTML = `${info.total_runtime_hours.toFixed(2)} <span class="unit">hrs</span>`;
                }
                if (info && footEl) {
                    footEl.innerText = `${info.completed_sessions} completed, ${info.interrupted_sessions} interrupted`;
                }
            }
        } catch (e) {
            console.error("Failed to fetch runtime analysis:", e);
        }
    }

    async function loadEvents() {
        try {
            const dev = filterDevice ? filterDevice.value : "";
            const src = filterSource ? filterSource.value : "";
            let url = "/api/events?limit=50";
            if (dev) url += `&device_id=${encodeURIComponent(dev)}`;
            if (src) url += `&state_source=${encodeURIComponent(src)}`;

            const resp = await fetch(url);
            if (!resp.ok) return;
            const events = await resp.json();

            if (!eventsTbody) return;

            if (events.length === 0) {
                eventsTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No state transition events match filters.</td></tr>`;
                return;
            }

            eventsTbody.innerHTML = events.map(ev => {
                const stateBadge = ev.requested_state === "ON"
                    ? `<span class="badge badge-success">ON</span>`
                    : `<span class="badge badge-danger">OFF</span>`;
                
                const srcBadge = `<span class="badge badge-info">${ev.state_source}</span>`;

                return `
                    <tr>
                        <td>${formatTs(ev.timestamp_utc)}</td>
                        <td><strong>${ev.device_id}</strong></td>
                        <td>${stateBadge}</td>
                        <td>${srcBadge}</td>
                        <td><code>${ev.reason_code}</code></td>
                        <td>${ev.controller_mode}</td>
                        <td>${ev.command_status}</td>
                    </tr>
                `;
            }).join("");
        } catch (e) {
            console.error("Failed to fetch events:", e);
        }
    }

    async function loadSessions() {
        try {
            const resp = await fetch("/api/analysis/sessions?limit=25");
            if (!resp.ok) return;
            const sessions = await resp.json();

            if (!sessionsTbody) return;

            if (sessions.length === 0) {
                sessionsTbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No runtime sessions recorded yet.</td></tr>`;
                return;
            }

            sessionsTbody.innerHTML = sessions.map(s => {
                let statusBadge;
                if (s.end_time_utc === null) {
                    statusBadge = `<span class="badge badge-info">Active</span>`;
                } else if (s.end_known === 1) {
                    statusBadge = `<span class="badge badge-success">Completed</span>`;
                } else {
                    statusBadge = `<span class="badge badge-warning">Interrupted (Gap)</span>`;
                }

                return `
                    <tr>
                        <td><code>${s.session_id.substring(0, 18)}...</code></td>
                        <td><strong>${s.device_id}</strong></td>
                        <td>${formatTs(s.start_time_utc)}</td>
                        <td>${s.end_time_utc ? formatTs(s.end_time_utc) : "<em>Active</em>"}</td>
                        <td>${formatDuration(s.estimated_duration_sec)}</td>
                        <td>${statusBadge}</td>
                    </tr>
                `;
            }).join("");
        } catch (e) {
            console.error("Failed to fetch sessions:", e);
        }
    }

    function refreshAllEventsData() {
        loadRuntimeAnalysis();
        loadEvents();
        loadSessions();
    }

    if (btnRefresh) {
        btnRefresh.addEventListener("click", refreshAllEventsData);
    }
    if (filterDevice) {
        filterDevice.addEventListener("change", loadEvents);
    }
    if (filterSource) {
        filterSource.addEventListener("change", loadEvents);
    }

    // Auto-refresh when on events tab every 10 seconds
    setInterval(function () {
        if (tabEvents && tabEvents.style.display !== "none") {
            refreshAllEventsData();
        }
    }, 10000);
})();

