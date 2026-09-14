(function () {
    "use strict";

    var contentUrl = window.INV_PRINT_CONTENT_URL || "";
    var stage = document.getElementById("invPrintStage");
    var loader = document.getElementById("invPrintLoader");
    var errorBox = document.getElementById("invPrintError");
    var scaler = document.getElementById("invPrintScaler");
    var documentRoot = document.getElementById("invPrintDocument");
    var zoomLabel = document.getElementById("invZoomLabel");
    var zoomIn = document.getElementById("invZoomIn");
    var zoomOut = document.getElementById("invZoomOut");
    var fitBtn = document.getElementById("invFitBtn");
    var printBtn = document.getElementById("invPrintBtn");

    if (!contentUrl || !stage || !scaler || !documentRoot) {
        return;
    }

    var contentWidth = 0;
    var contentHeight = 0;
    var fitScale = 1;
    var userScale = 1;
    var minUserScale = 0.6;
    var maxUserScale = 1.4;
    var karaBaseSet = false;

    function showError(message) {
        if (!errorBox) {
            return;
        }
        errorBox.textContent = message;
        errorBox.classList.remove("is-hidden");
    }

    function hideLoader() {
        if (loader) {
            loader.classList.add("is-hidden");
        }
    }

    function ensureKaraBase(parsed) {
        if (karaBaseSet) {
            return;
        }
        var baseNode = parsed.querySelector("base");
        var href = baseNode && baseNode.getAttribute("href");
        if (!href) {
            return;
        }
        var existing = document.querySelector("base[data-kara-print]");
        if (!existing) {
            existing = document.createElement("base");
            existing.setAttribute("data-kara-print", "1");
            document.head.appendChild(existing);
        }
        existing.setAttribute("href", href);
        karaBaseSet = true;
    }

    function importKaraStyles(parsed) {
        var marker = "data-kara-print-style";
        parsed.querySelectorAll('link[rel="stylesheet"], style').forEach(function (node) {
            if (node.id === "portal-invoice-print-enhance") {
                return;
            }
            var clone = node.cloneNode(true);
            clone.setAttribute(marker, "1");
            document.head.appendChild(clone);
        });
    }

    function measureContent() {
        contentWidth = Math.max(documentRoot.scrollWidth, documentRoot.offsetWidth, 720);
        contentHeight = Math.max(documentRoot.scrollHeight, documentRoot.offsetHeight, 400);
        return contentWidth > 0 && contentHeight > 0;
    }

    function availableSize() {
        var rect = stage.getBoundingClientRect();
        return {
            width: Math.max(rect.width - 24, 320),
            height: Math.max(rect.height - 24, 240),
        };
    }

    function computeFitScale() {
        if (!contentWidth || !contentHeight) {
            return 1;
        }
        var avail = availableSize();
        return Math.min(avail.width / contentWidth, avail.height / contentHeight, 1);
    }

    function effectiveScale() {
        return fitScale * userScale;
    }

    function applyLayout() {
        if (!measureContent()) {
            return;
        }
        var scale = effectiveScale();
        documentRoot.style.width = contentWidth + "px";
        documentRoot.style.height = contentHeight + "px";
        documentRoot.style.transform = "scale(" + scale + ")";

        scaler.style.width = Math.round(contentWidth * scale) + "px";
        scaler.style.height = Math.round(contentHeight * scale) + "px";

        if (zoomLabel) {
            zoomLabel.textContent = Math.round(scale * 100) + "%";
        }
    }

    function fitToScreen() {
        userScale = 1;
        if (!measureContent()) {
            return;
        }
        fitScale = computeFitScale();
        applyLayout();
    }

    function loadDocument() {
        fetch(contentUrl, { credentials: "same-origin", cache: "no-store" })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("بارگذاری پیش‌فاکتور ناموفق بود.");
                }
                return response.text();
            })
            .then(function (html) {
                var parsed = new DOMParser().parseFromString(html, "text/html");
                ensureKaraBase(parsed);
                importKaraStyles(parsed);
                documentRoot.innerHTML = parsed.body ? parsed.body.innerHTML : html;
                hideLoader();
                window.setTimeout(fitToScreen, 80);
                window.setTimeout(fitToScreen, 400);
                window.setTimeout(fitToScreen, 1200);
            })
            .catch(function (err) {
                hideLoader();
                showError(err && err.message ? err.message : "خطا در بارگذاری پیش‌فاکتور");
            });
    }

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
        fitBtn.addEventListener("click", fitToScreen);
    }

    if (printBtn) {
        printBtn.addEventListener("click", function () {
            window.print();
        });
    }

    window.addEventListener("resize", function () {
        fitScale = computeFitScale();
        applyLayout();
    });

    document.addEventListener("keydown", function (event) {
        if ((event.ctrlKey || event.metaKey) && event.key === "p") {
            event.preventDefault();
            window.print();
        }
    });

    loadDocument();
})();
