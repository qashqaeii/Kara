/* Salesperson detail page charts and history filter. */

(function () {
    "use strict";

    var ACCENT = "#0f766e";
    var COPPER = "#b45309";
    var DANGER = "#b91c1c";
    var MUTED = "#94a3b8";
    var GRID = "rgba(12,18,34,0.06)";

    function faNum(v) {
        try {
            return Number(v).toLocaleString("fa-IR");
        } catch (e) {
            return String(v);
        }
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

    function lineChart(canvasId, dataId, opts) {
        opts = opts || {};
        var canvas = document.getElementById(canvasId);
        var data = readJson(dataId);
        if (!canvas || !data || !data.length || !window.Chart) return;

        var color = opts.color || ACCENT;
        new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels: data.map(function (d) { return d.date_label || d.date; }),
                datasets: [{
                    label: opts.label || "",
                    data: data.map(function (d) { return d.value; }),
                    borderColor: color,
                    backgroundColor: function (ctx) {
                        var chart = ctx.chart;
                        var area = chart.chartArea;
                        if (!area) return "rgba(15,118,110,0.08)";
                        var g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
                        g.addColorStop(0, opts.fillTop || "rgba(15,118,110,0.22)");
                        g.addColorStop(1, "rgba(15,118,110,0.01)");
                        return g;
                    },
                    fill: opts.fill !== false,
                    tension: 0.35,
                    borderWidth: 2.5,
                    pointRadius: data.length > 20 ? 0 : 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: color,
                    pointBorderColor: "#fff",
                    pointBorderWidth: 1.5,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#0c1222",
                        padding: 10,
                        displayColors: false,
                        callbacks: {
                            label: function (c) {
                                var suffix = opts.suffix || "";
                                return " " + faNum(c.raw) + suffix;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: MUTED, font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
                        grid: { display: false },
                        border: { display: false },
                    },
                    y: {
                        beginAtZero: !!opts.beginAtZero,
                        ticks: {
                            color: MUTED,
                            font: { size: 11 },
                            callback: function (v) { return faNum(v) + (opts.suffix || ""); },
                        },
                        grid: { color: GRID },
                        border: { display: false },
                    }
                }
            }
        });
    }

    function barChart(canvasId, dataId, opts) {
        opts = opts || {};
        var canvas = document.getElementById(canvasId);
        var data = readJson(dataId);
        if (!canvas || !data || !data.length || !window.Chart) return;

        var color = opts.color || ACCENT;
        new Chart(canvas.getContext("2d"), {
            type: "bar",
            data: {
                labels: data.map(function (d) { return d.date_label || d.date; }),
                datasets: [{
                    data: data.map(function (d) { return d.value; }),
                    backgroundColor: color,
                    borderRadius: 5,
                    borderSkipped: false,
                    maxBarThickness: 28,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#0c1222",
                        padding: 10,
                        displayColors: false,
                        callbacks: { label: function (c) { return " " + faNum(c.raw); } }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: MUTED, font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
                        grid: { display: false },
                        border: { display: false },
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { color: MUTED, font: { size: 11 }, callback: faNum },
                        grid: { color: GRID },
                        border: { display: false },
                    }
                }
            }
        });
    }

    function doughnutChart(canvasId, dataId) {
        var canvas = document.getElementById(canvasId);
        var data = readJson(dataId);
        if (!canvas || !data || !window.Chart) return;
        var values = data.values || [];
        var labels = data.labels || [];
        if (!values.length || values.every(function (v) { return !v; })) return;

        new Chart(canvas.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        "rgba(15, 118, 110, 0.85)",
                        "rgba(180, 83, 9, 0.8)",
                        "rgba(185, 28, 28, 0.75)",
                    ],
                    borderWidth: 0,
                    hoverOffset: 6,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "62%",
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            boxWidth: 10,
                            boxHeight: 10,
                            padding: 14,
                            color: "#475569",
                            font: { size: 12 },
                        }
                    },
                    tooltip: {
                        backgroundColor: "#0c1222",
                        padding: 10,
                        callbacks: {
                            label: function (c) {
                                return " " + c.label + ": " + faNum(c.raw) + " " +
                                    ((window.KaraDashboard && window.KaraDashboard.currencyUnit) || "تومان");
                            }
                        }
                    }
                }
            }
        });
    }

    function bindFilter() {
        var input = document.getElementById("spdHistoryFilter");
        var table = document.getElementById("spdHistoryTable");
        var empty = document.getElementById("spdHistoryEmpty");
        if (!input || !table) return;
        input.addEventListener("input", function () {
            var q = (input.value || "").trim().toLowerCase();
            var rows = table.querySelectorAll("tbody tr");
            var visible = 0;
            rows.forEach(function (row) {
                var hay = (row.getAttribute("data-filter") || "").toLowerCase();
                var show = !q || hay.indexOf(q) !== -1;
                row.classList.toggle("d-none", !show);
                if (show) visible += 1;
            });
            if (empty) empty.classList.toggle("d-none", visible !== 0);
        });
    }

    window.KaraSalespersonDetail = {
        init: function () {
            requestAnimationFrame(function () {
                lineChart("spdPureChart", "spd-pure-data", {
                    label: "فروش خالص",
                    color: ACCENT,
                    fill: true,
                    suffix: " " + ((window.KaraDashboard && window.KaraDashboard.currencyUnit) || "تومان"),
                });
                barChart("spdOrdersChart", "spd-orders-data", {
                    color: COPPER,
                });
                lineChart("spdRevChart", "spd-rev-data", {
                    label: "نرخ برگشت",
                    color: DANGER,
                    fill: false,
                    beginAtZero: true,
                    suffix: "٪",
                    fillTop: "rgba(185,28,28,0.12)",
                });
                doughnutChart("spdCompChart", "spd-comp-data");
            });
            bindFilter();
        }
    };
})();
