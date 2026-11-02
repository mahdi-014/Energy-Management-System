// DCEMS Analysis & Profiling Tab Client (Phase 5)
// Zero external internet dependencies; renders offline via local vendored Chart.js.

(function () {
    const navAnalysis = document.getElementById("nav-analysis");
    const tabAnalysis = document.getElementById("tab-analysis");
    const dateInput = document.getElementById("analysis-date-input");
    const btnRefresh = document.getElementById("btn-refresh-analysis");
    const btnToggleBaseline = document.getElementById("btn-toggle-baseline");
    const baselineBadge = document.getElementById("baseline-feature-badge");
    const baselineCardsGrid = document.getElementById("baseline-cards-grid");
    const chartTotalEl = document.getElementById("analysis-chart-total");

    let hourlyChartInstance = null;
    let baselineFlagEnabled = false;

    // Tab Activation
    function activateTab(target) {
        const tabs = ["live", "events", "anomalies", "control", "settings", "analysis"];
        tabs.forEach(t => {
            const nav = document.getElementById("nav-" + t);
            const pane = document.getElementById("tab-" + t);
            if (nav) nav.classList.toggle("active", t === target);
            if (pane) pane.style.display = (t === target) ? "block" : "none";
        });

        if (target === "analysis") {
            loadAnalysisData();
        }
    }

    if (navAnalysis) {
        navAnalysis.addEventListener("click", function (e) {
            e.preventDefault();
            activateTab("analysis");
            window.location.hash = "analysis";
        });
    }

    if (window.location.hash === "#analysis") {
        activateTab("analysis");
    }

    window.addEventListener("hashchange", function () {
        if (window.location.hash === "#analysis") {
            activateTab("analysis");
        }
    });

    // Default Date to Today Local (YYYY-MM-DD)
    if (dateInput && !dateInput.value) {
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, "0");
        const dd = String(today.getDate()).padStart(2, "0");
        dateInput.value = `${yyyy}-${mm}-${dd}`;
    }

    if (btnRefresh) {
        btnRefresh.addEventListener("click", loadAnalysisData);
    }
    if (dateInput) {
        dateInput.addEventListener("change", loadAnalysisData);
    }

    // Authentication Helper
    async function getAuthHeader() {
        let token = localStorage.getItem("dcems_token");
        if (token) {
            return { "Authorization": "Bearer " + token, "Content-Type": "application/json" };
        }
        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: "admin", password: "admin123" })
            });
            if (res.ok) {
                const data = await res.json();
                token = data.access_token;
                localStorage.setItem("dcems_token", token);
                return { "Authorization": "Bearer " + token, "Content-Type": "application/json" };
            }
        } catch (e) {
            console.warn("Auto-login failed:", e);
        }
        return { "Content-Type": "application/json" };
    }

    // Toggle Adaptive Baseline Feature Flag
    if (btnToggleBaseline) {
        btnToggleBaseline.addEventListener("click", async function () {
            const targetState = !baselineFlagEnabled;
            try {
                const headers = await getAuthHeader();
                const res = await fetch("/api/settings/baseline-flag", {
                    method: "POST",
                    headers: headers,
                    body: JSON.stringify({ enabled: targetState })
                });
                if (res.ok) {
                    await loadBaselineData();
                }
            } catch (err) {
                console.error("Failed to toggle baseline flag:", err);
            }
        });
    }

    async function loadAnalysisData() {
        await Promise.all([
            loadHourlyHistogram(),
            loadBaselineData()
        ]);
    }

    // Load Hourly Runtime Histogram
    async function loadHourlyHistogram() {
        const targetDate = dateInput ? dateInput.value : "";
        try {
            const url = targetDate ? `/api/analysis/hourly?date=${targetDate}` : "/api/analysis/hourly";
            const res = await fetch(url, { cache: "no-cache" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            renderHourlyChart(data);
        } catch (err) {
            console.error("Failed to load hourly runtime distribution:", err);
        }
    }

    function renderHourlyChart(data) {
        const canvas = document.getElementById("hourly-usage-chart");
        if (!canvas) return;

        const hours = data.hours || [];
        const devs = data.devices || {};

        const datasets = [
            {
                label: "light_01",
                data: devs.light_01 || [],
                backgroundColor: "#fbbf24"
            },
            {
                label: "fan_01",
                data: devs.fan_01 || [],
                backgroundColor: "#38bdf8"
            },
            {
                label: "ac_01",
                data: devs.ac_01 || [],
                backgroundColor: "#a855f7"
            },
            {
                label: "pc_01",
                data: devs.pc_01 || [],
                backgroundColor: "#34d399"
            }
        ];

        if (hourlyChartInstance) {
            hourlyChartInstance.destroy();
        }

        hourlyChartInstance = new Chart(canvas, {
            type: "bar",
            data: {
                labels: hours,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { stacked: true },
                    y: { stacked: true }
                }
            }
        });

        if (chartTotalEl) {
            const totals = data.total_runtime_minutes || {};
            let sumMin = 0;
            for (const v of Object.values(totals)) sumMin += Number(v) || 0;
            const hrs = (sumMin / 60.0).toFixed(1);
            chartTotalEl.textContent = `Total active commanded runtime: ${hrs} hrs (${sumMin.toFixed(0)} mins)`;
        }
    }

    // Load Adaptive Baseline Stats
    async function loadBaselineData() {
        if (!baselineCardsGrid) return;
        try {
            const res = await fetch("/api/analysis/baseline", { cache: "no-cache" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            baselineFlagEnabled = !!data.feature_flag_enabled;

            if (baselineBadge) {
                if (baselineFlagEnabled) {
                    baselineBadge.className = "badge badge-success";
                    baselineBadge.textContent = "Feature Flag: Enabled";
                } else {
                    baselineBadge.className = "badge badge-warning";
                    baselineBadge.textContent = "Feature Flag: Disabled (Default)";
                }
            }

            if (btnToggleBaseline) {
                btnToggleBaseline.textContent = baselineFlagEnabled ? "Disable Feature Flag" : "Enable Feature Flag";
            }

            const devs = data.devices || {};
            const devKeys = ["light_01", "fan_01", "ac_01", "pc_01"];

            baselineCardsGrid.innerHTML = devKeys.map(k => {
                const b = devs[k] || {};
                let statusBadge = "";
                let bodyHtml = "";

                if (!baselineFlagEnabled || b.status === "disabled") {
                    statusBadge = '<span class="badge badge-info">Disabled (Default)</span>';
                    bodyHtml = `
                        <div class="card-value" style="font-size: 1.1rem; color: var(--text-muted);">Inactive</div>
                        <div class="card-footer">Feature flag currently OFF. No baseline evaluated.</div>
                    `;
                } else if (b.status === "insufficient_data") {
                    statusBadge = '<span class="badge badge-warning">Insufficient Sessions</span>';
                    bodyHtml = `
                        <div class="card-value" style="font-size: 1.1rem;">${b.completed_sessions_count || 0} / 20</div>
                        <div class="card-footer">Need &ge; 20 completed sessions for baseline stability.</div>
                    `;
                } else if (b.status === "active") {
                    statusBadge = '<span class="badge badge-success">Active & Calibrated</span>';
                    bodyHtml = `
                        <div style="margin: 0.75rem 0;">
                            <div style="font-size: 0.85rem; color: var(--text-secondary);">Median Duration: <strong>${b.median_min} min</strong></div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary);">MAD Dispersion: <strong>${(b.mad_sec / 60.0).toFixed(1)} min</strong></div>
                            <div style="font-size: 0.9rem; color: var(--color-danger); margin-top: 0.5rem;">
                                Anomaly Cutoff: <strong>${b.upper_threshold_min} min</strong>
                            </div>
                        </div>
                        <div class="card-footer">${b.completed_sessions_count} sessions analyzed via Median + MAD.</div>
                    `;
                } else {
                    statusBadge = '<span class="badge badge-info">Idle</span>';
                    bodyHtml = `<div class="card-footer">No historical sessions recorded.</div>`;
                }

                return `
                    <div class="card">
                        <div class="card-header-flex">
                            <div class="card-title">${escapeHtml(k)}</div>
                            ${statusBadge}
                        </div>
                        ${bodyHtml}
                    </div>
                `;
            }).join("");
        } catch (err) {
            console.error("Failed to load baseline data:", err);
        }
    }

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    window.dcemsRefreshAnalysis = loadAnalysisData;
})();

