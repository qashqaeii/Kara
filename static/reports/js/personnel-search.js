/**
 * Personnel search autocomplete for individual reports.
 */
const KaraPersonnelSearch = (function () {
    let config = {};
    let selected = null;
    let debounceTimer = null;

    function getElements() {
        return {
            input: document.getElementById("personnelSearch"),
            results: document.getElementById("personnelResults"),
            btn: document.getElementById("btnFetchPersonnel"),
            codeInput: document.getElementById("hiddenPersonnelCode"),
            nameInput: document.getElementById("hiddenPersonnelName"),
            form: document.getElementById("refreshForm"),
        };
    }

    function renderResults(items) {
        const { results } = getElements();
        if (!results) return;

        if (!items.length) {
            results.innerHTML = '<div class="personnel-item text-muted">نتیجه‌ای یافت نشد</div>';
            results.classList.remove("d-none");
            return;
        }

        results.innerHTML = items
            .map(
                (item, i) =>
                    `<div class="personnel-item" data-index="${i}" data-code="${item.code}" data-name="${item.name}">
                        <strong>${item.name}</strong>
                        <span class="code ms-2">${item.code}</span>
                    </div>`
            )
            .join("");

        results.querySelectorAll(".personnel-item[data-code]").forEach((el) => {
            el.addEventListener("click", () => selectPerson(el.dataset.code, el.dataset.name));
        });

        results.classList.remove("d-none");
    }

    function selectPerson(code, name) {
        selected = { code, name };
        const { input, results, btn, codeInput, nameInput } = getElements();
        if (input) input.value = `${name} (${code})`;
        if (codeInput) codeInput.value = code;
        if (nameInput) nameInput.value = name;
        if (btn) btn.disabled = false;
        if (results) results.classList.add("d-none");
    }

    async function search(query) {
        if (query.length < 1) return;
        const url = `${config.searchUrl}?q=${encodeURIComponent(query)}&report_key=${config.reportKey}`;
        try {
            const resp = await fetch(url);
            const data = await resp.json();
            if (data.error) {
                renderResults([]);
                return;
            }
            renderResults(data.results || []);
        } catch (err) {
            renderResults([]);
        }
    }

    function fetchPersonnelReport() {
        const { form, codeInput, nameInput } = getElements();
        if (!selected && codeInput && codeInput.value) {
            selected = { code: codeInput.value, name: nameInput ? nameInput.value : "" };
        }
        if (!selected) return;

        if (codeInput) codeInput.value = selected.code;
        if (nameInput) nameInput.value = selected.name;
        if (form) form.submit();
    }

    function init(cfg) {
        config = cfg || {};
        const { input, btn, results } = getElements();
        if (!input) return;

        input.addEventListener("input", () => {
            selected = null;
            if (btn) btn.disabled = true;
            clearTimeout(debounceTimer);
            const q = input.value.trim();
            if (q.length < 1) {
                if (results) results.classList.add("d-none");
                return;
            }
            debounceTimer = setTimeout(() => search(q), 350);
        });

        input.addEventListener("focus", () => {
            if (results && results.children.length) results.classList.remove("d-none");
        });

        document.addEventListener("click", (e) => {
            if (!e.target.closest("#personnelSearch") && !e.target.closest("#personnelResults")) {
                if (results) results.classList.add("d-none");
            }
        });

        if (btn) {
            btn.addEventListener("click", fetchPersonnelReport);
        }

        const codeInput = document.getElementById("hiddenPersonnelCode");
        if (codeInput && codeInput.value) {
            selected = { code: codeInput.value, name: document.getElementById("hiddenPersonnelName")?.value || "" };
            if (btn) btn.disabled = false;
        }
    }

    return { init };
})();

window.KaraPersonnelSearch = KaraPersonnelSearch;
