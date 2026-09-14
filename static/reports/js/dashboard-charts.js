/* Dashboard Chart.js — unified KARA theme, RTL-safe sizing */

(function () {
    "use strict";

    var T = window.KaraChartTheme || {};
    var TEAL = T.primary || "#0f766e";
    var MUTED = T.muted || "#94a3b8";
    var GRID = (T.colors && T.colors.grid) || "rgba(12,18,34,0.05)";
    var PALETTE = T.palette || ["#0f766e", "#0d9488", "#14b8a6", "#b45309", "#d97706", "#64748b"];
    var faNum = T.faNum || function (v) { return String(v); };
    var moneyLabel = T.moneyLabel || function (v) { return String(v); };

    function readJson(id) {
        var el = document.getElementById(id);
        if (!el) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return null;
        }
    }

    function ensureSize(canvas, minH) {
        var frame = canvas.parentElement;
        if (!frame) return;
        if (frame.clientHeight < 40) {
            frame.style.minHeight = (minH || 280) + "px";
            frame.style.height = (minH || 280) + "px";
        }
    }

    function destroy(canvas) {
        if (!window.Chart || !canvas) return;
        var existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
    }

    function markFailed(canvas) {
        var frame = canvas && canvas.closest(".db-chart-frame");
        if (frame) frame.classList.add("is-failed");
    }

    function scaleY(money) {
        if (T.scaleY) return T.scaleY({ money: money });
        return {
            beginAtZero: true,
            ticks: { callback: faNum, color: MUTED, font: { size: 10 }, maxTicksLimit: 6 },
            grid: { color: GRID },
            border: { display: false },
        };
    }

    function scaleX() {
        if (T.scaleX) return T.scaleX();
        return {
            ticks: { color: MUTED, font: { size: 10 }, maxRotation: 0 },
            grid: { display: false },
            border: { display: false },
        };
    }

    function chartMoney(row) {
        if (row == null) return 0;
        if (row.value != null && row.value !== "") return Number(row.value) || 0;
        return Number(row.pure_sale != null ? row.pure_sale : row.amount) || 0;
    }

    function trendChart() {
        var canvas = document.getElementById("dashboardTrend");
        var data = readJson("dashboard-trend-data");
        if (!canvas || !data || !data.length || !window.Chart) {
            if (canvas) markFailed(canvas);
            return;
        }
        destroy(canvas);
        ensureSize(canvas, 300);
        try {
            var chart = new Chart(canvas.getContext("2d"), {
                type: "line",
                data: {
                    labels: data.map(function (d) { return d.date_label || d.date; }),
                    datasets: [T.lineDataset ? T.lineDataset(data.map(function (d) { return Number(d.value) || 0; })) : {
                        data: data.map(function (d) { return Number(d.value) || 0; }),
                        borderColor: TEAL,
                        backgroundColor: "rgba(15,118,110,0.1)",
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2,
                        pointRadius: 2.5,
                        pointHoverRadius: 4,
                        pointBackgroundColor: TEAL,
                        pointBorderColor: "#fff",
                        pointBorderWidth: 1.5,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: function (c) { return moneyLabel(c.raw); } } },
                    },
                    scales: { y: scaleY(true), x: scaleX() },
                },
            });
            setTimeout(function () { try { chart.resize(); } catch (e) {} }, 80);
        } catch (e) {
            markFailed(canvas);
        }
    }

    function monthlyChart() {
        var canvas = document.getElementById("dashboardMonthly");
        var data = readJson("dashboard-monthly-data");
        if (!canvas || !data || !data.length || !window.Chart) {
            if (canvas) markFailed(canvas);
            return;
        }
        destroy(canvas);
        ensureSize(canvas, 300);
        try {
            var chart = new Chart(canvas.getContext("2d"), {
                type: "bar",
                data: {
                    labels: data.map(function (m) { return m.label; }),
                    datasets: [T.barDataset ? T.barDataset(data.map(function (m) { return Number(m.value) || 0; })) : {
                        data: data.map(function (m) { return Number(m.value) || 0; }),
                        backgroundColor: TEAL,
                        borderRadius: 5,
                        borderSkipped: false,
                        maxBarThickness: 32,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: function (c) { return moneyLabel(c.raw); } } },
                    },
                    scales: { y: scaleY(true), x: scaleX() },
                },
            });
            setTimeout(function () { try { chart.resize(); } catch (e) {} }, 80);
        } catch (e) {
            markFailed(canvas);
        }
    }

    function groupsChart() {
        var canvas = document.getElementById("dashboardGroups");
        var data = readJson("dashboard-groups-data");
        if (!canvas || !data || !data.length || !window.Chart) {
            if (canvas) markFailed(canvas);
            return;
        }
        destroy(canvas);
        ensureSize(canvas, 220);
        try {
            var colors = T.doughnutColors ? T.doughnutColors(data.length) : data.map(function (_, i) { return PALETTE[i % PALETTE.length]; });
            var chart = new Chart(canvas.getContext("2d"), {
                type: "doughnut",
                data: {
                    labels: data.map(function (g) { return g.name; }),
                    datasets: [{
                        data: data.map(chartMoney),
                        backgroundColor: colors,
                        borderWidth: 2,
                        borderColor: "#fff",
                        hoverOffset: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "62%",
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function (c) {
                                    return " " + (c.label || "") + ": " + moneyLabel(c.raw).trim();
                                },
                            },
                        },
                    },
                },
            });
            setTimeout(function () { try { chart.resize(); } catch (e) {} }, 80);
        } catch (e) {
            markFailed(canvas);
        }
    }

    function boot() {
        trendChart();
        monthlyChart();
        groupsChart();
    }

    window.KaraDashboardCharts = {
        init: function () {
            if (T.applyDefaults) T.applyDefaults();
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    boot();
                    setTimeout(boot, 150);
                });
            });
        },
    };
})();
