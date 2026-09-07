/**
 * Live dashboard auto-refresh and polling.
 */
const KaraLiveDashboard = (function () {
    let config = {};
    let countdownSeconds = 0;
    let countdownTimer = null;
    let pollTimer = null;
    let isRefreshing = false;

    function getCsrfToken() {
        return config.csrfToken || "";
    }

    function currentPeriod() {
        if (config.period) return config.period;
        const params = new URLSearchParams(window.location.search);
        return params.get("period") || "all";
    }

    function dashboardUrl() {
        const base = config.apiUrl || "";
        const period = currentPeriod();
        const sep = base.includes("?") ? "&" : "?";
        return `${base}${sep}period=${encodeURIComponent(period)}`;
    }

    function formatCountdown(seconds) {
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    function updateCountdownDisplay() {
        const el = document.getElementById("countdownText");
        if (el) el.textContent = formatCountdown(countdownSeconds);
    }

    function startCountdown() {
        countdownSeconds = (config.intervalMinutes || 5) * 60;
        updateCountdownDisplay();
        if (countdownTimer) clearInterval(countdownTimer);
        countdownTimer = setInterval(() => {
            countdownSeconds = Math.max(0, countdownSeconds - 1);
            updateCountdownDisplay();
            if (countdownSeconds === 0) {
                fetchDashboard();
                countdownSeconds = (config.intervalMinutes || 5) * 60;
            }
        }, 1000);
    }

    function setLiveStatus(text, state) {
        const textEl = document.getElementById("liveStatusText");
        const dot = document.querySelector(".live-dot");
        if (textEl) textEl.textContent = text;
        if (dot) {
            dot.classList.remove("refreshing", "error");
            if (state) dot.classList.add(state);
        }
    }

    function updateDashboardUI(data) {
        if (!data) return;

        const agg = data.aggregate_kpis || data.company_kpis || {};
        Object.entries(agg).forEach(([key, kpi]) => {
            const el = document.querySelector(`[data-kpi="${key}"]`);
            if (el && kpi && kpi.formatted != null) el.textContent = kpi.formatted;
        });

        (data.reports || []).forEach((report) => {
            const card = document.querySelector(`[data-report-key="${report.key}"]`);
            if (!card) return;

            const fetchedEl = card.querySelector(".fetched-at");
            const rowsEl = card.querySelector(".rows-count");
            const pill = card.querySelector(".status-pill");

            if (fetchedEl) fetchedEl.textContent = report.fetched_at_display || "—";
            if (rowsEl) rowsEl.textContent = report.has_data ? `${report.rows_count} ردیف` : "—";
            if (pill) {
                const ready = report.has_data;
                pill.innerHTML = `<span class="status-dot"></span>${ready ? "آماده" : "بدون داده"}`;
                pill.className = `status-pill ${ready ? "is-ready" : "is-idle"}`;
            }

            Object.entries(report.kpis || {}).forEach(([key, kpi]) => {
                const mini = card.querySelector(`[data-mini-kpi="${key}"]`);
                if (mini) mini.textContent = kpi.formatted;
            });

            const topList = card.querySelector(".top-performers-list");
            if (topList && report.top_performers) {
                if (!report.top_performers.length) {
                    topList.innerHTML = '<li class="leaderboard-item"><span class="text-muted small">داده‌ای نیست</span></li>';
                } else {
                    topList.innerHTML = report.top_performers.map((p) => `
                        <li class="leaderboard-item rank-${p.rank}">
                            <div class="rank-badge">${p.rank}</div>
                            <div class="leader-info">
                                <strong class="top-name">${p.name}</strong>
                                <span class="top-code">${p.code}</span>
                            </div>
                            <div class="leader-stat">
                                <strong class="top-sale">${p.total_sale_formatted}</strong>
                            </div>
                        </li>
                    `).join("");
                }
            }
        });

        const status = data.refresh_status || data.connection || {};
        const conn = data.connection || {};
        if (status.status === "running" || status.status === "syncing") {
            setLiveStatus("در حال همگام‌سازی...", "refreshing");
        } else if (status.status === "error" || status.status === "failed" || conn.status === "network_error") {
            setLiveStatus(conn.status_label || "خطا در همگام‌سازی", "error");
        } else if (status.last_refresh_display || conn.last_sync_label) {
            setLiveStatus(`به‌روزرسانی: ${status.last_refresh_display || conn.last_sync_label}`);
        } else {
            setLiveStatus("آماده");
        }
    }

    async function fetchDashboard() {
        try {
            const resp = await fetch(dashboardUrl());
            if (!resp.ok) throw new Error("API error");
            const data = await resp.json();
            updateDashboardUI(data);
            return data;
        } catch (err) {
            setLiveStatus("خطا در اتصال", "error");
            return null;
        }
    }

    async function triggerRefresh() {
        if (isRefreshing) return;
        isRefreshing = true;

        const alertEl = document.getElementById("refreshAlert");
        const btn = document.getElementById("btnRefreshAll");
        if (alertEl) alertEl.classList.remove("d-none");
        if (btn) btn.disabled = true;
        setLiveStatus("در حال بروزرسانی...", "refreshing");

        try {
            const resp = await fetch(config.refreshUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                    "Content-Type": "application/json",
                },
            });
            const result = await resp.json();
            if (!result.success) {
                setLiveStatus("خطا: " + (result.error || "نامشخص"), "error");
            }
        } catch (err) {
            setLiveStatus("خطا در بروزرسانی", "error");
        }

        await fetchDashboard();
        startCountdown();

        if (alertEl) alertEl.classList.add("d-none");
        if (btn) btn.disabled = false;
        isRefreshing = false;
    }

    function startPolling() {
        const pollInterval = 30000;
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(fetchDashboard, pollInterval);
    }

    function init(cfg) {
        config = cfg || {};
        startCountdown();
        fetchDashboard();
        startPolling();

        const btn = document.getElementById("btnRefreshAll");
        if (btn) {
            btn.addEventListener("click", triggerRefresh);
        }
    }

    return { init, fetchDashboard, triggerRefresh };
})();

window.KaraLiveDashboard = KaraLiveDashboard;
