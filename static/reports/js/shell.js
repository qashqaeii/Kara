/**
 * KARA App Shell — sticky header, nav overflow (992–1400px).
 */
(function () {
    "use strict";

    var OVERFLOW_MIN = 992;
    var OVERFLOW_MAX = 1400;

    function initStickyHeader() {
        var header = document.getElementById("karaHeader");
        if (!header) return;
        var onScroll = function () {
            header.classList.toggle("is-scrolled", window.scrollY > 4);
        };
        onScroll();
        window.addEventListener("scroll", onScroll, { passive: true });
    }

    function initNavOverflow() {
        var nav = document.querySelector(".kara-nav-groups");
        var overflowWrap = document.getElementById("karaNavOverflow");
        var overflowMenu = document.getElementById("karaNavOverflowMenu");
        if (!nav || !overflowWrap || !overflowMenu) return;

        var items = Array.prototype.slice.call(
            nav.querySelectorAll(".kara-nav-item[data-nav-priority]")
        );
        if (!items.length) return;

        items.forEach(function (li) {
            if (!li.dataset.originalParent) {
                var parent = li.parentElement;
                if (parent) {
                    li.dataset.originalParent = parent.className || "nav-group";
                    li.dataset.originalIndex = String(
                        Array.prototype.indexOf.call(parent.children, li)
                    );
                }
            }
        });

        function restoreAll() {
            items.forEach(function (li) {
                var groups = nav.querySelectorAll(".nav-group");
                var target = groups[0];
                groups.forEach(function (g) {
                    if ((g.className || "") === li.dataset.originalParent) target = g;
                });
                if (target && !target.contains(li)) {
                    target.appendChild(li);
                }
                li.classList.remove("d-none");
            });
            overflowMenu.innerHTML = "";
            overflowWrap.classList.add("d-none");
            overflowWrap.classList.remove("has-active");
        }

        function moveToOverflow(li) {
            if (overflowMenu.contains(li)) return;
            li.classList.add("d-none");
            var clone = li.cloneNode(true);
            clone.classList.remove("d-none");
            var link = clone.querySelector(".nav-link");
            if (link) {
                link.classList.remove("dropdown-item");
            }
            overflowMenu.appendChild(clone);
        }

        function totalWidth() {
            var used = 0;
            nav.querySelectorAll(".kara-nav-item").forEach(function (li) {
                if (!li.classList.contains("d-none") && li.offsetParent !== null) {
                    used += li.offsetWidth + 6;
                }
            });
            nav.querySelectorAll(".nav-group-divider").forEach(function (d) {
                if (d.offsetParent !== null) used += d.offsetWidth + 8;
            });
            if (!overflowWrap.classList.contains("d-none")) {
                used += overflowWrap.offsetWidth + 8;
            }
            return used;
        }

        function checkOverflow() {
            restoreAll();
            var w = window.innerWidth;
            if (w < OVERFLOW_MIN || w > OVERFLOW_MAX) return;

            var headerInner = document.querySelector(".kara-header-inner");
            var brand = document.querySelector(".kara-brand");
            var utility = document.querySelector(".kara-nav-utility");
            if (!headerInner || !brand || !utility) return;

            var available = headerInner.clientWidth
                - brand.offsetWidth
                - utility.offsetWidth
                - 72;

            if (totalWidth() <= available) return;

            overflowWrap.classList.remove("d-none");

            [3, 2].forEach(function (prio) {
                items
                    .filter(function (li) {
                        return li.getAttribute("data-nav-priority") === String(prio);
                    })
                    .sort(function (a, b) {
                        return Number(b.getAttribute("data-nav-order") || 0)
                            - Number(a.getAttribute("data-nav-order") || 0);
                    })
                    .forEach(function (li) {
                        if (totalWidth() > available) moveToOverflow(li);
                    });
            });

            var activeInOverflow = overflowMenu.querySelector(".nav-link.active");
            overflowWrap.classList.toggle("has-active", !!activeInOverflow);
        }

        var debounce;
        window.addEventListener("resize", function () {
            clearTimeout(debounce);
            debounce = setTimeout(checkOverflow, 80);
        });

        var run = function () {
            checkOverflow();
            setTimeout(checkOverflow, 100);
        };
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(run);
        } else {
            setTimeout(run, 150);
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        initStickyHeader();
        initNavOverflow();
    });
})();
