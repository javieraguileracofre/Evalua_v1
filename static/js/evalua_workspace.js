/* Buscador global, fijados, recientes y confirmación de acciones sensibles. */
(function () {
  var PIN_KEY = "evalua-pins";
  var RECENT_KEY = "evalua-recents";

  function readJson(key) {
    try {
      var raw = localStorage.getItem(key);
      var data = raw ? JSON.parse(raw) : [];
      return Array.isArray(data) ? data : [];
    } catch (e) {
      return [];
    }
  }

  function writeJson(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) { /* almacenamiento lleno o bloqueado */ }
  }

  function norm(text) {
    return String(text || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();
  }

  function remember(item) {
    if (!item || !item.href || !item.label) return;
    var rows = readJson(RECENT_KEY).filter(function (row) {
      return row.href !== item.href;
    });
    rows.unshift({
      href: item.href,
      label: item.label,
      kind: item.kind || "recente",
      icon: item.icon || "bi-clock-history",
      at: Date.now()
    });
    writeJson(RECENT_KEY, rows.slice(0, 8));
    paintRecents();
  }

  function paintRecents() {
    var host = document.getElementById("homeRecents");
    if (!host) return;
    var list = host.querySelector("[data-recent-list]");
    var rows = readJson(RECENT_KEY);
    if (!list || !rows.length) {
      host.hidden = true;
      return;
    }
    list.innerHTML = "";
    rows.forEach(function (row) {
      var a = document.createElement("a");
      a.className = "btn btn-sm btn-outline-secondary";
      a.href = row.href;
      a.textContent = row.label;
      a.setAttribute("data-recent", "1");
      a.setAttribute("data-recent-label", row.label || "");
      a.setAttribute("data-recent-kind", row.kind || "recente");
      a.setAttribute("data-recent-icon", row.icon || "bi-clock-history");
      list.appendChild(a);
    });
    host.hidden = false;
  }

  function paintPins() {
    var pins = readJson(PIN_KEY);
    document.querySelectorAll("[data-sidebar-pins]").forEach(function (host) {
      host.innerHTML = "";
      if (!pins.length) {
        host.classList.add("is-empty");
        return;
      }
      host.classList.remove("is-empty");
      var label = document.createElement("div");
      label.className = "sidebar-pins-label";
      label.textContent = "Fijados";
      host.appendChild(label);
      pins.forEach(function (pin) {
        var a = document.createElement("a");
        a.className = "nav-item-evalua";
        a.href = pin.href;
        a.setAttribute("data-nav-label", pin.label || "");
        a.title = pin.label || "";
        var wrap = document.createElement("span");
        wrap.className = "nav-item-icon-wrap";
        var icon = document.createElement("i");
        icon.className = "bi " + (pin.icon || "bi-star");
        wrap.appendChild(icon);
        var label = document.createElement("span");
        label.className = "nav-item-label";
        label.textContent = pin.label || "";
        a.appendChild(wrap);
        a.appendChild(label);
        host.appendChild(a);
      });
    });
    document.querySelectorAll(".nav-pin-btn").forEach(function (btn) {
      var href = btn.getAttribute("data-pin-href");
      var on = pins.some(function (pin) { return pin.href === href; });
      btn.classList.toggle("is-pinned", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      var icon = btn.querySelector("i");
      if (icon) icon.className = on ? "bi bi-star-fill" : "bi bi-star";
    });
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".nav-pin-btn");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    var href = btn.getAttribute("data-pin-href");
    var label = btn.getAttribute("data-pin-label");
    var icon = btn.getAttribute("data-pin-icon");
    if (!href || !label) return;
    var pins = readJson(PIN_KEY);
    var exists = pins.some(function (pin) { return pin.href === href; });
    pins = exists ? pins.filter(function (pin) { return pin.href !== href; }) : pins.concat([{ href: href, label: label, icon: icon }]);
    writeJson(PIN_KEY, pins.slice(0, 8));
    paintPins();
  });

  document.addEventListener("click", function (ev) {
    var link = ev.target.closest("[data-recent]");
    if (!link) return;
    remember({
      href: link.getAttribute("href"),
      label: link.getAttribute("data-recent-label") || link.textContent,
      kind: link.getAttribute("data-recent-kind") || "recente",
      icon: link.getAttribute("data-recent-icon") || "bi-clock-history"
    });
  });

  var palette = document.getElementById("evaluaPalette");
  var paletteInput = document.getElementById("evaluaPaletteInput");
  var paletteList = document.getElementById("evaluaPaletteList");
  var activeIndex = 0;
  var paletteItems = [];
  var searchTimer = 0;

  function openPalette() {
    if (!palette || !palette.showModal) return;
    if (!palette.open) palette.showModal();
    if (paletteInput) {
      paletteInput.value = "";
      paletteInput.focus();
    }
    renderPalette([], [], true);
    fetchPalette("");
  }

  function closePalette() {
    if (palette && palette.open) palette.close();
  }

  function renderPalette(actions, results, loading) {
    if (!paletteList) return;
    paletteList.innerHTML = "";
    paletteItems = [];
    var recents = paletteInput && paletteInput.value.trim() ? [] : readJson(RECENT_KEY).slice(0, 5);

    function addGroup(title, rows) {
      if (!rows.length) return;
      var h = document.createElement("div");
      h.className = "evalua-palette-group";
      h.textContent = title;
      paletteList.appendChild(h);
      rows.forEach(function (row) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "evalua-palette-item";
        b.innerHTML = '<span class="evalua-palette-ico"><i class="bi"></i></span><span><strong></strong><small></small></span>';
        b.querySelector("i").className = "bi " + (row.icon || "bi-arrow-return-right");
        b.querySelector("strong").textContent = row.label || "";
        b.querySelector("small").textContent = row.detail || row.kind || "";
        b.addEventListener("click", function () {
          remember(row);
          window.location.href = row.href;
        });
        paletteList.appendChild(b);
        paletteItems.push(b);
      });
    }

    addGroup("Recientes", recents.map(function (row) {
      return { href: row.href, label: row.label, detail: "Visto hace poco", icon: row.icon || "bi-clock-history", kind: row.kind };
    }));
    addGroup("Acciones", actions);
    addGroup("Registros", results);
    if (!paletteItems.length) {
      var empty = document.createElement("div");
      empty.className = "text-muted small px-2 py-3";
      empty.textContent = loading ? "Buscando…" : "Sin coincidencias. Pruebe un RUT, un número de nota o el nombre de una acción.";
      paletteList.appendChild(empty);
    }
    activeIndex = 0;
    markActive();
  }

  function markActive() {
    paletteItems.forEach(function (el, i) {
      el.classList.toggle("is-active", i === activeIndex);
    });
    var current = paletteItems[activeIndex];
    if (current && current.scrollIntoView) current.scrollIntoView({ block: "nearest" });
  }

  function fetchPalette(q) {
    var url = "/api/v1/search?q=" + encodeURIComponent(q || "");
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (res) {
        if (!res.ok) throw new Error("search");
        return res.json();
      })
      .then(function (data) {
        if (!paletteInput || paletteInput.value.trim() !== (q || "")) return;
        renderPalette(data.actions || [], data.results || [], false);
      })
      .catch(function () {
        renderPalette([], [], false);
      });
  }

  document.querySelectorAll("[data-command-open]").forEach(function (btn) {
    btn.addEventListener("click", openPalette);
  });

  document.addEventListener("keydown", function (ev) {
    var tag = (ev.target && ev.target.tagName) || "";
    var typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (ev.target && ev.target.isContentEditable);
    if ((ev.ctrlKey || ev.metaKey) && norm(ev.key) === "k") {
      ev.preventDefault();
      openPalette();
      return;
    }
    if (!typing && ev.key === "/" && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
      ev.preventDefault();
      openPalette();
    }
    if (!palette || !palette.open) return;
    if (ev.key === "Escape") {
      ev.preventDefault();
      closePalette();
    } else if (ev.key === "ArrowDown") {
      ev.preventDefault();
      activeIndex = Math.min(paletteItems.length - 1, activeIndex + 1);
      markActive();
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      activeIndex = Math.max(0, activeIndex - 1);
      markActive();
    } else if (ev.key === "Enter" && paletteItems[activeIndex]) {
      ev.preventDefault();
      paletteItems[activeIndex].click();
    }
  });

  if (paletteInput) {
    paletteInput.addEventListener("input", function () {
      window.clearTimeout(searchTimer);
      var q = paletteInput.value.trim();
      renderPalette([], [], true);
      searchTimer = window.setTimeout(function () { fetchPalette(q); }, 160);
    });
  }

  var confirmDialog = document.getElementById("evaluaConfirm");
  var confirmTitle = document.getElementById("evaluaConfirmTitle");
  var confirmText = document.getElementById("evaluaConfirmText");
  var confirmOk = document.getElementById("evaluaConfirmOk");
  var confirmCancel = document.getElementById("evaluaConfirmCancel");
  var pendingForm = null;

  function legacyConfirm(form) {
    var raw = form.getAttribute("onsubmit") || "";
    var match = raw.match(/confirm\(\s*(['"])([\s\S]*?)\1\s*\)/);
    if (!match) return;
    form.removeAttribute("onsubmit");
    form.dataset.confirmTitle = "Confirme la acción";
    form.dataset.confirmBody = match[2].replace(/\\n/g, "\n");
    form.dataset.confirmOk = "Continuar";
  }

  document.querySelectorAll("form[onsubmit]").forEach(legacyConfirm);

  function askConfirm(form) {
    var title = form.dataset.confirmTitle || "Confirme la acción";
    var body = form.dataset.confirmBody || "Esta acción no se puede deshacer desde esta pantalla.";
    var okLabel = form.dataset.confirmOk || "Continuar";
    if (!confirmDialog || !confirmDialog.showModal) {
      return window.confirm(title + "\n\n" + body);
    }
    confirmTitle.textContent = title;
    confirmText.textContent = body;
    confirmOk.textContent = okLabel;
    confirmOk.classList.toggle("btn-danger", form.dataset.confirmTone !== "primary");
    confirmOk.classList.toggle("btn-primary", form.dataset.confirmTone === "primary");
    pendingForm = form;
    confirmDialog.showModal();
    return null;
  }

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.confirmed === "1") return;
    if (!form.dataset.confirmTitle && !form.dataset.confirmBody) return;
    ev.preventDefault();
    ev.stopPropagation();
    var sync = askConfirm(form);
    if (sync === true) {
      form.dataset.confirmed = "1";
      form.submit();
    }
  }, true);

  if (confirmOk) {
    confirmOk.addEventListener("click", function () {
      var form = pendingForm;
      pendingForm = null;
      if (confirmDialog && confirmDialog.open) confirmDialog.close();
      if (!form) return;
      form.dataset.confirmed = "1";
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    });
  }
  if (confirmCancel) {
    confirmCancel.addEventListener("click", function () {
      pendingForm = null;
      if (confirmDialog && confirmDialog.open) confirmDialog.close();
    });
  }

  paintPins();
  paintRecents();
})();
