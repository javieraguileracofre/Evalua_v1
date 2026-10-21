/* Listados que filtran sin recargar el layout, y búsqueda de registros en formularios. */
(function () {
  function closestLive(node) {
    return node && node.closest ? node.closest("[data-live-list]") : null;
  }

  function listUrl(form) {
    var action = form.getAttribute("action") || window.location.pathname;
    var params = new URLSearchParams(new FormData(form));
    var skip = form.querySelector('input[name="skip"]');
    if (skip && form.dataset.liveKeepSkip !== "1") params.set("skip", "0");
    var qs = params.toString();
    return qs ? action + "?" + qs : action;
  }

  function samePath(url) {
    try {
      return new URL(url, window.location.href).pathname === window.location.pathname;
    } catch (e) {
      return false;
    }
  }

  function loadList(root, url, push) {
    if (!root || root.dataset.liveLoading === "1") return;
    root.dataset.liveLoading = "1";
    root.setAttribute("aria-busy", "true");
    fetch(url, { credentials: "same-origin", headers: { Accept: "text/html" } })
      .then(function (res) {
        if (res.redirected && res.url.indexOf("/login") !== -1) {
          window.location.href = res.url;
          return null;
        }
        if (!res.ok) throw new Error("list");
        return res.text();
      })
      .then(function (html) {
        if (!html) return;
        var doc = new DOMParser().parseFromString(html, "text/html");
        var next = doc.querySelector("[data-live-results]");
        var current = root.querySelector("[data-live-results]");
        if (!next || !current) {
          window.location.href = url;
          return;
        }
        current.replaceWith(next);
        syncExports(next);
        syncForm(root, url);
        if (push) history.pushState({ evaluaLive: 1 }, "", url);
        document.dispatchEvent(new CustomEvent("evalua:list-updated"));
      })
      .catch(function () {
        window.location.href = url;
      })
      .finally(function () {
        root.dataset.liveLoading = "0";
        root.removeAttribute("aria-busy");
      });
  }

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-live-form")) return;
    ev.preventDefault();
    var root = closestLive(form);
    loadList(root, listUrl(form), true);
  });

  var timer = 0;
  document.addEventListener("input", function (ev) {
    var form = ev.target && ev.target.form;
    if (!form || !form.hasAttribute("data-live-form")) return;
    if (ev.target.type === "checkbox" || ev.target.tagName === "SELECT") return;
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      loadList(closestLive(form), listUrl(form), true);
    }, 220);
  });

  document.addEventListener("change", function (ev) {
    var form = ev.target && ev.target.form;
    if (!form || !form.hasAttribute("data-live-form")) return;
    loadList(closestLive(form), listUrl(form), true);
  });

  document.addEventListener("click", function (ev) {
    var link = ev.target.closest("a");
    if (!link || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    if (link.target === "_blank" || link.hasAttribute("download")) return;
    try {
      var dest = new URL(link.href, window.location.href);
      var here = new URL(window.location.href);
      if (dest.hash && dest.pathname === here.pathname && dest.search === here.search) return;
    } catch (e) {
      return;
    }
    var root = closestLive(link);
    if (!root) return;
    var insideResults = link.closest("[data-live-results]");
    var reset = link.hasAttribute("data-live-reset");
    var liveLink = link.hasAttribute("data-live-link");
    if (!insideResults && !reset && !liveLink) return;
    if (!samePath(link.href)) return;
    ev.preventDefault();
    loadList(root, link.href, true);
  });

    window.addEventListener("popstate", function () {
      var root = document.querySelector("[data-live-list]");
      if (!root) return;
      syncForm(root, window.location.href);
      loadList(root, window.location.href, false);
    });

    function syncExports(results) {
      if (!results || !results.querySelectorAll) return;
      results.querySelectorAll("[data-live-export-for]").forEach(function (node) {
        var target = document.getElementById(node.getAttribute("data-live-export-for"));
        var href = node.getAttribute("data-href");
        if (target && href) target.setAttribute("href", href);
      });
    }

    function syncForm(root, url) {
      var form = root.querySelector("[data-live-form]");
      if (!form) return;
      var params = new URL(url, window.location.href).searchParams;
      Array.prototype.forEach.call(form.elements, function (el) {
        if (!el.name || el.type === "submit" || el.type === "button") return;
        if (el.type === "checkbox") {
          el.checked = params.get(el.name) === el.value;
          return;
        }
        if (params.has(el.name)) el.value = params.get(el.name) || "";
        else if (el.type !== "hidden") el.value = "";
      });
    }

  document.addEventListener("click", function (ev) {
    var row = ev.target.closest("tr[data-row-href]");
    if (!row || ev.target.closest("a, button, input, select, textarea, form, label")) return;
    window.location.href = row.getAttribute("data-row-href");
  });

  function lookupUrl(box, q) {
    var base = box.getAttribute("data-lookup-url");
    return base + (base.indexOf("?") === -1 ? "?" : "&") + "q=" + encodeURIComponent(q);
  }

  document.querySelectorAll("[data-lookup]").forEach(function (box) {
    var input = box.querySelector("[data-lookup-input]");
    var hidden = box.querySelector("[data-lookup-value]");
    var menu = box.querySelector("[data-lookup-menu]");
    var error = box.querySelector("[data-lookup-error]");
    if (!input || !hidden || !menu) return;
    var wait = 0;
    var items = [];
    var active = -1;

    function showError(text) {
      if (!error) return;
      error.textContent = text || "";
    }

    function choose(item) {
      hidden.value = String(item.id);
      input.value = item.label;
      menu.hidden = true;
      showError("");
      input.setCustomValidity("");
    }

    function paint() {
      menu.innerHTML = "";
      if (!items.length) {
        menu.hidden = true;
        return;
      }
      items.forEach(function (item, index) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "evalua-lookup-item" + (index === active ? " is-active" : "");
        btn.textContent = item.label;
        btn.addEventListener("mousedown", function (ev) {
          ev.preventDefault();
          choose(item);
        });
        menu.appendChild(btn);
      });
      menu.hidden = false;
    }

    input.addEventListener("input", function () {
      hidden.value = "";
      showError("");
      window.clearTimeout(wait);
      var q = input.value.trim();
      if (q.length < 2) {
        items = [];
        paint();
        return;
      }
      wait = window.setTimeout(function () {
        fetch(lookupUrl(box, q), { credentials: "same-origin", headers: { Accept: "application/json" } })
          .then(function (res) { return res.ok ? res.json() : []; })
          .then(function (data) {
            items = Array.isArray(data) ? data : [];
            active = items.length ? 0 : -1;
            paint();
            if (!items.length) showError("No hay coincidencias. Pruebe otro RUT o cree el cliente.");
          })
          .catch(function () {
            showError("No se pudo buscar. Intente de nuevo.");
          });
      }, 180);
    });

    input.addEventListener("keydown", function (ev) {
      if (menu.hidden || !items.length) return;
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        active = Math.min(items.length - 1, active + 1);
        paint();
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        active = Math.max(0, active - 1);
        paint();
      } else if (ev.key === "Enter" && items[active]) {
        ev.preventDefault();
        choose(items[active]);
      } else if (ev.key === "Escape") {
        menu.hidden = true;
      }
    });

    input.addEventListener("blur", function () {
      window.setTimeout(function () { menu.hidden = true; }, 150);
    });
  });
})();
