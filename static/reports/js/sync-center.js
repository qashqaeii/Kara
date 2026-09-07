/**
 * Sync center — connection test, per-report sync, history filters.
 */
(function () {
  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.content ||
    document.getElementById("scPage")?.dataset?.csrf ||
    "";

  function toast(msg, isError) {
    let el = document.getElementById("scToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "scToast";
      el.className = "sc-toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.toggle("is-error", !!isError);
    el.classList.add("is-show");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("is-show"), 3200);
  }

  async function post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrf,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body || "",
    });
    return res.json();
  }

  const btnTest = document.getElementById("btnTestConn");
  btnTest?.addEventListener("click", async () => {
    btnTest.disabled = true;
    const label = btnTest.querySelector("span");
    const prev = label?.textContent;
    if (label) label.textContent = "در حال تست...";
    try {
      const data = await post(btnTest.dataset.url);
      if (data.ok) toast("اتصال به کارا برقرار است");
      else toast("ناموفق: " + (data.error || "خطای ناشناخته"), true);
    } catch (e) {
      toast("خطای شبکه در تست اتصال", true);
    } finally {
      btnTest.disabled = false;
      if (label && prev) label.textContent = prev;
    }
  });

  const btnAll = document.getElementById("btnSyncAll");
  btnAll?.addEventListener("click", async () => {
    if (!window.confirm("همگام‌سازی همه گزارش‌ها ممکن است چند دقیقه طول بکشد و فشار همزمان روی کارا وارد کند. ادامه؟")) {
      return;
    }
    btnAll.disabled = true;
    const label = btnAll.querySelector("span");
    if (label) label.textContent = "در حال همگام‌سازی...";
    try {
      await post(btnAll.dataset.url);
      toast("همگام‌سازی گروهی شروع شد");
      setTimeout(() => location.reload(), 800);
    } catch (e) {
      toast("خطا در همگام‌سازی گروهی", true);
      btnAll.disabled = false;
      if (label) label.textContent = "همگام‌سازی همه";
    }
  });

  document.querySelectorAll(".btn-sync-one").forEach((el) => {
    el.addEventListener("click", async () => {
      el.disabled = true;
      const prev = el.textContent;
      el.textContent = "...";
      try {
        await post(el.dataset.url, "report=" + encodeURIComponent(el.dataset.report));
        toast("همگام‌سازی «" + (el.dataset.title || "") + "» انجام شد");
        setTimeout(() => location.reload(), 700);
      } catch (e) {
        toast("خطا در همگام‌سازی گزارش", true);
        el.disabled = false;
        el.textContent = prev;
      }
    });
  });

  const rows = document.querySelectorAll("#scHistoryBody tr[data-status]");
  document.querySelectorAll("[data-history-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-history-filter]").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      const f = btn.dataset.historyFilter;
      rows.forEach((row) => {
        const st = row.dataset.status;
        const show =
          f === "all" ||
          (f === "ok" && st === "success") ||
          (f === "fail" && st === "failed") ||
          (f === "run" && st === "running");
        row.hidden = !show;
      });
    });
  });
})();
