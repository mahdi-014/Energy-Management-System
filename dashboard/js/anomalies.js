(function () {
    const navLive = document.getElementById("nav-live");
    const navEvents = document.getElementById("nav-events");
    const navAnomalies = document.getElementById("nav-anomalies");
    const navSettings = document.getElementById("nav-settings");

    const tabLive = document.getElementById("tab-live");
    const tabEvents = document.getElementById("tab-events");
    const tabAnomalies = document.getElementById("tab-anomalies");
    const tabSettings = document.getElementById("tab-settings");

    const filterStatus = document.getElementById("filter-anom-status");
    const filterSeverity = document.getElementById("filter-anom-severity");
    const btnRefreshAnomalies = document.getElementById("btn-refresh-anomalies");
    const anomaliesTbody = document.getElementById("anomalies-tbody");

    const calibForm = document.getElementById("daylight-calib-form");
    const btnCalibReset = document.getElementById("btn-calib-reset");
    const calibStatusBadge = document.getElementById("calib-status-badge");
    const calibCurrentLdr = document.getElementById("calib-current-ldr");
    const calibOnInput = document.getElementById("calib-on-thresh");
    const calibOffInput = document.getElementById("calib-off-thresh");
    const calibDeltaPreview = document.getElementById("calib-delta-preview");

    const allTabs = {
        "live": { nav: navLive, pane: tabLive },
        "events": { nav: navEvents, pane: tabEvents },
        "anomalies": { nav: navAnomalies, pane: tabAnomalies },
        "settings": { nav: navSettings, pane: tabSettings }
    };

    function activateTab(target) {
        const tabs = ["live", "events", "anomalies", "settings"];
        tabs.forEach(t => {
            const nav = document.getElementById("nav-" + t);
            const pane = document.getElementById("tab-" + t);
            if (nav) nav.classList.toggle("active", t === target);
            if (pane) pane.style.display = (t === target) ? "block" : "none";
        });

        if (target === "anomalies") {
            loadAnomalies();
        } else if (target === "settings") {
            loadCalibrationStatus();
        }
    }

    if (navAnomalies) {
        navAnomalies.addEventListener("click", function (e) {
            e.preventDefault();
            activateTab("anomalies");
            window.location.hash = "anomalies";
        });
    }

    if (navSettings) {
        navSettings.addEventListener("click", function (e) {
            e.preventDefault();
            activateTab("settings");
            window.location.hash = "settings";
        });
    }

    if (window.location.hash === "#anomalies") {
        activateTab("anomalies");
    } else if (window.location.hash === "#settings") {
        activateTab("settings");
    }

    function formatTs(epochSec) {
        if (!epochSec) return "--";
        const d = new Date(epochSec * 1000);
        return d.toISOString().replace("T", " ").substring(0, 19) + " UTC";
    }

    async function loadAnomalies() {
        try {
            const st = filterStatus ? filterStatus.value : "";
            const sev = filterSeverity ? filterSeverity.value : "";
            let url = "/api/anomalies?limit=50";
            if (st) url += `&status=${encodeURIComponent(st)}`;
            if (sev) url += `&severity=${encodeURIComponent(sev)}`;

            const resp = await fetch(url);
            if (!resp.ok) return;
            const anomalies = await resp.json();

            if (!anomaliesTbody) return;

            if (anomalies.length === 0) {
                anomaliesTbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">No anomaly alerts found.</td></tr>`;
                return;
            }

            anomaliesTbody.innerHTML = anomalies.map(anom => {
                let sevBadge;
                if (anom.severity === "warning") {
                    sevBadge = `<span class="badge badge-warning">Warning</span>`;
                } else if (anom.severity === "high") {
                    sevBadge = `<span class="badge badge-danger">High</span>`;
                } else if (anom.severity === "diagnostic") {
                    sevBadge = `<span class="badge" style="background-color:rgba(168,85,247,0.15);color:#c084fc;border:1px solid rgba(168,85,247,0.3);">Diagnostic</span>`;
                } else {
                    sevBadge = `<span class="badge badge-info">Info</span>`;
                }

                let statusBadge;
                if (anom.status === "open") {
                    statusBadge = `<span class="badge badge-danger">Open</span>`;
                } else if (anom.status === "acknowledged") {
                    statusBadge = `<span class="badge badge-warning">Acked</span>`;
                } else {
                    statusBadge = `<span class="badge badge-success">Resolved</span>`;
                }

                let ackBtn = "--";
                if (anom.status === "open") {
                    ackBtn = `<button class="btn-refresh btn-ack" data-id="${anom.anomaly_id}" style="padding:0.2rem 0.5rem;font-size:0.75rem;">Ack</button>`;
                }

                const evNote = anom.evidence ? (anom.evidence.note || JSON.stringify(anom.evidence)) : "--";

                return `
                    <tr>
                        <td>${formatTs(anom.timestamp_utc)}</td>
                        <td><strong>${anom.device_id || "System"}</strong></td>
                        <td><code>${anom.anomaly_type}</code></td>
                        <td>${sevBadge}</td>
                        <td>${anom.observed_value} <span class="text-muted">(th: ${anom.threshold_value})</span></td>
                        <td><small>${evNote}</small></td>
                        <td>${statusBadge}</td>
                        <td>${ackBtn}</td>
                    </tr>
                `;
            }).join("");

            // Attach event listeners to ack buttons
            document.querySelectorAll(".btn-ack").forEach(btn => {
                btn.addEventListener("click", async function () {
                    const id = this.getAttribute("data-id");
                    try {
                        const r = await fetch(`/api/anomalies/${encodeURIComponent(id)}/ack`, { method: "POST" });
                        if (r.ok) {
                            loadAnomalies();
                        }
                    } catch (err) {
                        console.error("Failed to ack anomaly:", err);
                    }
                });
            });
        } catch (e) {
            console.error("Failed to fetch anomalies:", e);
        }
    }

    async function loadCalibrationStatus() {
        try {
            const resp = await fetch("/api/settings/calibration-status");
            if (!resp.ok) return;
            const data = await resp.json();

            if (calibStatusBadge) {
                if (data.daylight_calibration_flag) {
                    calibStatusBadge.className = "badge badge-success";
                    calibStatusBadge.innerText = "Calibrated & Active";
                } else {
                    calibStatusBadge.className = "badge badge-warning";
                    calibStatusBadge.innerText = "Uncalibrated - Gated for Safety";
                }
            }

            if (calibCurrentLdr) {
                calibCurrentLdr.innerText = data.latest_ldr_raw !== null ? data.latest_ldr_raw : "Waiting...";
            }

            if (calibOnInput) calibOnInput.value = data.daylight_on_threshold;
            if (calibOffInput) calibOffInput.value = data.daylight_off_threshold;

            updateDeltaPreview();
        } catch (e) {
            console.error("Failed to fetch calibration status:", e);
        }
    }

    function updateDeltaPreview() {
        if (!calibOnInput || !calibOffInput || !calibDeltaPreview) return;
        const onVal = parseInt(calibOnInput.value, 10) || 0;
        const offVal = parseInt(calibOffInput.value, 10) || 0;
        const delta = offVal - onVal;
        calibDeltaPreview.innerText = delta;
        if (delta <= 0) {
            calibDeltaPreview.style.color = "var(--color-danger)";
        } else {
            calibDeltaPreview.style.color = "var(--color-success)";
        }
    }

    if (calibOnInput) calibOnInput.addEventListener("input", updateDeltaPreview);
    if (calibOffInput) calibOffInput.addEventListener("input", updateDeltaPreview);

    if (calibForm) {
        calibForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const onVal = parseInt(calibOnInput.value, 10);
            const offVal = parseInt(calibOffInput.value, 10);

            if (offVal <= onVal) {
                alert("Bright Threshold (Light Turn-OFF) must be strictly greater than Dark Threshold (Light Turn-ON) for hysteresis.");
                return;
            }

            try {
                const resp = await fetch("/api/settings/calibrate-daylight", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        daylight_on_threshold: onVal,
                        daylight_off_threshold: offVal,
                        set_calibrated: true
                    })
                });
                if (resp.ok) {
                    alert("Daylight calibration saved and detector activated successfully!");
                    loadCalibrationStatus();
                } else {
                    alert("Failed to save calibration.");
                }
            } catch (err) {
                console.error("Calibration error:", err);
            }
        });
    }

    if (btnCalibReset) {
        btnCalibReset.addEventListener("click", async function () {
            if (!confirm("Are you sure you want to lock and disable the daylight detector?")) return;
            try {
                const resp = await fetch("/api/settings/calibrate-daylight", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ set_calibrated: false })
                });
                if (resp.ok) {
                    alert("Daylight detector has been locked and disabled.");
                    loadCalibrationStatus();
                }
            } catch (err) {
                console.error("Reset error:", err);
            }
        });
    }

    if (filterStatus) filterStatus.addEventListener("change", loadAnomalies);
    if (filterSeverity) filterSeverity.addEventListener("change", loadAnomalies);
    if (btnRefreshAnomalies) btnRefreshAnomalies.addEventListener("click", loadAnomalies);

    // Auto-refresh anomalies every 10s if active
    setInterval(function () {
        if (tabAnomalies && tabAnomalies.style.display !== "none") {
            loadAnomalies();
        }
    }, 10000);
})();
