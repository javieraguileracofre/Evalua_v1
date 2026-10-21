/* Loaders para formularios y enlaces de operaciones largas (PDF, Excel, simulaciones, backups). */
(function () {
  function setBusy(el, label) {
    if (!el || el.dataset.busy === "1") return;
    el.dataset.busy = "1";
    el.setAttribute("aria-busy", "true");
    if (el.tagName === "BUTTON" || (el.tagName === "INPUT" && el.type === "submit")) {
      el.disabled = true;
      if (label) {
        el.dataset.originalHtml = el.innerHTML;
        el.innerHTML =
          '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>' +
          label;
      }
    } else if (el.classList) {
      el.classList.add("opacity-75");
    }
  }

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!form.classList.contains("js-busy-form") && !form.querySelector("[data-busy-label]")) return;
    var btn =
      form.querySelector("[type=submit][data-busy-label]") ||
      form.querySelector("[type=submit]");
    var label = (btn && btn.getAttribute("data-busy-label")) || "Procesando…";
    setBusy(btn, label);
  });

  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (!(t instanceof Element)) return;
    var a = t.closest("a.js-busy-link");
    if (!a) return;
    setBusy(a, a.getAttribute("data-busy-label") || "Generando…");
  });
})();
