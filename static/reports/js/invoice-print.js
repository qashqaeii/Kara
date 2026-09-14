(function () {
    "use strict";

    var frame = document.getElementById("invPrintFrame");
    var paper = document.getElementById("invPrintPaper");
    var viewport = document.getElementById("invPrintViewport");
    var stage = document.querySelector(".inv-print-stage");
    var loader = document.getElementById("invPrintLoader");
    var zoomLabel = document.getElementById("invZoomLabel");
    var zoomIn = document.getElementById("invZoomIn");
    var zoomOut = document.getElementById("invZoomOut");
    var fitBtn = document.getElementById("invFitBtn");
    var printBtn = document.getElementById("invPrintBtn");

    if (!frame || !paper || !stage) {
        return;
    }

    var contentWidth = 0;
    var contentHeight = 0;
    var fitScale = 1;
    var userScale = 1;
    var minUserScale = 0.55;
    var maxUserScale = 1.35;

    function readContentSize() {
        try {
            var doc = frame.contentDocument || frame.contentWindow.document;
            if (!doc || !doc.body) {
                return false;
            }
            var root = doc.documentElement;
            contentWidth = Math.max(
                doc.body.scrollWidth,
                doc.body.offsetWidth,
                root ? root.scrollWidth : 0
            );
            contentHeight = Math.max(
                doc.body.scrollHeight,
                doc.body.offsetHeight,
                root ? root.scrollHeight : 0
            );
            return contentWidth > 0 && contentHeight > 0;
        } catch (err) {
            return false;
        }
    }

    function availableSize() {
        var rect = stage.getBoundingClientRect();
        return {
            width: Math.max(rect.width - 20, 320),
            height: Math.max(rect.height - 20, 240),
        };
    }

    function computeFitScale() {
        if (!contentWidth || !contentHeight) {
            return 1;
        }
        var avail = availableSize();
        var scaleW = avail.width / contentWidth;
        var scaleH = avail.height / contentHeight;
        return Math.min(scaleW, scaleH, 1);
    }

    function effectiveScale() {
        return fitScale * userScale;
    }

    function applyLayout() {
        var scale = effectiveScale();
        frame.style.width = contentWidth + "px";
        frame.style.height = contentHeight + "px";
        frame.style.transform = "scale(" + scale + ")";
        frame.style.transformOrigin = "top left";
        frame.setAttribute("scrolling", "no");

        paper.style.width = Math.round(contentWidth * scale) + "px";
        paper.style.height = Math.round(contentHeight * scale) + "px";
        paper.style.transform = "none";

        if (zoomLabel) {
            zoomLabel.textContent = Math.round(scale * 100) + "%";
        }
    }

    function fitToScreen() {
        if (!readContentSize()) {
            return;
        }
        fitScale = computeFitScale();
        applyLayout();
    }

    function hideLoader() {
        if (loader) {
            loader.classList.add("is-hidden");
        }
        fitToScreen();
    }

    frame.addEventListener("load", function () {
        window.setTimeout(hideLoader, 60);
        window.setTimeout(fitToScreen, 180);
        window.setTimeout(fitToScreen, 600);
    });

    if (zoomIn) {
        zoomIn.addEventListener("click", function () {
            userScale = Math.min(maxUserScale, userScale + 0.08);
            applyLayout();
        });
    }

    if (zoomOut) {
        zoomOut.addEventListener("click", function () {
            userScale = Math.max(minUserScale, userScale - 0.08);
            applyLayout();
        });
    }

    if (fitBtn) {
        fitBtn.addEventListener("click", function () {
            userScale = 1;
            fitToScreen();
        });
    }

    if (printBtn) {
        printBtn.addEventListener("click", function () {
            try {
                frame.contentWindow.focus();
                frame.contentWindow.print();
            } catch (err) {
                window.print();
            }
        });
    }

    window.addEventListener("resize", function () {
        fitScale = computeFitScale();
        applyLayout();
    });

    document.addEventListener("keydown", function (event) {
        if ((event.ctrlKey || event.metaKey) && event.key === "p") {
            event.preventDefault();
            if (printBtn) {
                printBtn.click();
            }
        }
    });
})();
