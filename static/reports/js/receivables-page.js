/* Receivables analytics page charts and interactive filters. */

(function () {
    "use strict";

    var TEAL = "#0f766e";
    var COPPER = "#b45309";
    var DANGER = "#b91c1c";
    var MUTED = "#94a3b8";
    var GRID = "rgba(12,18,34,0.06)";
    var started = false;

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

    function riskColor(risk) {
        if (risk === "critical") return DANGER;
        if (risk === "watch") return COPPER;
        return TEAL;
    }

    function ensureFrameSize(canvas, minH) {
        var frame = canvas.parentElement;
        if (!frame) return;
        var h = minH || 260;
        if (frame.clientHeight < 40) {
            frame.style.minHeight = h + "px";
            frame.style.height = h + "px";
        }
    }

    function markReady(canvas) {
        var frame = canvas.closest(".recv-chart-shell, .recv-mini-trend-frame, .recv-risk-orb");
        if (frame) frame.classList.add("is-ready");
    }

    function markFailed(canvas) {
        var frame = canvas.closest(".recv-chart-shell, .recv-mini-trend-frame");
        if (frame) frame.classList.add("is-failed");
        var trend = canvas.closest(".recv-mini-trend");
        if (trend && frame && frame.classList.contains("recv-mini-trend-frame")) {
            trend.classList.add("is-failed");
        }
    }

    function destroyIfAny(canvas) {
        if (!window.Chart || !canvas) return;
        var existing = Chart.getChart(canvas);
        if (existing) existing.destroy();
    }

    function bucketsChart() {
        var canvas = document.getElementById("recvBucketsChart");
        var data = readJson("recv-buckets-data");
        if (!canvas || !data || !data.length) {
            if (canvas) markFailed(canvas);
            return;
        }
        if (!window.Chart) {
            markFailed(canvas);
            return;
        }

        destroyIfAny(canvas);
        ensureFrameSize(canvas, 280);
        try {
            var chart = new Chart(canvas.getContext("2d"), {
                type: "bar",
                data: {
                    labels: data.map(function (d) { return d.label; }),
                    datasets: [{
                        data: data.map(function (d) { return Number(d.value) || 0; }),
                        backgroundColor: data.map(function (d) { return riskColor(d.risk); }),
                        borderRadius: 8,
                        borderSkipped: false,
                        maxBarThickness: 44,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 650 },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: "#0c1222",
                            padding: 12,
                            displayColors: false,
                            callbacks: {
                                title: function (items) {
                                    var row = data[items[0].dataIndex];
                                    return row.label || "";
                                },
                                label: function (c) {
                                    var row = data[c.dataIndex];
                                    return " " + (row.formatted || faNum(c.raw));
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: { color: MUTED, font: { size: 12 } },
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
            markReady(canvas);
            setTimeout(function () { try { chart.resize(); } catch (e) {} }, 80);
        } catch (err) {
            markFailed(canvas);
        }
    }

    function bandsChart() {
        var canvas = document.getElementById("recvBandsChart");
        var data = readJson("recv-bands-data");
        if (!canvas || !data || !data.length || !window.Chart) return;

        var values = data.map(function (d) { return Number(d.value) || 0; });
        if (values.every(function (v) { return v <= 0; })) return;

        var orb = canvas.closest(".recv-risk-orb");
        if (orb && orb.clientHeight < 40) {
            orb.style.minHeight = "210px";
            orb.style.height = "210px";
        }

        destroyIfAny(canvas);
        try {
            var chart = new Chart(canvas.getContext("2d"), {
                type: "doughnut",
                data: {
                    labels: data.map(function (d) { return d.label; }),
                    datasets: [{
                        data: values,
                        backgroundColor: data.map(function (d) { return d.color; }),
                        borderWidth: 3,
                        borderColor: "#ffffff",
                        hoverOffset: 6,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "70%",
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: "#0c1222",
                            padding: 12,
                            callbacks: {
                                label: function (c) {
                                    return " " + c.label + ": " + faNum(c.raw);
                                }
                            }
                        }
                    }
                }
            });
            if (orb) orb.classList.add("is-ready");
            setTimeout(function () { try { chart.resize(); } catch (e) {} }, 80);
        } catch (err) {
            /* CSS conic ring in hero already covers risk profile */
        }
    }

    function trendChart() {
        var canvas = document.getElementById("recvTrendChart");
        var data = readJson("recv-history-data");
        if (!canvas) return;
        if (!data || data.length < 2 || !window.Chart) {
            markFailed(canvas);
            return;
        }

        destroyIfAny(canvas);
        ensureFrameSize(canvas, 130);
        try {
            var chart = new Chart(canvas.getContext("2d"), {
                type: "line",
                data: {
                    labels: data.map(function (d) { return d.date_label || d.date; }),
                    datasets: [{
                        data: data.map(function (d) { return Number(d.outstanding) || 0; }),
                        borderColor: TEAL,
                        backgroundColor: "rgba(15,118,110,0.14)",
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2.5,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        pointBackgroundColor: TEAL,
                        pointBorderColor: "#fff",
                        pointBorderWidth: 1.5,
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
                            callbacks: {
                                label: function (c) {
                                    var row = data[c.dataIndex];
                                    return " " + (row.outstanding_formatted || faNum(c.raw));
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: { color: MUTED, font: { size: 10 }, maxTicksLimit: 5 },
                            grid: { display: false },
                            border: { display: false },
                        },
                        y: {
                            beginAtZero: true,
                            ticks: { color: MUTED, font: { size: 10 }, callback: faNum },
                            grid: { color: GRID },
                            border: { display: false },
                        }
                    }
                }
            });
            markReady(canvas);
            setTimeout(function () { try { chart.resize(); } catch (e) {} }, 80);
        } catch (err) {
            markFailed(canvas);
        }
    }

    function bindFilters() {
        var input = document.getElementById("recvRowFilter");
        var table = document.getElementById("recvDetailTable");
        var empty = document.getElementById("recvRowEmpty");
        var buttons = document.querySelectorAll(".recv-risk-filters button");
        if (!table) return;

        var risk = "all";

        function apply() {
            var q = input ? (input.value || "").trim().toLowerCase() : "";
            var rows = table.querySelectorAll("tbody tr[data-risk]");
            var visible = 0;
            rows.forEach(function (row) {
                var hay = (row.getAttribute("data-filter") || "").toLowerCase();
                var rowRisk = row.getAttribute("data-risk") || "";
                var matchText = !q || hay.indexOf(q) !== -1;
                var matchRisk = risk === "all" || rowRisk === risk;
                var show = matchText && matchRisk;
                row.classList.toggle("d-none", !show);
                if (show) visible += 1;
            });
            if (empty) empty.classList.toggle("d-none", visible !== 0);
        }

        if (input) input.addEventListener("input", apply);
        buttons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                buttons.forEach(function (b) { b.classList.remove("is-active"); });
                btn.classList.add("is-active");
                risk = btn.getAttribute("data-risk") || "all";
                apply();
            });
        });
    }

    function bootCharts() {
        bucketsChart();
        bandsChart();
        trendChart();
    }

    window.KaraReceivablesPage = {
        init: function () {
            if (started) return;
            started = true;
            bindFilters();
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    bootCharts();
                    setTimeout(bootCharts, 120);
                });
            });
        }
    };
})();
