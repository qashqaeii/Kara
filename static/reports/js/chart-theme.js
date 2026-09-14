/**
 * KARA — unified Chart.js theme (RTL-safe, enterprise analytics).
 */
(function () {
    "use strict";

    var root = document.documentElement;
    var cs = root && getComputedStyle(root);

    function token(name, fallback) {
        if (!cs) return fallback;
        var v = cs.getPropertyValue(name).trim();
        return v || fallback;
    }

    var THEME = {
        primary: token("--kara-chart", "#0f766e"),
        primarySoft: token("--kara-primary-soft", "rgba(15,118,110,0.12)"),
        muted: token("--kara-chart-muted", "#94a3b8"),
        grid: token("--kara-chart-grid", "rgba(12,18,34,0.05)"),
        text: token("--kara-text-muted", "#6b7485"),
        surface: token("--kara-surface", "#ffffff"),
        warning: token("--kara-warning", "#b45309"),
        danger: token("--kara-danger", "#b91c1c"),
        palette: [
            token("--kara-chart", "#0f766e"),
            token("--kara-accent-2", "#0d9488"),
            "#14b8a6",
            token("--kara-warning", "#b45309"),
            "#d97706",
            "#64748b",
            "#334155",
            token("--kara-primary", "#0b3d3a"),
        ],
        fontFamily: token("--kara-font-body", '"Vazirmatn", sans-serif'),
        fontDisplay: token("--kara-font-display", '"IBM Plex Sans Arabic", "Vazirmatn", sans-serif'),
        animationMs: 200,
    };

    function faNum(v) {
        try {
            return Number(v).toLocaleString("fa-IR");
        } catch (e) {
            return String(v);
        }
    }

    function compactAxis(v) {
        var n = Number(v);
        if (!isFinite(n)) return String(v);
        var abs = Math.abs(n);
        if (abs >= 1e9) return faNum(Math.round(n / 1e8) / 10) + "B";
        if (abs >= 1e6) return faNum(Math.round(n / 1e5) / 10) + "M";
        if (abs >= 1e4) return faNum(Math.round(n / 1e3)) + "K";
        return faNum(n);
    }

    function currencyUnit() {
        return (window.KaraDashboard && window.KaraDashboard.currencyUnit) || "تومان";
    }

    function moneyLabel(v) {
        return " " + faNum(v) + " " + currencyUnit();
    }

    function applyDefaults() {
        if (!window.Chart) return;
        Chart.defaults.font.family = THEME.fontFamily;
        Chart.defaults.font.size = 11;
        Chart.defaults.color = THEME.text;
        Chart.defaults.animation.duration = THEME.animationMs;
        Chart.defaults.plugins.tooltip.backgroundColor = THEME.surface;
        Chart.defaults.plugins.tooltip.titleColor = token("--kara-text", "#0c1222");
        Chart.defaults.plugins.tooltip.bodyColor = THEME.text;
        Chart.defaults.plugins.tooltip.borderColor = token("--kara-border-strong", "rgba(12,18,34,0.12)");
        Chart.defaults.plugins.tooltip.borderWidth = 1;
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.plugins.tooltip.cornerRadius = 10;
        Chart.defaults.plugins.tooltip.displayColors = true;
        Chart.defaults.plugins.tooltip.boxPadding = 4;
        Chart.defaults.plugins.legend.labels.usePointStyle = true;
        Chart.defaults.plugins.legend.labels.pointStyle = "circle";
        Chart.defaults.plugins.legend.labels.padding = 14;
        Chart.defaults.plugins.legend.labels.font = { size: 11, weight: "600" };
    }

    function scaleY(opts) {
        opts = opts || {};
        var tickFn = opts.money ? compactAxis : faNum;
        return {
            beginAtZero: opts.beginAtZero !== false,
            ticks: {
                callback: tickFn,
                color: THEME.muted,
                font: { size: 10 },
                maxTicksLimit: 6,
            },
            grid: { color: THEME.grid, drawBorder: false },
            border: { display: false },
        };
    }

    function scaleX(opts) {
        opts = opts || {};
        return {
            ticks: {
                color: THEME.muted,
                font: { size: 10 },
                maxRotation: opts.maxRotation || 0,
            },
            grid: { display: false },
            border: { display: false },
        };
    }

    function lineDataset(data, overrides) {
        var ds = {
            data: data,
            borderColor: THEME.primary,
            backgroundColor: THEME.primarySoft,
            fill: true,
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 2.5,
            pointHoverRadius: 4,
            pointBackgroundColor: THEME.primary,
            pointBorderColor: THEME.surface,
            pointBorderWidth: 1.5,
        };
        if (overrides) {
            Object.keys(overrides).forEach(function (k) { ds[k] = overrides[k]; });
        }
        return ds;
    }

    function barDataset(data, overrides) {
        var ds = {
            data: data,
            backgroundColor: THEME.primary,
            borderRadius: 5,
            borderSkipped: false,
            maxBarThickness: 32,
        };
        if (overrides) {
            Object.keys(overrides).forEach(function (k) { ds[k] = overrides[k]; });
        }
        return ds;
    }

    function doughnutColors(count) {
        var out = [];
        for (var i = 0; i < count; i++) {
            out.push(THEME.palette[i % THEME.palette.length]);
        }
        return out;
    }

    function baseOptions(type) {
        var opts = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { display: type === "doughnut" },
            },
        };
        if (type === "line" || type === "bar") {
            opts.scales = { y: scaleY(), x: scaleX() };
        }
        return opts;
    }

    applyDefaults();

    window.KaraChartTheme = {
        colors: THEME,
        faNum: faNum,
        compactAxis: compactAxis,
        moneyLabel: moneyLabel,
        currencyUnit: currencyUnit,
        applyDefaults: applyDefaults,
        scaleY: scaleY,
        scaleX: scaleX,
        lineDataset: lineDataset,
        barDataset: barDataset,
        doughnutColors: doughnutColors,
        baseOptions: baseOptions,
        palette: THEME.palette,
        primary: THEME.primary,
        muted: THEME.muted,
        grid: THEME.grid,
    };
})();
