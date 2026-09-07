/* Analytics ranking page charts + live table/list filters — RTL-safe Chart.js. */

(function () {
    "use strict";

    var DEFAULT_ACCENT = "#0f766e";
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

    function valueLabel(v, opts) {
        opts = opts || {};
        if (opts.money === false) {
            var unit = opts.unit || "";
            return " " + faNum(v) + (unit ? " " + unit : "");
        }
        return moneyLabel(v);
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

    function ensureFrameSize(canvas, minH) {
        var frame = canvas && canvas.closest(".ax-chart-frame");
        if (!frame) frame = canvas && canvas.parentElement;
        if (!frame) return;
        var h = minH || 280;
        frame.style.minHeight = h + "px";
        if (frame.clientHeight < 40) {
            frame.style.height = h + "px";
        }
    }

    function destroyIfAny(canvas) {
        if (!window.Chart || !canvas) return;
        var existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
    }

    function markFailed(canvas) {
        var frame = canvas && canvas.closest(".ax-chart-frame");
        if (frame) frame.classList.add("is-failed");
    }

    function hideFallback(canvas) {
        var panel = canvas.closest(".ax-chart-panel") || canvas.parentElement;
        if (!panel) return;
        var fb = panel.querySelector(".ax-chart-fallback");
        if (fb) fb.classList.add("d-none");
    }

    function bindTableFilter(filterId, tableId, emptyId) {
        var input = document.getElementById(filterId);
        var table = document.getElementById(tableId);
        var empty = emptyId ? document.getElementById(emptyId) : null;
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

    function bindListFilter(filterId, listId, emptyId) {
        var input = document.getElementById(filterId);
        var list = document.getElementById(listId);
        var empty = emptyId ? document.getElementById(emptyId) : null;
        if (!input || !list) return;

        input.addEventListener("input", function () {
            var q = (input.value || "").trim().toLowerCase();
            var items = list.querySelectorAll("li");
            var visible = 0;
            items.forEach(function (li) {
                var hay = (li.getAttribute("data-filter") || li.textContent || "").toLowerCase();
                var show = !q || hay.indexOf(q) !== -1;
                li.classList.toggle("d-none", !show);
                if (show) visible += 1;
            });
            if (empty) empty.classList.toggle("d-none", visible !== 0);
        });
    }

    function initBarChart(opts) {
        var data = readJson(opts.dataId);
        var canvas = document.getElementById(opts.chartId);
        if (!data || !data.length || !canvas) {
            if (canvas) markFailed(canvas);
            return false;
        }
        if (!window.Chart) {
            markFailed(canvas);
            return false;
        }

        destroyIfAny(canvas);
        ensureFrameSize(canvas, opts.horizontal ? 240 : 220);

        var accent = opts.accent || DEFAULT_ACCENT;
        var horizontal = !!opts.horizontal;
        var values = data.map(function (d) { return Number(d.value) || 0; });
        var labels = data.map(function (d) { return d.name || ""; });

        try {
            var chart = new Chart(canvas.getContext("2d"), {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [{
                        label: opts.label || "فروش",
                        data: values,
                        backgroundColor: values.map(function (_, i) {
                            return i === 0 ? accent : (i < 3 ? "#0d9488" : "#94a3b8");
                        }),
                        borderRadius: 6,
                        borderSkipped: false,
                        maxBarThickness: horizontal ? 18 : 32,
                    }]
                },
                options: {
                    indexAxis: horizontal ? "y" : "x",
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 550 },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: "#0c1222",
                            titleColor: "#f8fafc",
                            bodyColor: accent,
                            padding: 10,
                            displayColors: false,
                            callbacks: {
                                label: function (c) { return valueLabel(c.raw, opts); }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                color: MUTED,
                                font: { size: 11 },
                                callback: horizontal ? function (v) { return faNum(v); } : undefined,
                                maxRotation: 0,
                                autoSkip: true,
                            },
                            grid: {
                                color: horizontal ? GRID : "transparent",
                                drawTicks: false,
                            },
                            border: { display: false },
                        },
                        y: {
                            ticks: {
                                color: MUTED,
                                font: { size: 11 },
                                callback: horizontal ? undefined : function (v) { return faNum(v); },
                            },
                            grid: {
                                color: horizontal ? "transparent" : GRID,
                                drawTicks: false,
                            },
                            border: { display: false },
                            beginAtZero: !horizontal,
                        }
                    }
                }
            });
            requestAnimationFrame(function () { chart.resize(); });
            hideFallback(canvas);
            return true;
        } catch (err) {
            console.error("KaraAnalyticsRank bar chart failed", err);
            markFailed(canvas);
            return false;
        }
    }

    function initDoughnut(opts) {
        var data = readJson(opts.dataId);
        var canvas = document.getElementById(opts.chartId);
        if (!data || !data.length || !canvas) {
            if (canvas) markFailed(canvas);
            return false;
        }
        if (!window.Chart) {
            markFailed(canvas);
            return false;
        }

        destroyIfAny(canvas);
        ensureFrameSize(canvas, 240);

        try {
            var chart = new Chart(canvas.getContext("2d"), {
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
                    animation: { duration: 550 },
                    plugins: {
                        legend: {
                            position: "bottom",
                            rtl: true,
                            labels: {
                                boxWidth: 10,
                                boxHeight: 10,
                                padding: 10,
                                font: { size: 11 },
                                color: MUTED,
                            }
                        },
                        tooltip: {
                            backgroundColor: "#0c1222",
                            padding: 10,
                            callbacks: {
                                label: function (c) {
                                    return " " + c.label + ": " + valueLabel(c.raw, opts).trim();
                                }
                            }
                        }
                    }
                }
            });
            requestAnimationFrame(function () { chart.resize(); });
            hideFallback(canvas);
            return true;
        } catch (err) {
            console.error("KaraAnalyticsRank doughnut failed", err);
            markFailed(canvas);
            return false;
        }
    }

    function deferInit(fn) {
        // Two frames so flex/grid parents have final computed size under RTL
        requestAnimationFrame(function () {
            requestAnimationFrame(fn);
        });
    }

    function bootChart(cfg) {
        if (!cfg || !cfg.chartId || !cfg.dataId) return;
        if (cfg.type === "doughnut") {
            deferInit(function () { initDoughnut(cfg); });
        } else {
            deferInit(function () { initBarChart(cfg); });
        }
    }

    window.KaraAnalyticsRank = {
        init: function (opts) {
            opts = opts || {};
            if (opts.charts && opts.charts.length) {
                opts.charts.forEach(bootChart);
            } else if (opts.chartId && opts.dataId) {
                bootChart(opts);
            }
            if (opts.filterId && opts.tableId) {
                bindTableFilter(opts.filterId, opts.tableId, opts.emptyId);
            }
        },
        initDoughnut: function (opts) {
            deferInit(function () { initDoughnut(opts || {}); });
        },
        bindListFilter: bindListFilter,
    };
})();
