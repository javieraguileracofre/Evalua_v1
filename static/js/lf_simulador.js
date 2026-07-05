/**
 * Simulador en vivo — Leasing financiero (Evalúa ERP).
 * Uso: LfSimulador.init({ formId, simUrl, ratesUrl, cliente, monedaDefault })
 */
(function (global) {
  "use strict";

  function normalizeNumericString(v) {
    let s = (v || "").toString().trim();
    if (!s) return "";
    s = s.replace(/\s+/g, "");
    if (s.includes(",") && s.includes(".")) {
      if (s.lastIndexOf(",") > s.lastIndexOf(".")) s = s.replace(/\./g, "").replace(",", ".");
      else s = s.replace(/,/g, "");
    } else if (s.includes(",")) {
      s = s.replace(/\./g, "").replace(",", ".");
    }
    return s.replace(/[^\d.-]/g, "");
  }

  function parseNum(v) {
    const raw = normalizeNumericString(v);
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }

  function formatMoney(v, dec) {
    const raw = normalizeNumericString(v);
    if (!raw || raw === "-" || raw === ".") return "";
    const n = Number(raw);
    if (!Number.isFinite(n)) return "";
    const digits =
      dec != null ? dec : String(raw).includes(".") ? Math.min(4, (String(raw).split(".")[1] || "").length) : 0;
    return n.toLocaleString("es-CL", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function formatThousands(v) {
    return formatMoney(v, null);
  }

  function fmtPreview(n, moneda) {
    if (n == null || !Number.isFinite(Number(n))) return "—";
    const num = Number(n);
    if (moneda === "UF") return num.toLocaleString("es-CL", { minimumFractionDigits: 4, maximumFractionDigits: 4 }) + " UF";
    if (moneda === "USD") return "US$ " + num.toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return "$ " + num.toLocaleString("es-CL", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function fmtPct(n) {
    if (n == null || !Number.isFinite(Number(n))) return "—";
    return Number(n).toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " %";
  }

  function init(cfg) {
    const form = document.getElementById(cfg.formId || "cotForm");
    if (!form) return;

    const btn = document.getElementById("btnSubmit");
    const simUrl = cfg.simUrl || form.getAttribute("data-sim-url") || "";
    const ratesUrl = cfg.ratesUrl || form.getAttribute("data-rates-url") || "";
    const hasClientes = cfg.hasClientes != null ? !!cfg.hasClientes : (form.getAttribute("data-has-clientes") || "").trim() === "1";
    const inputSearch = document.getElementById("cliente_search");
    const selectList = document.getElementById("cliente_select");
    const hiddenId = document.getElementById("cliente_id");
    const help = document.getElementById("cliente_help");
    const datalist = document.getElementById("clientes_datalist");
    const monedaSelect = document.getElementById("moneda_select");
    const ratesInfo = document.getElementById("rates_info");
    const btnRates = document.getElementById("btn_rates");
    const monedaDefault = (cfg.monedaDefault || form.getAttribute("data-moneda-default") || "CLP").trim();
    const moneyInputs = form.querySelectorAll(".js-money:not([readonly])");
    const rateInputs = form.querySelectorAll(".js-rate");
    const ufInput = document.getElementById("uf_valor");
    const usdInput = document.getElementById("dolar_valor");
    const monedaHelp = document.getElementById("moneda_help");
    const ufHelp = document.getElementById("uf_help");
    const usdHelp = document.getElementById("usd_help");
    const montoFinInput = document.getElementById("monto_financiado");
    const montoRefInput = document.getElementById("monto");
    const montoFinHelp = document.getElementById("monto_fin_help");
    let montoFinManual = false;
    let simTimer = null;
    let simAbort = null;

    function setFxUx() {
      if (!monedaSelect) return;
      const m = (monedaSelect.value || "CLP").toUpperCase();
      if (ufInput) ufInput.required = m === "UF";
      if (usdInput) usdInput.required = m === "USD";
      if (ufHelp) ufHelp.textContent = m === "UF" ? "Obligatorio para cotizar en UF." : "";
      if (usdHelp) usdHelp.textContent = m === "USD" ? "Obligatorio para cotizar en USD." : "";
      if (monedaHelp) {
        monedaHelp.textContent =
          m === "CLP"
            ? "Operación en pesos; tipo de cambio opcional para seguros en UF."
            : m === "UF"
              ? "Operación en UF; requiere valor UF vigente."
              : "Operación en USD; requiere valor dólar vigente.";
      }
      const badge = document.getElementById("preview_moneda");
      if (badge) badge.textContent = m;
    }

    function onBlurFormat(e) {
      e.target.value = formatThousands(e.target.value);
      scheduleSim();
    }

    function onFocusUnformat(e) {
      const raw = normalizeNumericString(e.target.value);
      e.target.value = raw ? raw.replace(".", ",") : "";
    }

    moneyInputs.forEach((el) => {
      el.addEventListener("focus", onFocusUnformat);
      el.addEventListener("blur", onBlurFormat);
    });
    rateInputs.forEach((el) => {
      el.addEventListener("focus", onFocusUnformat);
      el.addEventListener("blur", onBlurFormat);
    });

    if (montoFinInput) {
      montoFinInput.addEventListener("input", function () {
        montoFinManual = true;
      });
      montoFinInput.addEventListener("blur", function () {
        if (!parseNum(montoFinInput.value)) montoFinManual = false;
      });
    }

    function payloadSim() {
      const finSeg = document.getElementById("financia_seguro");
      const finCom = form.querySelector("[name=financia_comision]");
      const ivaApl = form.querySelector("[name=iva_aplica]");
      const ivaRec = form.querySelector("[name=iva_recuperable]");
      return {
        moneda: (monedaSelect && monedaSelect.value) || "CLP",
        valor_neto: parseNum(document.getElementById("valor_neto") && document.getElementById("valor_neto").value),
        pago_inicial_tipo: (document.getElementById("pago_inicial_tipo") && document.getElementById("pago_inicial_tipo").value) || null,
        pago_inicial_valor: parseNum(document.getElementById("pago_inicial_valor") && document.getElementById("pago_inicial_valor").value),
        monto_financiado: montoFinManual ? parseNum(montoFinInput && montoFinInput.value) : null,
        tasa: parseNum(document.getElementById("tasa") && document.getElementById("tasa").value),
        plazo: parseNum(document.getElementById("plazo") && document.getElementById("plazo").value),
        opcion_compra: parseNum(document.getElementById("opcion_compra") && document.getElementById("opcion_compra").value),
        periodos_gracia: parseNum(document.getElementById("periodos_gracia") && document.getElementById("periodos_gracia").value) || 0,
        periodicidad: (form.querySelector("[name=periodicidad]") && form.querySelector("[name=periodicidad]").value) || "MENSUAL",
        financia_seguro: finSeg && finSeg.value === "true",
        seguro_monto_uf: parseNum(document.getElementById("seguro_monto_uf") && document.getElementById("seguro_monto_uf").value),
        otros_montos_pesos: parseNum(document.getElementById("otros_montos_pesos") && document.getElementById("otros_montos_pesos").value),
        gastos_operacionales: parseNum(form.querySelector("[name=gastos_operacionales]") && form.querySelector("[name=gastos_operacionales]").value),
        comision_apertura_tipo: (form.querySelector("[name=comision_apertura_tipo]") && form.querySelector("[name=comision_apertura_tipo]").value) || null,
        comision_apertura: parseNum(form.querySelector("[name=comision_apertura]") && form.querySelector("[name=comision_apertura]").value),
        financia_comision: finCom && finCom.value === "true",
        iva_aplica: ivaApl && ivaApl.value === "true",
        iva_tasa: parseNum(form.querySelector("[name=iva_tasa]") && form.querySelector("[name=iva_tasa]").value),
        iva_recuperable: !(ivaRec && ivaRec.value === "false"),
        uf_valor: parseNum(ufInput && ufInput.value),
        dolar_valor: parseNum(usdInput && usdInput.value),
      };
    }

    function renderPreview(data) {
      const m = (data.moneda || "CLP").toUpperCase();
      const el = (id) => document.getElementById(id);
      if (el("pv_renta")) el("pv_renta").textContent = fmtPreview(data.renta_mensual, m);
      if (el("pv_monto_fin")) el("pv_monto_fin").textContent = fmtPreview(data.monto_financiado, m);
      if (el("pv_pie")) el("pv_pie").textContent = fmtPreview(data.pago_inicial, m);
      if (el("pv_intereses")) el("pv_intereses").textContent = fmtPreview(data.total_intereses, m);
      if (el("pv_tea")) el("pv_tea").textContent = fmtPct(data.tea_anual_pct);
      if (el("pv_cae")) el("pv_cae").textContent = fmtPct(data.cae_anual_pct);
      if (el("pv_total")) el("pv_total").textContent = fmtPreview(data.total_desembolso, m);
      const warn = el("pv_warn");
      if (warn) {
        const msgs = (data.advertencias || []).filter(Boolean);
        if (msgs.length) {
          warn.textContent = msgs.join(" · ");
          warn.classList.remove("d-none");
        } else {
          warn.textContent = "";
          warn.classList.add("d-none");
        }
      }
      if (data.monto_financiado_calculado && montoFinInput && !montoFinManual) {
        montoFinInput.value = formatThousands(String(data.monto_financiado));
        if (montoFinHelp) montoFinHelp.textContent = "Calculado: neto − pie + seguro + otros + comisión/gastos.";
      }
      if (montoRefInput && data.monto_financiado != null) {
        montoRefInput.value = formatThousands(String(data.monto_financiado));
      }
    }

    async function ejecutarSim() {
      if (!simUrl || !hasClientes) return;
      if (simAbort) simAbort.abort();
      simAbort = new AbortController();
      try {
        const res = await fetch(simUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payloadSim()),
          signal: simAbort.signal,
        });
        if (!res.ok) return;
        renderPreview(await res.json());
      } catch (err) {
        if (err && err.name === "AbortError") return;
      }
    }

    function scheduleSim() {
      clearTimeout(simTimer);
      simTimer = setTimeout(ejecutarSim, 350);
    }

    async function cargarIndicadores() {
      if (!btnRates || !ratesUrl) return;
      btnRates.disabled = true;
      btnRates.textContent = "Consultando...";
      try {
        const res = await fetch(ratesUrl, { headers: { Accept: "application/json" } });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        if (ufInput && data.uf) ufInput.value = formatThousands(String(data.uf));
        if (usdInput && data.dolar) usdInput.value = formatThousands(String(data.dolar));
        if (ratesInfo) ratesInfo.textContent = `Actualizado ${data.fecha} · UF ${data.uf} · USD ${data.dolar} (${data.fuente})`;
        scheduleSim();
      } catch (_err) {
        if (ratesInfo) ratesInfo.textContent = "No se pudo consultar UF/USD. Intente nuevamente.";
      } finally {
        btnRates.disabled = false;
        btnRates.textContent = "Cargar UF/USD del día";
      }
    }

    function validar() {
      const ok = !!(hiddenId && hiddenId.value && hiddenId.value.trim() !== "");
      if (btn) btn.disabled = !hasClientes || !ok;
      return ok;
    }

    function setCliente(id, razon, rut) {
      if (hiddenId) hiddenId.value = (id || "").trim();
      if (inputSearch && razon != null) inputSearch.value = razon;
      if (selectList && id != null) selectList.value = String(id);
      if (help) help.textContent = rut ? "RUT: " + rut : "Cliente seleccionado";
      validar();
    }

    function limpiar() {
      if (hiddenId) hiddenId.value = "";
      if (selectList) selectList.value = "";
      if (help) help.textContent = "Seleccione un cliente válido.";
      validar();
    }

    function buscarEnDatalist(valor) {
      if (!datalist) return null;
      const options = datalist.querySelectorAll("option");
      const v = (valor || "").trim();
      if (!v) return null;
      for (let i = 0; i < options.length; i++) {
        if ((options[i].value || "").trim() === v) return options[i];
      }
      const vLower = v.toLowerCase();
      for (let i = 0; i < options.length; i++) {
        if (((options[i].value || "").trim().toLowerCase()) === vLower) return options[i];
      }
      return null;
    }

    function unformatFormNumbers() {
      form.querySelectorAll(".js-money, .js-rate").forEach((el) => {
        if (el.readOnly) return;
        el.value = normalizeNumericString(el.value) || "";
      });
    }

    if (inputSearch && datalist) {
      inputSearch.addEventListener("input", function () {
        if (!(inputSearch.value || "").trim()) limpiar();
      });
      inputSearch.addEventListener("change", function () {
        const val = (inputSearch.value || "").trim();
        if (!val) return limpiar();
        const found = buscarEnDatalist(val);
        if (found) setCliente(found.getAttribute("data-id") || "", found.value || "", found.getAttribute("data-rut") || "");
        else limpiar();
      });
    }

    if (selectList) {
      selectList.addEventListener("change", function () {
        const idx = selectList.selectedIndex;
        const o = idx >= 0 ? selectList.options[idx] : null;
        if (!o || !o.value) return limpiar();
        setCliente(o.value, o.getAttribute("data-razon") || "", o.getAttribute("data-rut") || "");
      });
    }

    if (btnRates) btnRates.addEventListener("click", cargarIndicadores);
    if (monedaSelect) monedaSelect.addEventListener("change", function () {
      setFxUx();
      scheduleSim();
    });
    form.querySelectorAll(".js-sim").forEach((el) => {
      el.addEventListener("change", scheduleSim);
      el.addEventListener("input", scheduleSim);
    });

    if (cfg.cliente && cfg.cliente.id) {
      setCliente(String(cfg.cliente.id), cfg.cliente.razon || "", cfg.cliente.rut || "");
    }

    if (!hasClientes) {
      if (help) help.textContent = "No existen clientes.";
      if (btn) btn.disabled = true;
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        alert("Debe crear un cliente antes de cotizar.");
      });
    } else {
      form.addEventListener("submit", function (e) {
        if (!validar()) {
          e.preventDefault();
          alert("Selecciona un cliente válido.");
          return;
        }
        const m = ((monedaSelect && monedaSelect.value) || "CLP").toUpperCase();
        const ufVal = ufInput ? parseNum(ufInput.value) : null;
        const usdVal = usdInput ? parseNum(usdInput.value) : null;
        if (m === "UF" && !(ufVal > 0)) {
          e.preventDefault();
          alert("Debes informar Valor UF mayor a 0 para cotizar en UF.");
          return;
        }
        if (m === "USD" && !(usdVal > 0)) {
          e.preventDefault();
          alert("Debes informar Valor dólar mayor a 0 para cotizar en USD.");
          return;
        }
        unformatFormNumbers();
      });
    }

    if (monedaSelect && monedaDefault) monedaSelect.value = monedaDefault;
    setFxUx();
    validar();
    moneyInputs.forEach((el) => {
      if (el.value) el.value = formatThousands(el.value);
    });
    rateInputs.forEach((el) => {
      if (el.value) el.value = formatThousands(el.value);
    });
    if (hasClientes) {
      cargarIndicadores();
      scheduleSim();
    }
  }

  global.LfSimulador = { init: init };
})(typeof window !== "undefined" ? window : globalThis);
