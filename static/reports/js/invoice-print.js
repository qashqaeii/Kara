(function () {
    "use strict";

    var frame = document.getElementById("invPrintFrame");
    var paper = document.getElementById("invPrintPaper");
    var loader = document.getElementById("invPrintLoader");
    var zoomLabel = document.getElementById("invZoomLabel");
    var zoomIn = document.getElementById("invZoomIn");
    var zoomOut = document.getElementById("invZoomOut");
    var printBtn = document.getElementById("invPrintBtn");

    if (!frame || !paper) {
        return;
    }

    var scale = 1;
    var minScale = 0.7;
    var maxScale = 1.4;

    function applyScale() {
        paper.style.transform = "scale(" + scale + ")";
        if (zoomLabel) {
            zoomLabel.textContent = Math.round(scale * 100) + "%";
        }
    }

    function resizeFrame() {
        try {
            var doc = frame.contentDocument || frame.contentWindow.document;
            if (!doc || !doc.body) {
                return;
            }
            var height = Math.max(
                doc.body.scrollHeight,
                doc.documentElement ? doc.documentElement.scrollHeight : 0
            );
            frame.style.height = Math.max(height + 24, 480) + "px";
        } catch (err) {
            frame.style.height = "80vh";
        }
    }

    function hideLoader() {
        if (loader) {
            loader.classList.add("is-hidden");
        }
        resizeFrame();
    }

    frame.addEventListener("load", hideLoader);

    if (zoomIn) {
        zoomIn.addEventListener("click", function () {
            scale = Math.min(maxScale, scale + 0.1);
            applyScale();
        });
    }

    if (zoomOut) {
        zoomOut.addEventListener("click", function () {
            scale = Math.max(minScale, scale - 0.1);
            applyScale();
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

    applyScale();
})();
