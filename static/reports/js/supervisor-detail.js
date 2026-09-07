/* Supervisor detail charts + team table filter. */

(function () {
    "use strict";

    var TEAL = "#0f766e";
    var COPPER = "#b45309";
    var MUTED = "#94a3b8";
    var GRID = "rgba(12,18,34,0.06)";
    var PALETTE = ["#0f766e", "#0d9488", "#14b8a6", "#b45309", "#d97706", "#64748b", "#334155", "#0b3d3a"];
    var CURRENCY = (window.KaraDashboard && window.KaraDashboard.currencyUnit) || "تومان";

    function faNum(v) {
        try {
            return Number(v).toLocaleString("fa-IR");
        } catch (e) {
            return String(v);
        }
    }

    function moneyLabel(v) {
        return " " + faNum(v) + " " + CURRENCY;
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

    function ensureSize(canvas, minH) {
        var frame = canvas && canvas.closest(".ax-chart-frame");
        if (!frame) return;
        var h = minH || 260;
        frame.style.minHeight = h + "px";
        if (frame.clientHeight < 40) frame.style.height = h + "px";
    }

    function destroy(canvas) {
        if (!window.Chart || !canvas) return;
        var existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
    }

    function lineChart(canvasId, dataId, opts) {
        opts = opts || {};
        var canvas = document.getElementById(canvasId);
        var data = readJson(dataId);
        if (!canvas || !data || !data.length || !window.Chart) return;
        destroy(canvas);
        ensureSize(canvas, opts.height || 280);
        var color = opts.color || TEAL;
        new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels: data.map(function (d) { return d.date_label || d.date; }),
                datasets: [{
                    data: data.map(function (d) { return Number(d.value) || 0; }),
                    borderColor: color,
                    backgroundColor: opts.fill || "rgba(15,118,110,0.12)",
                    fill: opts.fill !== false,
                    tension: 0.35,
                    borderWidth: 2.4,
                    pointRadius: data.length > 20 ? 0 : 3,
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
                                if (opts.money === false) return " " + faNum(c.raw) + (opts.unit ? " " + opts.unit : "");
                                return moneyLabel(c.raw);
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
                        beginAtZero: true,
                        ticks: {
                            color: MUTED,
                            font: { size: 11 },
                            callback: function (v) { return faNum(v); },
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
        destroy(canvas);
        ensureSize(canvas, 240);
        var horizontal = opts.horizontal !== false;
        new Chart(canvas.getContext("2d"), {
            type: "bar",
            data: {
                labels: data.map(function (d) { return d.name || ""; }),
                datasets: [{
                    data: data.map(function (d) { return Number(d.value) || 0; }),
                    backgroundColor: data.map(function (_, i) {
                        return i === 0 ? TEAL : (i < 3 ? "#0d9488" : "#94a3b8");
                    }),
                    borderRadius: 6,
                    borderSkipped: false,
                    maxBarThickness: 18,
                }]
            },
            options: {
                indexAxis: horizontal ? "y" : "x",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#0c1222",
                        padding: 10,
                        displayColors: false,
                        callbacks: {
                            label: function (c) {
                                if (opts.money === false) return " " + faNum(c.raw) + (opts.unit ? " " + opts.unit : "");
                                return moneyLabel(c.raw);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: MUTED, font: { size: 11 }, callback: function (v) { return faNum(v); } },
                        grid: { color: horizontal ? GRID : "transparent" },
                        border: { display: false },
                    },
                    y: {
                        ticks: { color: MUTED, font: { size: 11 } },
                        grid: { display: false },
                        border: { display: false },
                    }
                }
            }
        });
    }

    function doughnut(canvasId, dataId) {
        var canvas = document.getElementById(canvasId);
        var data = readJson(dataId);
        if (!canvas || !data || !data.length || !window.Chart) return;
        destroy(canvas);
        ensureSize(canvas, 280);
        new Chart(canvas.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: data.map(function (d) { return d.name || ""; }),
                datasets: [{
                    data: data.map(function (d) { return Number(d.value) || 0; }),
                    backgroundColor: data.map(function (_, i) { return PALETTE[i % PALETTE.length]; }),
                    borderWidth: 0,
                    hoverOffset: 8,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "62%",
                plugins: {
                    legend: {
                        position: "bottom",
                        rtl: true,
                        labels: { boxWidth: 10, boxHeight: 10, padding: 10, font: { size: 11 }, color: MUTED }
                    },
                    tooltip: {
                        backgroundColor: "#0c1222",
                        padding: 10,
                        callbacks: {
                            label: function (c) {
                                return " " + c.label + ": " + moneyLabel(c.raw).trim();
                            }
                        }
                    }
                }
            }
        });
    }

    function bindFilter() {
        var input = document.getElementById("svdTeamFilter");
        var table = document.getElementById("svdTeamTable");
        var empty = document.getElementById("svdTeamEmpty");
        if (!input || !table) return;
        input.addEventListener("input", function () {
            var q = (input.value || "").trim().toLowerCase();
            var rows = table.querySelectorAll("tbody tr");
            var visible = 0;
            rows.forEach(function (row) {
                var hay = (row.getAttribute("data-filter") || row.textContent || "").toLowerCase();
                var show = !q || hay.indexOf(q) !== -1;
                row.classList.toggle("d-none", !show);
                if (show) visible += 1;
            });
            if (empty) empty.classList.toggle("d-none", visible !== 0);
        });
    }

    window.KaraSupervisorDetail = {
        init: function () {
            requestAnimationFrame(function () {
                lineChart("svdSaleChart", "svd-sale-data", { height: 300 });
                doughnut("svdShareChart", "svd-share-data");
                lineChart("svdOrdersTrend", "svd-orders-trend-data", {
                    color: COPPER,
                    fill: "rgba(180,83,9,0.12)",
                    money: false,
                    unit: "سفارش",
                });
                barChart("svdOrdersRank", "svd-orders-rank-data", {
                    money: false,
                    unit: "سفارش",
                });
                bindFilter();
            });
        }
    };
})();
