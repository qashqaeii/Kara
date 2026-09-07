(function () {
    "use strict";

    var CHART_ACCENT = "#2dd4bf";
    var CHART_MUTED = "#8b98ad";
    var CHART_GRID = "rgba(255,255,255,0.06)";
    var CHART_COPPER = "#d97706";
    var CURRENCY = (window.KaraDashboard && window.KaraDashboard.currencyUnit) || "تومان";

    function faNum(v) {
        try {
            return Number(v).toLocaleString("fa-IR");
        } catch (e) {
            return String(v);
        }
    }

    function moneyLabel(v) {
        return faNum(v) + " " + CURRENCY;
    }

    function chartDefaults() {
        if (!window.Chart) return;
        Chart.defaults.font.family = '"Vazirmatn", sans-serif';
        Chart.defaults.color = CHART_MUTED;
        Chart.defaults.animation.duration = 900;
        Chart.defaults.animation.easing = "easeOutQuart";
    }

    function readJson(id) {
        var el = document.getElementById(id);
        if (!el) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return null;
        }
    }

    function setText(id, text) {
        var el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function initTrendChart() {
        var data = readJson("tv-trend-data");
        var canvas = document.getElementById("tvTrendChart");
        if (!data || !canvas || !window.Chart) return;

        var values = data.map(function (d) { return Number(d.value) || 0; });
        var last = data[data.length - 1] || {};
        var peak = values.length ? Math.max.apply(null, values) : 0;
        var avg = values.length
            ? values.reduce(function (a, b) { return a + b; }, 0) / values.length
            : 0;

        setText("tvTrendLatest", moneyLabel(last.value || 0));
        setText("tvTrendPeak", moneyLabel(peak));
        setText("tvTrendAvg", moneyLabel(Math.round(avg)));
        setText("tvTrendPoints", faNum(data.length));

        var dense = data.length > 24;
        new Chart(canvas, {
            type: "line",
            data: {
                labels: data.map(function (d) { return d.date_label || d.date; }),
                datasets: [{
                    data: values,
                    borderColor: CHART_ACCENT,
                    backgroundColor: function (ctx) {
                        var chart = ctx.chart;
                        var area = chart.chartArea;
                        if (!area) return "rgba(45,212,191,0.08)";
                        var g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
                        g.addColorStop(0, "rgba(45,212,191,0.32)");
                        g.addColorStop(1, "rgba(45,212,191,0.02)");
                        return g;
                    },
                    fill: true,
                    tension: 0.38,
                    borderWidth: dense ? 2.2 : 3.2,
                    pointRadius: dense ? 0 : 4,
                    pointHoverRadius: 7,
                    pointBackgroundColor: CHART_ACCENT,
                    pointBorderColor: "#0c1520",
                    pointBorderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#121c2a",
                        titleColor: "#f2f6fb",
                        bodyColor: CHART_ACCENT,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            label: function (c) { return moneyLabel(c.raw); }
                        }
                    }
                },
                scales: {
                    y: {
                        ticks: { callback: faNum, color: CHART_MUTED, font: { size: 13 } },
                        grid: { color: CHART_GRID },
                        border: { display: false },
                    },
                    x: {
                        ticks: {
                            color: CHART_MUTED,
                            font: { size: 13 },
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: dense ? 10 : 12,
                        },
                        grid: { display: false },
                        border: { display: false },
                    }
                }
            }
        });
    }

    function initMonthlyChart() {
        var data = readJson("tv-monthly-data");
        var canvas = document.getElementById("tvMonthlyChart");
        if (!data || !canvas || !window.Chart) return;

        var max = Math.max.apply(null, data.map(function (m) { return m.value || 0; })) || 1;
        var best = data.slice().sort(function (a, b) {
            return (b.value || 0) - (a.value || 0);
        })[0];
        var current = null;
        for (var i = data.length - 1; i >= 0; i--) {
            if ((data[i].value || 0) > 0) {
                current = data[i];
                break;
            }
        }

        if (best) {
            setText("tvBestMonth", (best.label || "—") + " · " + moneyLabel(best.value || 0));
        }
        if (current) {
            setText("tvCurrentMonth", (current.label || "—") + " · " + moneyLabel(current.value || 0));
        }

        var colors = data.map(function (m) {
            var t = (m.value || 0) / max;
            if (best && m.key === best.key) return CHART_COPPER;
            return t > 0.85 ? CHART_ACCENT : (t > 0.5 ? "#0d9488" : "#134e4a");
        });

        new Chart(canvas, {
            type: "bar",
            data: {
                labels: data.map(function (m) { return m.label; }),
                datasets: [{
                    data: data.map(function (m) { return m.value; }),
                    backgroundColor: colors,
                    borderRadius: 10,
                    borderSkipped: false,
                    maxBarThickness: 52,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#121c2a",
                        bodyColor: CHART_ACCENT,
                        padding: 12,
                        displayColors: false,
                        callbacks: { label: function (c) { return moneyLabel(c.raw); } }
                    }
                },
                scales: {
                    y: {
                        ticks: { callback: faNum, color: CHART_MUTED, font: { size: 13 } },
                        grid: { color: CHART_GRID },
                        border: { display: false },
                    },
                    x: {
                        ticks: { color: CHART_MUTED, font: { size: 13 } },
                        grid: { display: false },
                        border: { display: false },
                    }
                }
            }
        });
    }

    function initBucketsChart() {
        var data = readJson("tv-buckets-data");
        var canvas = document.getElementById("tvBucketsChart");
        if (!data || !data.length || !canvas || !window.Chart) return;

        // Keep chronological month order M1..M12 when possible
        var sorted = data.slice().sort(function (a, b) {
            var ka = String(a.key || "");
            var kb = String(b.key || "");
            var na = parseInt(ka.replace(/\D/g, ""), 10) || 0;
            var nb = parseInt(kb.replace(/\D/g, ""), 10) || 0;
            return na - nb;
        });

        new Chart(canvas, {
            type: "bar",
            data: {
                labels: sorted.map(function (b) { return b.label; }),
                datasets: [{
                    data: sorted.map(function (b) { return b.amount; }),
                    backgroundColor: sorted.map(function (_, i) {
                        return i < 3 ? CHART_ACCENT : (i < 6 ? CHART_COPPER : "#f43f5e");
                    }),
                    borderRadius: 8,
                    borderSkipped: false,
                    maxBarThickness: 40,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#121c2a",
                        bodyColor: "#f2f6fb",
                        padding: 12,
                        displayColors: false,
                        callbacks: { label: function (c) { return moneyLabel(c.raw); } }
                    }
                },
                scales: {
                    y: {
                        ticks: { callback: faNum, color: CHART_MUTED, font: { size: 12 } },
                        grid: { color: CHART_GRID },
                        border: { display: false },
                    },
                    x: {
                        ticks: { color: CHART_MUTED, font: { size: 11 }, maxRotation: 0 },
                        grid: { display: false },
                        border: { display: false },
                    }
                }
            }
        });
    }

    var supervisorShareChart = null;

    function initSupervisorShareChart() {
        var data = readJson("tv-supervisor-share-data");
        var canvas = document.getElementById("tvSupervisorShareChart");
        if (!data || !data.length || !canvas || !window.Chart) return;

        var palette = [
            "#2dd4bf", "#d97706", "#94a3b8", "#a78bfa",
            "#38bdf8", "#fb7185", "#34d399", "#fbbf24"
        ];

        if (supervisorShareChart) {
            supervisorShareChart.destroy();
            supervisorShareChart = null;
        }

        supervisorShareChart = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: data.map(function (d) { return d.name; }),
                datasets: [{
                    data: data.map(function (d) { return d.value; }),
                    backgroundColor: data.map(function (_, i) { return palette[i % palette.length]; }),
                    borderColor: "#0c1520",
                    borderWidth: 3,
                    hoverOffset: 8,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#121c2a",
                        titleColor: "#f2f6fb",
                        bodyColor: CHART_ACCENT,
                        padding: 12,
                        displayColors: true,
                        callbacks: {
                            label: function (c) {
                                var share = data[c.dataIndex] && data[c.dataIndex].share;
                                var shareTxt = share != null ? " · " + faNum(share) + "٪" : "";
                                return moneyLabel(c.raw) + shareTxt;
                            }
                        }
                    }
                }
            }
        });
    }

    function resizeActiveCharts(slide) {
        if (!slide || !window.Chart) return;
        slide.querySelectorAll("canvas").forEach(function (canvas) {
            var chart = Chart.getChart(canvas);
            if (chart) chart.resize();
        });
    }

    function updateClock() {
        var el = document.getElementById("tvClock");
        if (!el) return;
        var now = new Date();
        el.textContent = now.toLocaleTimeString("fa-IR", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }

    function init() {
        var root = document.getElementById("tvRoot");
        if (!root) return;

        chartDefaults();
        initTrendChart();
        initMonthlyChart();
        initBucketsChart();
        initSupervisorShareChart();
        updateClock();
        setInterval(updateClock, 1000);

        var slides = Array.prototype.slice.call(root.querySelectorAll(".tv-slide"));
        var dotsContainer = document.getElementById("tvDots");
        var slideLabel = document.getElementById("tvSlideLabel");
        var pauseBtn = document.getElementById("tvPauseBtn");
        var fullscreenBtn = document.getElementById("tvFullscreenBtn");
        var progress = document.getElementById("tvProgress");
        var liveBadge = document.getElementById("tvLiveBadge");
        var intervalSec = parseInt(root.getAttribute("data-interval") || "20", 10);
        var refreshSec = parseInt(root.getAttribute("data-refresh") || "60", 10);
        var apiUrl = root.getAttribute("data-api-url");

        var current = 0;
        var paused = false;
        var rotateTimer = null;

        slides.forEach(function (slide, i) {
            var dot = document.createElement("button");
            dot.type = "button";
            dot.className = "tv-dot" + (i === 0 ? " active" : "");
            var label = slide.getAttribute("data-label") || ("اسلاید " + (i + 1));
            dot.setAttribute("aria-label", label);
            dot.title = label;
            dot.addEventListener("click", function () {
                goTo(i);
                resetRotate();
            });
            dotsContainer.appendChild(dot);
        });

        function dots() {
            return dotsContainer.querySelectorAll(".tv-dot");
        }

        function restartProgress() {
            if (!progress) return;
            progress.classList.remove("is-running", "is-paused");
            progress.style.animationDuration = "";
            void progress.offsetWidth;
            if (paused) {
                progress.classList.add("is-paused");
                return;
            }
            progress.style.animationDuration = intervalSec + "s";
            progress.classList.add("is-running");
        }

        function goTo(index) {
            current = ((index % slides.length) + slides.length) % slides.length;
            slides.forEach(function (s, i) {
                s.classList.toggle("active", i === current);
            });
            dots().forEach(function (d, i) {
                d.classList.toggle("active", i === current);
            });
            if (slideLabel) {
                var label = slides[current].getAttribute("data-label") || "";
                slideLabel.innerHTML =
                    "<strong>" + faNum(current + 1) + "</strong> / " + faNum(slides.length) +
                    (label ? " · " + label : "");
            }
            restartProgress();
            // Allow layout paint before chart resize
            requestAnimationFrame(function () {
                resizeActiveCharts(slides[current]);
            });
        }

        function next() {
            if (!paused) goTo(current + 1);
        }

        function prev() {
            goTo(current - 1);
            resetRotate();
        }

        function resetRotate() {
            if (rotateTimer) clearInterval(rotateTimer);
            rotateTimer = setInterval(next, intervalSec * 1000);
            restartProgress();
        }

        function togglePause() {
            paused = !paused;
            if (pauseBtn) {
                pauseBtn.innerHTML = paused
                    ? '<i class="bi bi-play-fill"></i>'
                    : '<i class="bi bi-pause-fill"></i>';
                pauseBtn.classList.toggle("is-paused", paused);
            }
            if (progress) {
                progress.classList.toggle("is-paused", paused);
            }
            if (liveBadge) {
                liveBadge.classList.toggle("is-paused", paused);
                var label = liveBadge.querySelector(".tv-live-text");
                if (label) label.textContent = paused ? "توقف" : "زنده";
            }
        }

        if (pauseBtn) {
            pauseBtn.addEventListener("click", togglePause);
        }

        if (fullscreenBtn) {
            fullscreenBtn.addEventListener("click", function () {
                if (!document.fullscreenElement) {
                    document.documentElement.requestFullscreen();
                } else {
                    document.exitFullscreen();
                }
            });
        }

        document.addEventListener("keydown", function (e) {
            if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
                e.preventDefault();
                if (e.key === "ArrowLeft") goTo(current + 1);
                else prev();
                resetRotate();
            } else if (e.key === " " || e.code === "Space") {
                e.preventDefault();
                togglePause();
            } else if (e.key === "f" || e.key === "F") {
                if (fullscreenBtn) fullscreenBtn.click();
            }
        });

        function refreshData() {
            if (!apiUrl) return;
            fetch(apiUrl, { headers: { Accept: "application/json" } })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var syncEl = document.getElementById("tvSyncLabel");
                    if (syncEl && data.connection) {
                        syncEl.textContent = "به‌روزرسانی: " + data.connection.last_sync_label;
                    }
                    var connEl = document.getElementById("tvConnStatus");
                    if (connEl && data.connection) {
                        connEl.className = "tv-conn status-" + (data.connection.status || "");
                        connEl.textContent = data.connection.status_label || data.connection.status || "";
                    }
                })
                .catch(function () { /* silent */ });
        }

        goTo(0);
        resetRotate();
        setInterval(refreshData, refreshSec * 1000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
