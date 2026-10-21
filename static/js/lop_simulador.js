(function () {
  "use strict";

  const form = document.getElementById("lop-sim-form");
  if (!form) return;

  const BOOT = window.LOP_BOOT || {
    tipos: [],
    marcas: [],
    modelos: [],
    catalogo: null,
    anios: [],
    tiposUso: [],
    defaultTipoId: 0,
    paramsByTipo: {},
  };

  const API_PREVIEW = "/api/comercial/leasing-operativo/simular/preview";
  const API_RESIDUAL = "/api/comercial/leasing-operativo/cotizacion/estimar-residual";
  const API_OVERRIDE = "/api/comercial/leasing-operativo/residual-value/override";
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrf = csrfMeta ? csrfMeta.getAttribute("content") || "" : "";

  const unitsEl = document.getElementById("lop-units");
  const residualsEl = document.getElementById("lop-residuals");
  const summaryEl = document.getElementById("lop-summary-body");
  const previewBody = document.getElementById("lop-preview-body");
  const previewStatus = document.getElementById("lop-preview-status");
  const hiddenUnits = document.getElementById("unidades_json");
  const hiddenTipo = document.getElementById("tipo_activo_id_hidden");
  const btnPrev = document.getElementById("lop-wizard-prev");
  const btnNext = document.getElementById("lop-wizard-next");
  const btnSave = document.getElementById("lop-save-btn");
  const btnAdd = document.getElementById("lop-add-unit");
  const btnReest = document.getElementById("lop-reestimate");
  const kpiUnits = document.getElementById("lop-kpi-units");
  const kpiRenta = document.getElementById("lop-kpi-renta");
  const panels = Array.from(form.querySelectorAll("[data-lop-panel]"));

  let currentStep = 1;
  let units = [];
  let timer = null;
  let inflight = null;
  let lastResult = null;

  function uid() {
    return "u-" + Math.random().toString(36).slice(2, 9);
  }

  function fmt(n) {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
    return Math.round(Number(n)).toLocaleString("es-CL");
  }

  function money(n) {
    return "$" + fmt(n);
  }

  function val(name) {
    const el = form.querySelector('[name="' + name + '"]');
    return el ? el.value : "";
  }

  function num(name, def) {
    const v = parseFloat(String(val(name)).replace(",", "."));
    return Number.isFinite(v) ? v : def;
  }

  function tipoCodigo(tipoId) {
    const t = (BOOT.tipos || []).find(function (x) {
      return String(x.id) === String(tipoId);
    });
    return (t && t.codigo) || "";
  }

  function catalogoTipo(tipoId) {
    const cat = BOOT.catalogo || {};
    const porTipo = cat.por_tipo || {};
    const cod = tipoCodigo(tipoId);
    if (cod && porTipo[cod]) return porTipo[cod];
    // Fallback: primer tipo conocido o mapa plano legado.
    const keys = Object.keys(porTipo);
    if (keys.length) return porTipo[keys[0]];
    return null;
  }

  function marcasParaTipo(tipoId) {
    const map = catalogoTipo(tipoId);
    if (!map) return BOOT.marcas && BOOT.marcas.length ? BOOT.marcas.slice() : ["Otro"];
    const marcas = Object.keys(map).filter(function (m) {
      return m !== "Otro";
    });
    marcas.sort(function (a, b) {
      return a.localeCompare(b, "es");
    });
    marcas.push("Otro");
    return marcas;
  }

  function modelosParaMarca(tipoId, marca) {
    const map = catalogoTipo(tipoId);
    const m = (marca || "").trim() || "Otro";
    if (map && map[m] && map[m].length) return map[m].slice();
    if (map) {
      // Misma marca en otro segmento del catálogo boot.
      const porTipo = (BOOT.catalogo && BOOT.catalogo.por_tipo) || {};
      for (const cod of Object.keys(porTipo)) {
        if (porTipo[cod][m] && porTipo[cod][m].length) return porTipo[cod][m].slice();
      }
    }
    return BOOT.modelos && BOOT.modelos.length ? BOOT.modelos.slice() : ["Otro"];
  }

  function syncMarcaModelo(u, resetIfInvalid) {
    const marcas = marcasParaTipo(u.tipo_activo_id);
    if (!u.marca) {
      u.marca = marcas[0] || "Otro";
    } else if (resetIfInvalid && !marcas.includes(u.marca)) {
      u.marca = marcas[0] || "Otro";
    }
    const modelos = modelosParaMarca(u.tipo_activo_id, u.marca);
    if (!u.modelo) {
      u.modelo = modelos[0] || "Otro";
    } else if (resetIfInvalid && !modelos.includes(u.modelo)) {
      u.modelo = modelos[0] || "Otro";
    }
    u.descripcion = [u.marca, u.modelo, u.anio].filter(Boolean).join(" ");
    return u;
  }

  function defaultUnit() {
    const tid = BOOT.defaultTipoId || (BOOT.tipos[0] && BOOT.tipos[0].id) || 0;
    const p = BOOT.paramsByTipo[String(tid)] || {};
    const km = (p.perfil && p.perfil.uso && p.perfil.uso.km_anual) || 40000;
    const marcas = marcasParaTipo(tid);
    const marca = marcas[0] || "";
    const modelos = modelosParaMarca(tid, marca);
    return {
      id: uid(),
      tipo_activo_id: tid,
      descripcion: "",
      marca: marca,
      modelo: modelos[0] || "",
      anio: BOOT.anios[BOOT.anios.length - 2] || new Date().getFullYear(),
      cantidad: 1,
      valor_bien: 0,
      tipo_uso: "INTERURBANO",
      km_anual: Number(km) || 40000,
      km_inicial: 0,
      residual_sugerido: 0,
      residual_aceptado: 0,
      residual_fuente: "modelo_interno",
      residual_estimacion: null,
    };
  }

  function syncHidden() {
    if (hiddenUnits) hiddenUnits.value = JSON.stringify(units);
    if (hiddenTipo && units[0]) hiddenTipo.value = String(units[0].tipo_activo_id || "");
    const total = units.reduce(function (a, u) {
      return a + (parseInt(u.cantidad, 10) || 1);
    }, 0);
    if (kpiUnits) kpiUnits.textContent = String(total);
    if (btnSave) btnSave.disabled = !(units.length && currentStep >= 3);
  }

  function optionsHtml(list, selected, mapFn) {
    return list
      .map(function (item) {
        const o = mapFn ? mapFn(item) : { value: item, label: item };
        const sel = String(o.value) === String(selected) ? " selected" : "";
        return '<option value="' + o.value + '"' + sel + ">" + o.label + "</option>";
      })
      .join("");
  }

  function renderUnits() {
    if (!unitsEl) return;
    if (!units.length) {
      unitsEl.innerHTML =
        '<div class="lo-empty">Sin unidades. Pulse «Agregar unidad» para comenzar (puede cotizar 1, 2 o más).</div>';
      syncHidden();
      return;
    }
    unitsEl.innerHTML = units
      .map(function (u, idx) {
        syncMarcaModelo(u, false);
        const marcasBase = marcasParaTipo(u.tipo_activo_id);
        const marcas = marcasBase.includes(u.marca) ? marcasBase : marcasBase.concat([u.marca]);
        const modelos = modelosParaMarca(u.tipo_activo_id, u.marca);
        // Cotizaciones antiguas: conservar modelo fuera de catálogo en el select.
        const modelosOpts = modelos.includes(u.modelo) ? modelos : modelos.concat([u.modelo]);
        const fuente =
          (BOOT.catalogo && BOOT.catalogo.fuente) || "Mercado Chile (oferta / liquidez local)";
        return (
          '<article class="lo-unit-card" data-uid="' +
          u.id +
          '">' +
          '<div class="lo-unit-card-top">' +
          "<strong>Unidad " +
          (idx + 1) +
          "</strong>" +
          '<button type="button" class="btn btn-sm btn-link text-danger lop-remove-unit" data-uid="' +
          u.id +
          '">Quitar</button>' +
          "</div>" +
          '<div class="row g-2">' +
          '<div class="col-md-4"><label class="form-label">Tipo de activo</label>' +
          '<select class="form-select lop-f" data-f="tipo_activo_id" data-uid="' +
          u.id +
          '">' +
          optionsHtml(BOOT.tipos, u.tipo_activo_id, function (t) {
            return { value: t.id, label: t.nombre };
          }) +
          "</select></div>" +
          '<div class="col-md-2"><label class="form-label">Cantidad</label>' +
          '<input type="number" min="1" max="500" class="form-control lop-f" data-f="cantidad" data-uid="' +
          u.id +
          '" value="' +
          (u.cantidad || 1) +
          '" /></div>' +
          '<div class="col-md-3"><label class="form-label">Valor del bien</label>' +
          '<input type="number" min="0" step="1000" class="form-control lop-f" data-f="valor_bien" data-uid="' +
          u.id +
          '" value="' +
          (u.valor_bien || 0) +
          '" /></div>' +
          '<div class="col-md-3"><label class="form-label">Tipo de uso</label>' +
          '<select class="form-select lop-f" data-f="tipo_uso" data-uid="' +
          u.id +
          '">' +
          optionsHtml(BOOT.tiposUso, u.tipo_uso, function (t) {
            return { value: t.codigo, label: t.label };
          }) +
          "</select></div>" +
          '<div class="col-md-3"><label class="form-label">Marca</label>' +
          '<select class="form-select lop-f" data-f="marca" data-uid="' +
          u.id +
          '">' +
          optionsHtml(marcas, u.marca) +
          "</select></div>" +
          '<div class="col-md-3"><label class="form-label">Modelo</label>' +
          '<select class="form-select lop-f" data-f="modelo" data-uid="' +
          u.id +
          '">' +
          optionsHtml(modelosOpts, u.modelo) +
          '</select><div class="form-text">' +
          escapeHtml(fuente) +
          "</div></div>" +
          '<div class="col-md-2"><label class="form-label">Año</label>' +
          '<select class="form-select lop-f" data-f="anio" data-uid="' +
          u.id +
          '">' +
          optionsHtml(BOOT.anios, u.anio) +
          "</select></div>" +
          '<div class="col-md-2"><label class="form-label">Km anuales</label>' +
          '<input type="number" min="0" class="form-control lop-f" data-f="km_anual" data-uid="' +
          u.id +
          '" value="' +
          (u.km_anual || 0) +
          '" /></div>' +
          '<div class="col-md-2"><label class="form-label">Km actuales</label>' +
          '<input type="number" min="0" class="form-control lop-f" data-f="km_inicial" data-uid="' +
          u.id +
          '" value="' +
          (u.km_inicial || 0) +
          '" /></div>' +
          "</div></article>"
        );
      })
      .join("");
    syncHidden();
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function proxiedImageUrl(raw) {
    const src = String(raw || "").trim();
    if (!src || src.indexOf("https://") !== 0) return "";
    return "/api/comercial/leasing-operativo/cotizacion/market-image?u=" + encodeURIComponent(src);
  }

  function renderComps(est) {
    const comps = est.comparables || [];
    const portales = est.portales || [];
    const urls = est.search_urls || {};
    const stats = est.stats || {};
    let portalsHtml = portales
      .map(function (p) {
        const ok = p.ok ? "ok" : "fail";
        const link = p.search_url
          ? '<a href="' +
            escapeHtml(p.search_url) +
            '" target="_blank" rel="noopener">abrir búsqueda</a>'
          : "";
        return (
          '<span class="lo-portal-chip ' +
          ok +
          '"><strong>' +
          escapeHtml(p.portal) +
          "</strong> · " +
          (p.ok ? p.count + " avisos" : p.error || "sin datos") +
          " " +
          link +
          "</span>"
        );
      })
      .join("");
    if (!portalsHtml && urls.chileautos) {
      portalsHtml =
        '<a class="lo-portal-chip ok" href="' +
        escapeHtml(urls.chileautos) +
        '" target="_blank" rel="noopener">chileautos</a>' +
        '<a class="lo-portal-chip ok" href="' +
        escapeHtml(urls.autocosmos || "#") +
        '" target="_blank" rel="noopener">autocosmos</a>' +
        '<a class="lo-portal-chip ok" href="' +
        escapeHtml(urls.mercadolibre || "#") +
        '" target="_blank" rel="noopener">mercadolibre</a>';
    }
    const cards = comps
      .slice(0, 8)
      .map(function (c) {
        const proxied = proxiedImageUrl(c.image_url);
        const img = proxied
          ? '<img src="' +
            escapeHtml(proxied) +
            '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement(\'div\'),{className:\'lo-comp-ph\',textContent:\'Sin foto\'}))" />'
          : '<div class="lo-comp-ph">Sin foto</div>';
        return (
          '<a class="lo-comp-card" href="' +
          escapeHtml(c.url || "#") +
          '" target="_blank" rel="noopener">' +
          '<div class="lo-comp-img">' +
          img +
          "</div>" +
          '<div class="lo-comp-body">' +
          '<div class="lo-comp-portal">' +
          escapeHtml(c.portal || "") +
          "</div>" +
          '<div class="lo-comp-title">' +
          escapeHtml(c.title || "") +
          "</div>" +
          '<div class="lo-comp-meta">' +
          (c.year || "—") +
          " · " +
          (c.km != null ? fmt(c.km) + " km" : "km n/d") +
          "</div>" +
          '<div class="lo-comp-price">' +
          money(c.price) +
          "</div>" +
          (c.comparability_score
            ? '<div class="lo-comp-score">Score ' + Math.round(c.comparability_score) + "/100</div>"
            : "") +
          "</div></a>"
        );
      })
      .join("");
    return (
      '<div class="lo-market-block mt-3">' +
      '<div class="d-flex flex-wrap justify-content-between gap-2 align-items-center mb-2">' +
      "<div><strong>Respaldo de mercado (auditable)</strong>" +
      '<div class="form-text mb-0">Avisos con link e imagen. Mercado actual ponderado: <strong>' +
      money(stats.valor_mercado_actual || stats.mediana) +
      "</strong> · n=" +
      (stats.n || comps.length || 0) +
      " · fuente: " +
      escapeHtml(est.fuente || "") +
      "</div></div>" +
      '<div class="lo-portal-row">' +
      portalsHtml +
      "</div></div>" +
      (cards
        ? '<div class="lo-comp-grid">' + cards + "</div>"
        : '<div class="lo-empty">Sin fotos en vivo; use los links de búsqueda de cada portal.</div>') +
      "</div>"
    );
  }

  function dealTone(decision) {
    const d = String(decision || "").toUpperCase();
    if (d.indexOf("NO RECOMENDADO") >= 0) return "danger";
    if (d.indexOf("REVISAR") >= 0 || d.indexOf("PENDIENTE") >= 0) return "warn";
    if (d.indexOf("CONDICIONES") >= 0) return "mid";
    if (d.indexOf("APROBAR") >= 0) return "ok";
    return "mid";
  }

  function renderAnalisisResidual(est) {
    const esc = est.escenarios || {};
    const riesgo = est.riesgo || {};
    const conf = est.confianza || {};
    const deal = est.deal || {};
    const rent = est.rentabilidad || {};
    const panel = est.panel_ejecutivo || {};
    const layers = est.layers || {};
    const book = layers.BOOK_VALUE || {};
    const tax = layers.TAX_VALUE || {};
    const tone = dealTone(deal.DECISION);
    const tirTxt =
      rent.tir_anual_pct != null && rent.tir_anual_pct !== ""
        ? Number(rent.tir_anual_pct).toFixed(2) + "%"
        : "—";
    const margenTxt =
      rent.margen_operacional_promedio_pct != null && rent.margen_operacional_promedio_pct !== ""
        ? Number(rent.margen_operacional_promedio_pct).toFixed(2) + "%"
        : "—";
    return (
      '<div class="lo-rv-panel mt-3">' +
      '<div class="lo-rv-panel-title">Análisis de valor residual · ' +
      escapeHtml(est.model_version || "") +
      (est.deal_con_pricing ? " · con pricing" : "") +
      "</div>" +
      '<div class="lo-rv-flow">' +
      "<div><span>Adquisición</span><strong>" +
      money(panel.precio_adquisicion || est.PRECIO_COMPRA || est.valor_bien) +
      "</strong></div>" +
      "<div><span>Mercado actual</span><strong>" +
      money(est.VALOR_MERCADO_ACTUAL) +
      "</strong></div>" +
      "<div><span>Mercado proyectado</span><strong>" +
      money(panel.valor_mercado_proyectado || est.valor_residual_sugerido) +
      "</strong></div>" +
      "<div><span>Costos recupero</span><strong>" +
      money(panel.costos_recuperacion) +
      "</strong></div>" +
      "<div><span>Recupero neto</span><strong>" +
      money(est.VALOR_RECUPERO_NETO) +
      "</strong></div>" +
      "<div><span>Resultado venta</span><strong>" +
      money(est.RESULTADO_ESPERADO_VENTA) +
      "</strong></div>" +
      "</div>" +
      '<div class="lo-rv-scenarios">' +
      '<div class="lo-rv-sc cons"><span>Conservador</span><strong>' +
      money(esc.CONSERVADOR) +
      "</strong></div>" +
      '<div class="lo-rv-sc base"><span>Base</span><strong>' +
      money(esc.BASE || est.valor_residual_sugerido) +
      "</strong></div>" +
      '<div class="lo-rv-sc opt"><span>Optimista</span><strong>' +
      money(esc.OPTIMISTA) +
      "</strong></div>" +
      "</div>" +
      '<div class="lo-rv-kpis">' +
      "<div><span>Valor libro</span><strong>" +
      money(est.VALOR_LIBROS_FINAL || book.valor) +
      "</strong></div>" +
      "<div><span>Valor tributario</span><strong>" +
      money(tax.valor) +
      "</strong></div>" +
      "<div><span>Confianza</span><strong>" +
      escapeHtml(conf.display || "—") +
      "</strong></div>" +
      "<div><span>Riesgo residual</span><strong>" +
      escapeHtml(riesgo.RESIDUAL_RISK_LEVEL || "—") +
      "</strong></div>" +
      "<div><span>TIR anual</span><strong>" +
      tirTxt +
      "</strong></div>" +
      "<div><span>VAN</span><strong>" +
      money(rent.van) +
      "</strong></div>" +
      "<div><span>Margen op.</span><strong>" +
      margenTxt +
      "</strong></div>" +
      "<div><span>Renta sugerida</span><strong>" +
      money(rent.renta_sugerida) +
      "</strong></div>" +
      "</div>" +
      '<div class="lo-rv-decision lo-rv-decision--' +
      tone +
      '">' +
      "<div><span>Deal score</span><strong>" +
      (deal.DEAL_SCORE != null ? deal.DEAL_SCORE + " · " + escapeHtml(deal.DEAL_CLASS || "") : "—") +
      "</strong></div>" +
      "<div><span>Recomendación</span><strong>" +
      escapeHtml(deal.DECISION || "Calcule residual y pricing") +
      "</strong></div>" +
      "</div>" +
      (est.MANUAL_OVERRIDE
        ? '<div class="lo-rv-warn">El valor residual fue modificado manualmente respecto del modelo de mercado.</div>'
        : "") +
      (!est.deal_con_pricing
        ? '<p class="form-text mb-0 mt-2">Tras estimar residual se calcula la renta para completar TIR, VAN y recomendación.</p>'
        : "") +
      "</div>"
    );
  }

  function renderResiduals() {
    if (!residualsEl) return;
    if (!units.length) {
      residualsEl.innerHTML = '<div class="lo-empty">Primero agregue unidades.</div>';
      return;
    }
    residualsEl.innerHTML = units
      .map(function (u, idx) {
        const est = u.residual_estimacion || {};
        const capital = Math.max(0, Number(u.valor_bien || 0) - Number(u.residual_aceptado || 0));
        return (
          '<article class="lo-residual-card" data-uid="' +
          u.id +
          '">' +
          '<div class="lo-residual-card-top">' +
          "<div><strong>Unidad " +
          (idx + 1) +
          "</strong> · " +
          (u.marca || "") +
          " " +
          (u.modelo || "") +
          " · ×" +
          (u.cantidad || 1) +
          '</div><span class="badge text-bg-light border">' +
          (est.tipo_uso_label || u.tipo_uso || "") +
          "</span></div>" +
          renderAnalisisResidual(est) +
          '<div class="row g-3 align-items-end mt-1">' +
          '<div class="col-md-3"><div class="lo-mini-kpi"><span>Valor bien</span><strong>' +
          money(u.valor_bien) +
          "</strong></div></div>" +
          '<div class="col-md-3"><div class="lo-mini-kpi"><span>Km al término</span><strong>' +
          fmt(est.km_fin_estimado || est.KM_FINAL_ESTIMADO) +
          "</strong></div></div>" +
          '<div class="col-md-3"><div class="lo-mini-kpi"><span>Edad al término</span><strong>' +
          (est.edad_fin_anios != null ? est.edad_fin_anios + " años" : "—") +
          "</strong></div></div>" +
          '<div class="col-md-3"><div class="lo-mini-kpi"><span>Residual sugerido</span><strong>' +
          money(u.residual_sugerido) +
          "</strong></div></div>" +
          '<div class="col-md-4"><label class="form-label">Residual aceptado (editable)</label>' +
          '<input type="number" min="0" class="form-control form-control-lg lop-f" data-f="residual_aceptado" data-uid="' +
          u.id +
          '" value="' +
          (u.residual_aceptado || 0) +
          '" /></div>' +
          '<div class="col-md-4"><div class="lo-mini-kpi accent"><span>Capital a invertir (unit.)</span><strong>' +
          money(capital) +
          "</strong></div></div>" +
          '<div class="col-md-4"><button type="button" class="btn btn-outline-secondary w-100 lop-accept-residual" data-uid="' +
          u.id +
          '">Aceptar sugerido</button></div>' +
          "</div>" +
          renderComps(est) +
          (est.nota ? '<p class="form-text mb-0 mt-2">' + escapeHtml(est.nota) + "</p>" : "") +
          "</article>"
        );
      })
      .join("");
  }

  function renderSummary() {
    if (!summaryEl) return;
    const r = lastResult || {};
    const lineas = r.lineas || [];
    const flota = r.flota || {};
    if (!lineas.length && !r.renta_sugerida) {
      summaryEl.innerHTML = '<p class="text-muted mb-0">Calcule la vista previa para ver el resumen.</p>';
      return;
    }
    let rows = lineas
      .map(function (ln) {
        return (
          "<tr><td>" +
          (ln.descripcion || ln.tipo_nombre || "—") +
          "</td><td class='text-end'>" +
          (ln.cantidad || 1) +
          "</td><td class='text-end'>" +
          money(ln.valor_bien_unitario) +
          "</td><td class='text-end'>" +
          money(ln.residual_aceptado_unitario) +
          "</td><td class='text-end'>" +
          money(ln.renta_unitaria) +
          "</td><td class='text-end fw-semibold'>" +
          money(ln.renta_linea) +
          "</td></tr>"
        );
      })
      .join("");
    if (!rows) {
      rows =
        "<tr><td colspan='6' class='text-muted'>Cotización de una unidad (sin desglose de flota).</td></tr>";
    }
    const ev = r.evaluacion_economica || {};
    const deal = ev.deal || {};
    const tone = dealTone(ev.decision || deal.DECISION);
    summaryEl.innerHTML =
      '<div class="lo-summary-kpis">' +
      '<div><span>Unidades</span><strong>' +
      (flota.unidades_totales || units.reduce(function (a, u) { return a + (u.cantidad || 1); }, 0)) +
      "</strong></div>" +
      "<div><span>Inversión (CAPEX)</span><strong>" +
      money(r.capex_total) +
      "</strong></div>" +
      "<div><span>Residual flota</span><strong>" +
      money((r.valor_residual || {}).valor_residual_ajustado) +
      "</strong></div>" +
      "<div><span>Capital amortizable</span><strong>" +
      money(r.capital_amortizable) +
      "</strong></div>" +
      "<div class='accent'><span>Renta mensual flota</span><strong>" +
      money(r.renta_sugerida) +
      "</strong></div>" +
      "<div><span>Renta + IVA</span><strong>" +
      money(r.renta_mensual_bruta) +
      "</strong></div>" +
      "<div><span>TIR anual</span><strong>" +
      (r.tir_anual_pct != null ? Number(r.tir_anual_pct).toFixed(2) + "%" : "—") +
      "</strong></div>" +
      "<div><span>VAN</span><strong>" +
      money(r.van) +
      "</strong></div>" +
      "</div>" +
      '<div class="lo-eval-banner lo-rv-decision--' +
      tone +
      '">' +
      "<div><strong>Evaluación económica:</strong> " +
      escapeHtml(ev.decision || deal.DECISION || (r.decision || {}).decision_codigo || "—") +
      (deal.DEAL_SCORE != null ? " · score " + deal.DEAL_SCORE : "") +
      "</div>" +
      '<div class="form-text mb-0 mt-1">TIR ' +
      (r.tir_anual_pct != null ? Number(r.tir_anual_pct).toFixed(2) + "%" : "—") +
      " · VAN " +
      money(r.van) +
      " · Margen " +
      (r.margen_operacional_promedio_pct != null
        ? Number(r.margen_operacional_promedio_pct).toFixed(2) + "%"
        : "—") +
      "</div></div>" +
      '<div class="table-responsive mt-3"><table class="table table-sm lo-table">' +
      "<thead><tr><th>Línea</th><th class='text-end'>Cant.</th><th class='text-end'>Valor</th><th class='text-end'>Residual</th><th class='text-end'>Renta unit.</th><th class='text-end'>Renta línea</th></tr></thead>" +
      "<tbody>" +
      rows +
      "</tbody></table></div>";
  }

  function renderPreview(result) {
    lastResult = result || {};
    const ev = (result && result.evaluacion_economica) || {};
    const dec = (result && result.decision) || {};
    if (previewStatus) {
      const code = ev.decision || dec.decision_codigo || "OK";
      const tone = dealTone(code);
      previewStatus.className =
        "badge " +
        (tone === "ok"
          ? "text-bg-success"
          : tone === "danger"
            ? "text-bg-danger"
            : tone === "warn" || tone === "mid"
              ? "text-bg-warning"
              : "text-bg-secondary");
      previewStatus.textContent = code;
    }
    if (kpiRenta) kpiRenta.textContent = money(result.renta_sugerida);
    if (!previewBody) return;
    const flota = result.flota || {};
    previewBody.innerHTML =
      '<div class="lo-preview-hero">' +
      '<div class="text-muted small">Renta mensual flota</div>' +
      '<div class="lo-preview-renta">' +
      money(result.renta_sugerida) +
      "</div>" +
      (flota.unidades_totales
        ? '<div class="text-muted small">' + flota.unidades_totales + " unidad(es)</div>"
        : "") +
      "</div>" +
      '<div class="lo-preview-grid">' +
      "<div><span>CAPEX</span><strong>" +
      money(result.capex_total) +
      "</strong></div>" +
      "<div><span>Residual</span><strong>" +
      money((result.valor_residual || {}).valor_residual_ajustado) +
      "</strong></div>" +
      "<div><span>Capital</span><strong>" +
      money(result.capital_amortizable) +
      "</strong></div>" +
      "<div><span>TIR</span><strong>" +
      (result.tir_anual_pct != null ? Number(result.tir_anual_pct).toFixed(1) + "%" : "—") +
      "</strong></div>" +
      "</div>";
    if (currentStep === 4) renderSummary();
  }

  function findUnit(id) {
    return units.find(function (u) {
      return u.id === id;
    });
  }

  function updateField(uidVal, field, value) {
    const u = findUnit(uidVal);
    if (!u) return;
    if (field === "cantidad" || field === "anio" || field === "tipo_activo_id") {
      u[field] = parseInt(value, 10) || 0;
    } else if (
      field === "valor_bien" ||
      field === "km_anual" ||
      field === "km_inicial" ||
      field === "residual_aceptado" ||
      field === "residual_sugerido"
    ) {
      u[field] = parseFloat(String(value).replace(",", ".")) || 0;
    } else {
      u[field] = value;
    }
    if (field === "tipo_activo_id" || field === "marca") {
      // Al cambiar tipo o marca, restringir modelos al catálogo chileno del segmento.
      syncMarcaModelo(u, true);
      renderUnits();
    } else if (field === "modelo" || field === "anio") {
      u.descripcion = [u.marca, u.modelo, u.anio].filter(Boolean).join(" ");
    }
    syncHidden();
    if (field === "residual_aceptado") {
      const sug = Number(u.residual_sugerido || 0);
      const acc = Number(u.residual_aceptado || 0);
      if (sug > 0 && Math.abs(acc - sug) > 1) {
        u.residual_estimacion = Object.assign({}, u.residual_estimacion || {}, {
          MANUAL_OVERRIDE: true,
          valor_residual_modelo: sug,
          advertencia_override:
            "El valor residual fue modificado manualmente respecto del modelo de mercado.",
        });
        if (!u._overridePrompted) {
          u._overridePrompted = true;
          const motivo = window.prompt(
            "Residual modificado manualmente. Indique el motivo (obligatorio para auditoría):",
            u.residual_override_motivo || ""
          );
          if (motivo && motivo.trim()) {
            u.residual_override_motivo = motivo.trim();
            const boot = window.LOP_BOOT || {};
            const cotizacionId = boot.sim_id || null;
            fetch(API_OVERRIDE, {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
              body: JSON.stringify({
                cotizacion_id: cotizacionId,
                unidad_id: u.id,
                valor_anterior: sug,
                valor_nuevo: acc,
                motivo: u.residual_override_motivo,
                observacion: "",
                model_version: (u.residual_estimacion || {}).model_version || "",
              }),
            }).catch(function () {});
          }
        }
      } else if (u.residual_estimacion) {
        u.residual_estimacion.MANUAL_OVERRIDE = false;
      }
      renderResiduals();
    }
    schedulePreview();
  }

  async function estimarResiduales() {
    if (!units.length) return;
    const plazo = parseInt(val("plazo_meses"), 10) || 36;
    try {
      if (previewStatus) {
        previewStatus.className = "badge text-bg-secondary";
        previewStatus.textContent = "Residual…";
      }
      const res = await fetch(API_RESIDUAL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ plazo_meses: plazo, unidades: units }),
      });
      if (!res.ok) {
        const err = await res.json().catch(function () {
          return {};
        });
        if (res.status === 503) {
          throw new Error(
            "El servidor estuvo ocupado consultando mercado (503). Espere unos segundos y pulse «Calcular valor residual» de nuevo."
          );
        }
        throw new Error(err.detail || "No se pudo estimar residual");
      }
      const data = await res.json();
      const next = data.unidades || [];
      units = next.map(function (nu) {
        const prev = findUnit(nu.id) || {};
        const bien = Number(nu.valor_bien || prev.valor_bien || 0);
        const prevAcc = Number(prev.residual_aceptado || 0);
        const sug = Number(nu.residual_sugerido || 0);
        const keepManual =
          prevAcc > 0 &&
          sug > 0 &&
          Math.abs(prevAcc - Number(prev.residual_sugerido || 0)) > 1 &&
          !(bien > 0 && prevAcc < bien * 0.15);
        return Object.assign({}, prev, nu, {
          residual_aceptado: keepManual ? prevAcc : sug || nu.residual_aceptado,
        });
      });
      syncHidden();
      renderResiduals();
      // Fase final: pricing inmediato (sin re-scrapear) para TIR/VAN/deal score
      if (previewStatus) previewStatus.textContent = "Pricing…";
      await runPreview();
    } catch (e) {
      if (previewBody) {
        previewBody.innerHTML = '<p class="text-danger small mb-0">' + String(e.message || e) + "</p>";
      }
      if (previewStatus) {
        previewStatus.className = "badge text-bg-danger";
        previewStatus.textContent = "Error";
      }
    }
  }

  function buildPayload() {
    syncHidden();
    const first = units[0] || {};
    return {
      tipo_activo_id: first.tipo_activo_id || BOOT.defaultTipoId || 0,
      cliente_id: val("cliente_id") ? parseInt(val("cliente_id"), 10) : null,
      plazo_meses: parseInt(val("plazo_meses"), 10) || 36,
      escenario: "BASE",
      metodo_pricing: "COSTO_SPREAD",
      spread_pct: num("spread_pct", 8),
      moneda: val("moneda") || "CLP",
      iva_pct: 19,
      unidades: units,
      inputs: {
        moneda: val("moneda") || "CLP",
        iva_pct: "19",
        market_data: {
          uf_clp: val("uf_clp"),
          usd_clp: val("usd_clp"),
          ipc_pct: val("ipc_pct"),
          source: val("market_source"),
          as_of: val("market_as_of"),
        },
        unidades: units,
        nombre: val("nombre"),
      },
    };
  }

  function schedulePreview() {
    clearTimeout(timer);
    timer = setTimeout(runPreview, 500);
  }

  async function runPreview() {
    if (!units.length) return;
    const invalid = units.some(function (u) {
      return !(u.tipo_activo_id > 0) || !(Number(u.valor_bien) > 0);
    });
    if (invalid) {
      if (previewBody) {
        previewBody.innerHTML =
          '<p class="text-muted small mb-0">Indique tipo y valor del bien en cada unidad.</p>';
      }
      return;
    }
    if (inflight) inflight.abort();
    const ctrl = new AbortController();
    inflight = ctrl;
    if (previewStatus) {
      previewStatus.className = "badge text-bg-secondary";
      previewStatus.textContent = "…";
    }
    try {
      const res = await fetch(API_PREVIEW, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(buildPayload()),
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(function () {
          return {};
        });
        if (res.status === 503) {
          throw new Error(
            "Servidor no disponible (503). Si acaba de estimar residual, espere y reintente el pricing."
          );
        }
        throw new Error(typeof err.detail === "string" ? err.detail : "Error en preview");
      }
      const data = await res.json();
      if (data.unidades && data.unidades.length) {
        units = data.unidades.map(function (nu) {
          const prev = findUnit(nu.id) || {};
          const estNu = nu.residual_estimacion || {};
          const estPrev = prev.residual_estimacion || {};
          // Preferir estimación enriquecida con pricing; conservar comps si el preview no trae
          const mergedEst = Object.assign({}, estPrev, estNu, {
            comparables: estNu.comparables && estNu.comparables.length ? estNu.comparables : estPrev.comparables,
            search_urls: estNu.search_urls || estPrev.search_urls,
            portales: estNu.portales && estNu.portales.length ? estNu.portales : estPrev.portales,
            deal: estNu.deal || estPrev.deal,
            rentabilidad: estNu.rentabilidad || estPrev.rentabilidad,
            deal_con_pricing: !!(estNu.deal_con_pricing || (estNu.rentabilidad && estNu.rentabilidad.tir_anual_pct != null)),
          });
          return Object.assign({}, prev, nu, {
            residual_aceptado:
              prev.residual_aceptado && Number(prev.residual_aceptado) > 0
                ? prev.residual_aceptado
                : nu.residual_aceptado,
            residual_estimacion: mergedEst,
            analisis_residual: nu.analisis_residual || prev.analisis_residual,
          });
        });
        syncHidden();
        if (currentStep === 3 || currentStep === 4) renderResiduals();
      }
      renderPreview(data.result || {});
      if (previewStatus) {
        const ev = (data.result || {}).evaluacion_economica || data.evaluacion_economica || {};
        previewStatus.className = "badge text-bg-success";
        previewStatus.textContent = ev.decision || "OK";
      }
    } catch (e) {
      if (e.name === "AbortError") return;
      if (previewBody) {
        previewBody.innerHTML = '<p class="text-danger small mb-0">' + String(e.message || e) + "</p>";
      }
      if (previewStatus) {
        previewStatus.className = "badge text-bg-danger";
        previewStatus.textContent = "Error";
      }
    }
  }

  function showStep(step) {
    currentStep = step;
    panels.forEach(function (p) {
      p.style.display = parseInt(p.getAttribute("data-lop-panel"), 10) === step ? "" : "none";
    });
    document.querySelectorAll("[data-step-ind]").forEach(function (el) {
      const s = parseInt(el.getAttribute("data-step-ind"), 10);
      el.classList.toggle("is-active", s === step);
      el.classList.toggle("is-done", s < step);
    });
    if (btnPrev) btnPrev.disabled = step <= 1;
    if (btnNext) {
      btnNext.style.display = step >= panels.length ? "none" : "";
      btnNext.textContent = step === 2 ? "Estimar residual →" : "Siguiente";
    }
    if (btnSave) btnSave.disabled = step < 3 || !units.length;
    if (step === 2) renderUnits();
    if (step === 3) {
      renderResiduals();
      // Si ya hay residual estimado, solo pricing (sin reconsultar portales → evita 503)
      const ready = units.length && units.every(function (u) {
        return Number(u.residual_sugerido || 0) > 0 && u.residual_estimacion;
      });
      if (ready) runPreview();
      else estimarResiduales();
    }
    if (step === 4) {
      renderSummary();
      schedulePreview();
    }
  }

  form.addEventListener("click", function (ev) {
    const rem = ev.target.closest(".lop-remove-unit");
    if (rem) {
      units = units.filter(function (u) {
        return u.id !== rem.getAttribute("data-uid");
      });
      renderUnits();
      schedulePreview();
      return;
    }
    const acc = ev.target.closest(".lop-accept-residual");
    if (acc) {
      const u = findUnit(acc.getAttribute("data-uid"));
      if (u) {
        u.residual_aceptado = u.residual_sugerido;
        renderResiduals();
        schedulePreview();
      }
    }
  });

  form.addEventListener("change", function (ev) {
    const el = ev.target.closest(".lop-f");
    if (!el) return;
    updateField(el.getAttribute("data-uid"), el.getAttribute("data-f"), el.value);
  });

  form.addEventListener("input", function (ev) {
    const el = ev.target.closest(".lop-f");
    if (!el) return;
    const f = el.getAttribute("data-f");
    if (f === "valor_bien" || f === "km_anual" || f === "cantidad" || f === "residual_aceptado") {
      updateField(el.getAttribute("data-uid"), f, el.value);
    }
  });

  btnAdd &&
    btnAdd.addEventListener("click", function () {
      units.push(defaultUnit());
      renderUnits();
      schedulePreview();
    });

  btnReest && btnReest.addEventListener("click", function () {
    estimarResiduales();
  });

  btnPrev &&
    btnPrev.addEventListener("click", function () {
      if (currentStep > 1) showStep(currentStep - 1);
    });

  btnNext &&
    btnNext.addEventListener("click", function () {
      if (currentStep === 1) {
        showStep(2);
        if (!units.length) {
          units.push(defaultUnit());
          renderUnits();
        }
        return;
      }
      if (currentStep === 2) {
        const bad = units.some(function (u) {
          return !(Number(u.valor_bien) > 0);
        });
        if (!units.length || bad) {
          alert("Agregue al menos una unidad con valor del bien mayor a 0.");
          return;
        }
        showStep(3);
        return;
      }
      if (currentStep < panels.length) showStep(currentStep + 1);
    });

  form.addEventListener("submit", function () {
    syncHidden();
    if (!units.length) {
      alert("Agregue al menos una unidad.");
      return false;
    }
  });

  // init
  showStep(1);
  const seed = BOOT.seed || null;
  if (seed && Array.isArray(seed.unidades) && seed.unidades.length) {
    units = seed.unidades.map(function (u) {
      const base = defaultUnit();
      const merged = Object.assign(base, u || {}, { id: (u && u.id) || uid() });
      // Conserva marca/modelo legacy aunque no estén en catálogo actual.
      return merged;
    });
    syncHidden();
    renderUnits();
    renderResiduals();
    schedulePreview();
    if (btnSave) btnSave.disabled = false;
  } else {
    const firstTipo = BOOT.paramsByTipo[String(BOOT.defaultTipoId)];
    if (firstTipo && BOOT.modo !== "editar") {
      const plazoEl = form.querySelector('[name="plazo_meses"]');
      const spreadEl = form.querySelector('[name="spread_pct"]');
      if (plazoEl) plazoEl.value = String(firstTipo.plazo_default || 36);
      if (spreadEl) spreadEl.value = String(firstTipo.spread_default_pct || 8);
    }
  }
})();
