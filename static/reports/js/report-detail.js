/**
 * Report detail — DataTables chrome + RTL-safe leaders chart.
 */
(function () {
    "use strict";

    var TEAL = "#0f766e";
    var COPPER = "#b45309";
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

    function ensureFrame(canvas, minH) {
        var frame = canvas && canvas.closest(".rd-chart-frame");
        if (!frame) return;
        var h = minH || 280;
        frame.style.minHeight = h + "px";
        if (frame.clientHeight < 40) frame.style.height = h + "px";
    }

    function markFailed(canvas) {
        var frame = canvas && canvas.closest(".rd-chart-frame");
        if (frame) frame.classList.add("is-failed");
    }

    function leadersChart() {
        var canvas = document.getElementById("rdLeadersChart");
        var data = readJson("rd-leaders-chart-data");
        if (!canvas || !data || !data.length || !window.Chart) {
            if (canvas) markFailed(canvas);
            return;
        }

        var existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
        ensureFrame(canvas, 280);

        try {
            var chart = new Chart(canvas.getContext("2d"), {
                type: "bar",
                data: {
                    labels: data.map(function (d) { return d.name || ""; }),
                    datasets: [{
                        data: data.map(function (d) { return Number(d.value) || 0; }),
                        backgroundColor: data.map(function (_, i) {
                            if (i === 0) return COPPER;
                            if (i < 3) return TEAL;
                            return "#94a3b8";
                        }),
                        borderRadius: 6,
                        borderSkipped: false,
                        maxBarThickness: 22,
                    }]
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 550 },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: "#0c1222",
                            padding: 10,
                            displayColors: false,
                            callbacks: {
                                label: function (c) { return " " + faNum(c.raw); }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                color: MUTED,
                                font: { size: 11 },
                                callback: function (v) { return faNum(v); },
                            },
                            grid: { color: GRID, drawTicks: false },
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
            requestAnimationFrame(function () { chart.resize(); });
        } catch (err) {
            console.error("rd leaders chart failed", err);
            markFailed(canvas);
        }
    }

    function initDataTable() {
        if (!window.jQuery || !jQuery.fn.DataTable) return;
        var $table = jQuery("#reportTable");
        if (!$table.length) return;
        if (jQuery.fn.DataTable.isDataTable($table)) return;

        $table.DataTable({
            language: { url: "https://cdn.datatables.net/plug-ins/1.13.8/i18n/fa.json" },
            pageLength: 25,
            order: [],
            scrollX: true,
            dom: '<"row px-2 pt-2"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>rt<"row px-2 pb-2"ip>',
        });
    }

    function boot() {
        requestAnimationFrame(function () {
            requestAnimationFrame(leadersChart);
        });
        initDataTable();
        if (window.KaraPersonnelSearch && window.KARA_REPORT) {
            KaraPersonnelSearch.init(window.KARA_REPORT);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
