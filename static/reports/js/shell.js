/**
 * KARA App Shell — sticky header, nav overflow (desktop).
 */
(function () {
    "use strict";

    var DESKTOP_MIN = 992;

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
        var navGroups = document.querySelector(".kara-nav-groups");
        var overflowWrap = document.getElementById("karaNavOverflow");
        var overflowMenu = document.getElementById("karaNavOverflowMenu");
        if (!navGroups || !overflowWrap || !overflowMenu) return;

        var items = Array.prototype.slice.call(
            navGroups.querySelectorAll(".kara-nav-item[data-nav-priority]")
        );
        if (!items.length) return;

        function buildDropdownItem(li) {
            var link = li.querySelector(".nav-link");
            if (!link) return null;
            var menuLi = document.createElement("li");
            menuLi.setAttribute("role", "none");
            var a = document.createElement("a");
            a.className = "dropdown-item";
            a.setAttribute("role", "menuitem");
            if (link.classList.contains("active")) {
                a.classList.add("active");
                a.setAttribute("aria-current", "page");
            }
            a.href = link.getAttribute("href") || "#";
            if (link.target) a.target = link.target;
            if (link.rel) a.rel = link.rel;
            a.innerHTML = link.innerHTML;
            menuLi.appendChild(a);
            return menuLi;
        }

        function restoreAll() {
            items.forEach(function (li) {
                li.classList.remove("d-none");
                li.removeAttribute("aria-hidden");
            });
            overflowMenu.innerHTML = "";
            overflowWrap.classList.add("d-none");
            overflowWrap.classList.remove("has-active");
        }

        function hiddenInOverflow(li) {
            li.classList.add("d-none");
            li.setAttribute("aria-hidden", "true");
            var menuItem = buildDropdownItem(li);
            if (menuItem) overflowMenu.appendChild(menuItem);
        }

        function measureWidth() {
            var used = 0;
            items.forEach(function (li) {
                if (!li.classList.contains("d-none") && li.offsetParent !== null) {
                    used += li.offsetWidth + 6;
                }
            });
            navGroups.querySelectorAll(".nav-group-divider").forEach(function (d) {
                if (d.offsetParent !== null) used += d.offsetWidth + 8;
            });
            if (!overflowWrap.classList.contains("d-none")) {
                used += overflowWrap.offsetWidth + 8;
            }
            return used;
        }

        function checkOverflow() {
            restoreAll();
            if (window.innerWidth < DESKTOP_MIN) return;

            var headerInner = document.querySelector(".kara-header-inner");
            var brand = document.querySelector(".kara-brand");
            var utility = document.querySelector(".kara-nav-utility");
            if (!headerInner || !brand || !utility) return;

            var available = headerInner.clientWidth
                - brand.offsetWidth
                - utility.offsetWidth
                - 80;

            if (measureWidth() <= available) return;

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
                        if (measureWidth() > available) hiddenInOverflow(li);
                    });
            });

            if (!overflowMenu.children.length) {
                restoreAll();
                return;
            }

            var activeInOverflow = overflowMenu.querySelector(".dropdown-item.active");
            overflowWrap.classList.toggle("has-active", !!activeInOverflow);
        }

        var debounce;
        window.addEventListener("resize", function () {
            clearTimeout(debounce);
            debounce = setTimeout(checkOverflow, 80);
        });

        var run = function () {
            checkOverflow();
            setTimeout(checkOverflow, 120);
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
