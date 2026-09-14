(function () {
    "use strict";

    var contentUrl = window.INV_PRINT_CONTENT_URL || "";
    var loader = document.getElementById("invPrintLoader");
    var errorBox = document.getElementById("invPrintError");
    var scaler = document.getElementById("invPrintScaler");
    var documentRoot = document.getElementById("invPrintDocument");
    var zoomLabel = document.getElementById("invZoomLabel");
    var zoomIn = document.getElementById("invZoomIn");
    var zoomOut = document.getElementById("invZoomOut");
    var fitBtn = document.getElementById("invFitBtn");
    var printBtn = document.getElementById("invPrintBtn");

    if (!contentUrl || !scaler || !documentRoot) {
        return;
    }

    var userScale = 1;
    var minScale = 0.75;
    var maxScale = 1.35;
    var karaBaseSet = false;
    var loaderHidden = false;

    function showError(message) {
        if (!errorBox) {
            return;
        }
        errorBox.textContent = message;
        errorBox.classList.remove("is-hidden");
    }

    function hideLoader() {
        if (loaderHidden || !loader) {
            return;
        }
        loaderHidden = true;
        loader.classList.add("is-hidden");
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
        parsed.querySelectorAll('link[rel="stylesheet"], style').forEach(function (node) {
            if (node.id === "portal-invoice-print-enhance") {
                return;
            }
            var clone = node.cloneNode(true);
            clone.setAttribute("data-kara-print-style", "1");
            document.head.appendChild(clone);
        });
    }

    function applyScale() {
        scaler.style.transform = userScale === 1 ? "none" : "scale(" + userScale + ")";
        if (zoomLabel) {
            zoomLabel.textContent = Math.round(userScale * 100) + "%";
        }
    }

    function resetScale() {
        userScale = 1;
        applyScale();
    }

    function revealDocument() {
        hideLoader();
        resetScale();
    }

    function scheduleReveal() {
        window.requestAnimationFrame(function () {
            revealDocument();
        });
    }

    function loadDocument() {
        var safetyTimer = window.setTimeout(revealDocument, 1500);

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
                scheduleReveal();
            })
            .catch(function (err) {
                window.clearTimeout(safetyTimer);
                hideLoader();
                showError(err && err.message ? err.message : "خطا در بارگذاری پیش‌فاکتور");
            })
            .then(function () {
                window.clearTimeout(safetyTimer);
            });
    }

    if (zoomIn) {
        zoomIn.addEventListener("click", function () {
            userScale = Math.min(maxScale, userScale + 0.1);
            applyScale();
        });
    }

    if (zoomOut) {
        zoomOut.addEventListener("click", function () {
            userScale = Math.max(minScale, userScale - 0.1);
            applyScale();
        });
    }

    if (fitBtn) {
        fitBtn.addEventListener("click", resetScale);
    }

    if (printBtn) {
        printBtn.addEventListener("click", function () {
            window.print();
        });
    }

    document.addEventListener("keydown", function (event) {
        if ((event.ctrlKey || event.metaKey) && event.key === "p") {
            event.preventDefault();
            window.print();
        }
    });

    loadDocument();
})();
