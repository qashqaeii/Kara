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
    var stylesReady = false;

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
        var promises = [];
        parsed.querySelectorAll('link[rel="stylesheet"], style').forEach(function (node) {
            if (node.id === "portal-invoice-print-enhance") {
                return;
            }
            var clone = node.cloneNode(true);
            clone.setAttribute("data-kara-print-style", "1");
            document.head.appendChild(clone);
            if (clone.tagName === "LINK") {
                promises.push(
                    new Promise(function (resolve) {
                        clone.addEventListener("load", resolve);
                        clone.addEventListener("error", resolve);
                    })
                );
            }
        });
        return Promise.all(promises);
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

    function waitForImages() {
        var images = documentRoot.querySelectorAll("img");
        var pending = [];
        images.forEach(function (img) {
            if (!img.complete) {
                pending.push(
                    new Promise(function (resolve) {
                        img.addEventListener("load", resolve);
                        img.addEventListener("error", resolve);
                    })
                );
            }
        });
        return Promise.all(pending);
    }

    function finalizeLayout() {
        hideLoader();
        resetScale();
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
                return importKaraStyles(parsed).then(function () {
                    stylesReady = true;
                    documentRoot.innerHTML = parsed.body ? parsed.body.innerHTML : html;
                    return waitForImages();
                });
            })
            .then(function () {
                window.setTimeout(finalizeLayout, 50);
                window.setTimeout(finalizeLayout, 300);
            })
            .catch(function (err) {
                hideLoader();
                showError(err && err.message ? err.message : "خطا در بارگذاری پیش‌فاکتور");
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
