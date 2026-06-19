(function () {
  "use strict";

  const form = document.getElementById("lop-sim-form");
  if (!form) return;

  const API = "/api/comercial/leasing-operativo/simular/preview";
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrf = csrfMeta ? csrfMeta.getAttribute("content") || "" : "";

  const previewBody = document.getElementById("lop-preview-body");
  const previewStatus = document.getElementById("lop-preview-status");
  const nav = document.getElementById("lop-wizard-nav");
  const btnPrev = document.getElementById("lop-wizard-prev");
  const btnNext = document.getElementById("lop-wizard-next");
  const panels = Array.from(form.querySelectorAll("[data-lop-panel]"));
  let currentStep = 1;
  let timer = null;
  let inflight = null;

  function fmt(n) {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
    return Math.round(Number(n)).toLocaleString("es-CL");
  }

  function val(name) {
    const el = form.querySelector('[name="' + name + '"]');
    return el ? el.value : "";
  }

  function num(name, def) {
    const v = parseFloat(String(val(name)).replace(",", "."));
    return Number.isFinite(v) ? v : def;
  }

  function buildPayload() {
    return {
      tipo_activo_id: parseInt(val("tipo_activo_id"), 10) || 0,
      cliente_id: val("cliente_id") ? parseInt(val("cliente_id"), 10) : null,
      plazo_meses: parseInt(val("plazo_meses"), 10) || 36,
      escenario: val("escenario") || "BASE",
      metodo_pricing: val("metodo_pricing") || "COSTO_SPREAD",
      spread_pct: num("spread_pct", 8),
      margen_pct: num("margen_pct", 12),
      tir_objetivo: num("tir_objetivo_anual", 14),
      moneda: val("moneda") || "CLP",
      iva_pct: num("iva_pct", 19),
      indexacion_tipo: val("indexacion_tipo") || "NINGUNA",
      indexacion_pct: num("indexacion_pct", 0),
      pie_inicial_pct: num("pie_inicial_pct", 0),
      opcion_compra_pct: num("opcion_compra_pct", 0),
      inputs: {
        moneda: val("moneda") || "CLP",
        iva_pct: val("iva_pct") || "19",
        market_data: {
          uf_clp: val("uf_clp"),
          usd_clp: val("usd_clp"),
          ipc_pct: val("ipc_pct"),
          source: val("market_source"),
          as_of: val("market_as_of"),
        },
        capex: {
          precio_compra: val("precio_compra"),
          importacion: val("importacion"),
          inscripcion: val("inscripcion"),
          patente: val("patente"),
          gps_telemetria: val("gps_telemetria"),
          traslado: val("traslado"),
          acondicionamiento: val("acondicionamiento"),
          puesta_marcha: val("puesta_marcha"),
          comision_proveedor: val("comision_proveedor"),
          otros_activables: val("otros_activables"),
        },
        uso: { km_anual: val("km_anual"), horas_anual: val("horas_anual") },
        activo: {
          marca_modelo_factor: val("marca_modelo_factor"),
          sector_economico_mult: val("sector_economico_mult"),
          inflacion_activo_pct_anual: val("inflacion_activo_pct_anual"),
          condicion_factor: val("condicion_factor"),
        },
        collateral: {
          valor_mercado: val("col_valor_mercado"),
          costo_repossession: val("col_repossession"),
          costo_legal: val("col_legal"),
          transporte: val("col_transporte"),
          reacondicionamiento: val("col_reacond"),
          descuento_venta_forzada_pct: val("col_desc_forzada_pct"),
          meses_liquidacion: val("col_meses_liq"),
          tasa_fin_liquidacion_mensual: val("col_tasa_fin_m"),
        },
        comercial: {
          comision_vendedor: val("com_vendedor"),
          comision_canal: val("com_canal"),
          costo_adquisicion: val("com_adq"),
          evaluacion: val("com_eval"),
          legal: val("com_legal"),
          onboarding: val("com_onb"),
        },
        riesgo: {
          segmento_cliente: val("riesgo_segmento") || "MEDIO",
          sector_mult: val("riesgo_sector_mult"),
          activo_mult: val("riesgo_activo_mult"),
          uso_intensivo_mult: val("riesgo_uso_mult"),
          liquidez_mult: val("riesgo_liq_mult"),
        },
      },
    };
  }

  function renderPreview(result, decision) {
    if (!previewBody) return;
    const dec = decision || {};
    const badge =
      dec.decision_codigo === "APROBAR"
        ? "text-bg-success"
        : dec.decision_codigo === "RECHAZAR"
          ? "text-bg-danger"
          : dec.decision_codigo === "OBSERVAR"
            ? "text-bg-warning"
            : "text-bg-secondary";
    if (previewStatus) {
      previewStatus.className = "badge " + badge;
      previewStatus.textContent = dec.decision_codigo || "—";
    }
    previewBody.innerHTML =
      '<div class="lo-preview-kpi mb-2"><span class="text-muted">Renta sugerida</span><div class="fs-5 fw-bold text-primary">$' +
      fmt(result.renta_sugerida) +
      "</div></div>" +
      '<div class="row g-2 mb-2">' +
      '<div class="col-6"><div class="border rounded p-2"><div class="text-muted">VAN</div><strong>$' +
      fmt(result.van) +
      "</strong></div></div>" +
      '<div class="col-6"><div class="border rounded p-2"><div class="text-muted">TIR anual</div><strong>' +
      (result.tir_anual_pct != null ? Number(result.tir_anual_pct).toFixed(2) + "%" : "—") +
      "</strong></div></div>" +
      '<div class="col-6"><div class="border rounded p-2"><div class="text-muted">Renta mín. pico</div><strong>$' +
      fmt(result.renta_minima_pico) +
      "</strong></div></div>" +
      '<div class="col-6"><div class="border rounded p-2"><div class="text-muted">Margen op.</div><strong>' +
      (result.margen_operacional_promedio_pct != null
        ? Number(result.margen_operacional_promedio_pct).toFixed(2) + "%"
        : "—") +
      "</strong></div></div></div>" +
      (result.pie_inicial
        ? '<div class="text-muted mb-1">Pie inicial: $' + fmt(result.pie_inicial) + "</div>"
        : "") +
      (result.indexacion_tipo && result.indexacion_tipo !== "NINGUNA"
        ? '<div class="text-muted mb-1">Indexación ' +
          result.indexacion_tipo +
          " " +
          (result.indexacion_pct || 0) +
          "%</div>"
        : "") +
      '<div class="small text-muted mt-2">' +
      (dec.decision_detalle || "").slice(0, 220) +
      "</div>";
  }

  function schedulePreview() {
    if (!previewBody) return;
    clearTimeout(timer);
    timer = setTimeout(runPreview, 450);
  }

  async function runPreview() {
    const payload = buildPayload();
    if (!payload.tipo_activo_id || payload.tipo_activo_id <= 0) return;
    if (inflight) inflight.abort();
    const ctrl = new AbortController();
    inflight = ctrl;
    if (previewStatus) {
      previewStatus.className = "badge text-bg-secondary";
      previewStatus.textContent = "…";
    }
    try {
      const res = await fetch(API, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
        },
        body: JSON.stringify(payload),
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(function () {
          return {};
        });
        throw new Error(err.detail || "Error en preview");
      }
      const data = await res.json();
      renderPreview(data.result || {}, (data.result || {}).decision || {});
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
    if (nav) {
      nav.querySelectorAll("[data-lop-step]").forEach(function (btn) {
        const s = parseInt(btn.getAttribute("data-lop-step"), 10);
        btn.classList.toggle("active", s === step);
      });
    }
    if (btnPrev) btnPrev.disabled = step <= 1;
    if (btnNext) btnNext.textContent = step >= panels.length ? "Último paso" : "Siguiente";
  }

  if (panels.length) {
    showStep(1);
    nav &&
      nav.addEventListener("click", function (ev) {
        const btn = ev.target.closest("[data-lop-step]");
        if (!btn) return;
        ev.preventDefault();
        showStep(parseInt(btn.getAttribute("data-lop-step"), 10));
      });
    btnPrev &&
      btnPrev.addEventListener("click", function () {
        if (currentStep > 1) showStep(currentStep - 1);
      });
    btnNext &&
      btnNext.addEventListener("click", function () {
        if (currentStep < panels.length) showStep(currentStep + 1);
      });
  }

  form.addEventListener("input", schedulePreview);
  form.addEventListener("change", schedulePreview);
  schedulePreview();
})();
