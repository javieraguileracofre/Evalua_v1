/**
 * Filtro en vivo para tablas de informes contables (balance / estado de resultados).
 * Espera #fin-inf-search y secciones [data-fin-inf-section] con filas tr[data-fin-inf-q].
 */
(function () {
  function normalizeQuery(raw) {
    var q = (raw || "").toLowerCase().trim();
    if (q.normalize) {
      q = q.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    }
    return q;
  }

  function applyFilter(input) {
    var q = normalizeQuery(input.value);
    document.querySelectorAll("[data-fin-inf-section]").forEach(function (sec) {
      var rows = sec.querySelectorAll("tbody tr[data-fin-inf-q]");
      var visible = 0;
      rows.forEach(function (tr) {
        var hay = !q || (tr.getAttribute("data-fin-inf-q") || "").indexOf(q) !== -1;
        tr.classList.toggle("d-none", !hay);
        if (hay) visible++;
      });
      var empty = sec.querySelector(".fin-inf-empty-filter");
      if (empty) {
        var hasDataRows = rows.length > 0;
        empty.classList.toggle("d-none", !hasDataRows || !q || visible > 0);
      }
    });
  }

  document.addEventListener("input", function (ev) {
    if (ev.target && ev.target.id === "fin-inf-search") applyFilter(ev.target);
  });
  document.addEventListener("search", function (ev) {
    if (ev.target && ev.target.id === "fin-inf-search") applyFilter(ev.target);
  });
})();
