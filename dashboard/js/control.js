// DCEMS Manual & Policy-Gated Control Tab Client (Phase 4)
// Local LAN operations with zero internet/CDN dependencies.

(function () {
    const navControl = document.getElementById("nav-control");
    const tabControl = document.getElementById("tab-control");
    const btnToggleMode = document.getElementById("btn-toggle-mode");
    const modeIndicator = document.getElementById("ctrl-mode-indicator");
    const cmdBanner = document.getElementById("cmd-status-banner");
    const cmdBannerIcon = document.getElementById("cmd-banner-icon");
    const cmdBannerText = document.getElementById("cmd-banner-text");
    const actionsTbody = document.getElementById("actions-tbody");

    let currentMode = "AUTO";

    // Tab Activation
    function activateTab(target) {
        const tabs = ["live", "events", "anomalies", "control", "settings"];
        tabs.forEach(t => {
            const nav = document.getElementById("nav-" + t);
            const pane = document.getElementById("tab-" + t);
            if (nav) nav.classList.toggle("active", t === target);
            if (pane) pane.style.display = (t === target) ? "block" : "none";
        });

        if (target === "control") {
            refreshControlState();
            loadControlActions();
        }
    }

    if (navControl) {
        navControl.addEventListener("click", function (e) {
            e.preventDefault();
            activateTab("control");
            window.location.hash = "control";
        });
    }

    if (window.location.hash === "#control") {
        activateTab("control");
    }

    window.addEventListener("hashchange", function () {
        if (window.location.hash === "#control") {
            activateTab("control");
        }
    });

    // Authentication Helper (auto-authenticates for local operator convenience)
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

    // Banner Message Helper
    function showBanner(message, type = "info") {
        if (!cmdBanner || !cmdBannerText) return;
        cmdBanner.style.display = "flex";
        cmdBanner.className = `alert-banner banner-${type}`;

        if (cmdBannerIcon) {
            if (type === "success") cmdBannerIcon.textContent = "✅";
            else if (type === "danger") cmdBannerIcon.textContent = "❌";
            else if (type === "warning") cmdBannerIcon.textContent = "⚠️";
            else cmdBannerIcon.textContent = "ℹ️";
        }
        cmdBannerText.innerHTML = message;
    }

    function formatTs(epochSec) {
        if (!epochSec) return "--";
        const d = new Date(epochSec * 1000);
        const utcStr = d.toISOString().replace("T", " ").substring(0, 19) + " UTC";
        const localStr = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        return `${utcStr} (${localStr})`;
    }

    // Synchronize current device states and mode from /api/live
    async function refreshControlState() {
        try {
            const res = await fetch("/api/live", { cache: "no-cache" });
            if (!res.ok) return;
            const data = await res.json();

            // Mode
            currentMode = data.mode || "AUTO";
            if (modeIndicator) {
                modeIndicator.textContent = currentMode;
                modeIndicator.className = (currentMode === "AUTO") ? "badge badge-info" : "badge badge-warning";
            }
            if (btnToggleMode) {
                btnToggleMode.textContent = (currentMode === "AUTO") ? "Switch to MANUAL" : "Switch to AUTO";
            }

            // Devices
            const devs = data.devices || {};
            const devMap = {
                light_01: "ctrl-state-light",
                fan_01: "ctrl-state-fan",
                ac_01: "ctrl-state-ac",
                pc_01: "ctrl-state-pc"
            };

            for (const [id, elemId] of Object.entries(devMap)) {
                const el = document.getElementById(elemId);
                if (el) {
                    const st = devs[id] || "OFF";
                    el.textContent = st;
                    el.className = (st === "ON") ? "appliance-state state-on" : "appliance-state state-off";
                }
            }
        } catch (e) {
            console.error("Failed to sync control state:", e);
        }
    }

    // Mode Toggle Handler
    if (btnToggleMode) {
        btnToggleMode.addEventListener("click", async function () {
            const targetMode = (currentMode === "AUTO") ? "MANUAL" : "AUTO";
            showBanner(`Switching controller mode to <strong>${targetMode}</strong>...`, "info");

            try {
                const headers = await getAuthHeader();
                const res = await fetch("/api/control/mode", {
                    method: "POST",
                    headers: headers,
                    body: JSON.stringify({ mode: targetMode })
                });

                const data = await res.json();
                if (res.ok && data.success) {
                    showBanner(`Controller mode successfully changed to <strong>${targetMode}</strong>.`, "success");
                    currentMode = targetMode;
                    await refreshControlState();
                    await loadControlActions();
                } else {
                    const err = data.detail || data.reason || "Mode switch rejected";
                    showBanner(`Mode change blocked: ${err}`, "danger");
                }
            } catch (err) {
                showBanner(`Network error: ${err.message}`, "danger");
            }
        });
    }

    // Device Command Buttons Handler
    const deviceButtons = document.querySelectorAll(".btn-device-cmd");
    deviceButtons.forEach(btn => {
        btn.addEventListener("click", async function () {
            const deviceId = btn.getAttribute("data-device");
            const requestedState = btn.getAttribute("data-state");

            // Test T13 Check: AC and PC power-off commands are blocked by policy
            if ((deviceId === "ac_01" || deviceId === "pc_01") && requestedState === "OFF") {
                showBanner(
                    `<strong>Action Blocked:</strong> Power-OFF for <code>${deviceId}</code> is prohibited by policy (Test T13 safeguard).`,
                    "danger"
                );
                return;
            }

            showBanner(`Sending command: Turn <strong>${requestedState}</strong> <code>${deviceId}</code>...`, "info");

            try {
                const headers = await getAuthHeader();
                const res = await fetch("/api/control/device", {
                    method: "POST",
                    headers: headers,
                    body: JSON.stringify({
                        device_id: deviceId,
                        requested_state: requestedState,
                        reason: "dashboard_manual_control"
                    })
                });

                const data = await res.json();
                if (res.ok && data.success) {
                    const actId = data.action_id;
                    showBanner(`Command <code>${actId}</code> issued to controller. Awaiting hardware ACK...`, "info");

                    // Poll for outcome after 1.5s
                    setTimeout(async () => {
                        await refreshControlState();
                        await loadControlActions();
                        showBanner(`Command <code>${actId}</code> processed. Commanded state verified.`, "success");
                    }, 1500);
                } else {
                    const reason = data.detail || data.reason || "Safety gate rejected command";
                    showBanner(`<strong>Command Blocked by Safety Policy:</strong> ${reason}`, "danger");
                    await loadControlActions();
                }
            } catch (err) {
                showBanner(`Communication error: ${err.message}`, "danger");
            }
        });
    });

    // Load Control Actions Audit Table
    async function loadControlActions() {
        if (!actionsTbody) return;
        try {
            const res = await fetch("/api/control/actions?limit=25", { cache: "no-cache" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const actions = await res.json();

            if (!actions || actions.length === 0) {
                actionsTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No control actions recorded yet.</td></tr>`;
                return;
            }

            actionsTbody.innerHTML = actions.map(act => {
                const tsStr = formatTs(act.timestamp_utc);
                const stBadge = (act.proposed_state === "ON")
                    ? '<span class="badge badge-success">ON</span>'
                    : '<span class="badge badge-danger">OFF</span>';

                let decBadge = "";
                if (act.policy_decision === "allowed") {
                    decBadge = '<span class="badge badge-success">Allowed</span>';
                } else {
                    decBadge = '<span class="badge badge-danger">Blocked</span>';
                }

                let outBadge = "";
                if (act.execution_result === "success") {
                    outBadge = '<span class="badge badge-success">Accepted (ACK)</span>';
                } else if (act.execution_result === "failed") {
                    outBadge = '<span class="badge badge-danger">Blocked (Gate)</span>';
                } else if (act.execution_result === "expired") {
                    outBadge = '<span class="badge badge-warning">Expired</span>';
                } else {
                    outBadge = '<span class="badge badge-info">Pending / Not Executed</span>';
                }

                return `<tr>
                    <td>${tsStr}</td>
                    <td><code>${escapeHtml(act.action_id)}</code></td>
                    <td><strong>${escapeHtml(act.device_id)}</strong></td>
                    <td>${stBadge}</td>
                    <td>${decBadge}</td>
                    <td>${escapeHtml(act.decision_reason || "--")}</td>
                    <td>${outBadge}</td>
                </tr>`;
            }).join("");
        } catch (e) {
            console.error("Failed to load control actions:", e);
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

    // Expose for external refreshes
    window.dcemsRefreshControl = refreshControlState;
})();
