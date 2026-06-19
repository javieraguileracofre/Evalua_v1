# services/leasing_operativo/economic_engine.py
# -*- coding: utf-8 -*-
"""
Núcleo económico leasing operativo v2: CAPEX, pie, residual, collateral, costo de fondo,
depreciación, costos operativos/comercial (upfront + recurrente), prima riesgo, pricing,
flujo indexado UF/IPC, VAN, TIR, payback, waterfall y decisión.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from services.leasing_operativo.collateral_model import analizar_collateral
from services.leasing_operativo.cronograma import calcular_monto_cuota_indexada, resumen_cronograma
from services.leasing_operativo.decision_engine import evaluar_decision
from services.leasing_operativo.pricing_model import (
    buscar_renta_por_tir,
    construir_flujos_caja_inversionista,
    npv_mensual,
    renta_costo_mas_spread,
    renta_margen_sobre_venta,
    tir_anual_desde_mensual,
    tir_mensual_bisec,
)


def _d(v: Any, default: str = "0") -> Decimal:
    if v is None:
        return Decimal(default)
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def _suma_capex(inp: dict[str, Any]) -> Decimal:
    keys = (
        "precio_compra",
        "importacion",
        "inscripcion",
        "patente",
        "gps_telemetria",
        "traslado",
        "acondicionamiento",
        "puesta_marcha",
        "comision_proveedor",
        "otros_activables",
    )
    capex_block = inp.get("capex") if isinstance(inp.get("capex"), dict) else inp
    return sum((_d(capex_block.get(k)) for k in keys), Decimal("0")).quantize(Decimal("1"))


def _wacc_mensual(costo_fondo: dict[str, Any], scenario_mult: Decimal, mes: int = 1) -> Decimal:
    tramos = costo_fondo.get("tramos") if isinstance(costo_fondo.get("tramos"), list) else None
    if tramos:
        for tr in tramos:
            desde = int(tr.get("desde_mes", 1))
            hasta = int(tr.get("hasta_mes", 9999))
            if desde <= mes <= hasta:
                kd = _d(tr.get("costo_deuda_anual_pct", costo_fondo.get("costo_deuda_anual_pct"))) / Decimal("100")
                ke = _d(tr.get("costo_capital_anual_pct", costo_fondo.get("costo_capital_anual_pct"))) / Decimal("100")
                wd = _d(tr.get("peso_deuda", costo_fondo.get("peso_deuda")), "0.65")
                we = _d(tr.get("peso_capital", costo_fondo.get("peso_capital")), "0.35")
                sp = _d(tr.get("spread_inversionista_anual_pct", costo_fondo.get("spread_inversionista_anual_pct"))) / Decimal(
                    "100"
                )
                wacc_a = (kd * wd + ke * we + sp) * scenario_mult
                return ((Decimal("1") + wacc_a) ** (Decimal("1") / Decimal("12"))) - Decimal("1")
    kd = _d(costo_fondo.get("costo_deuda_anual_pct")) / Decimal("100")
    ke = _d(costo_fondo.get("costo_capital_anual_pct")) / Decimal("100")
    wd = _d(costo_fondo.get("peso_deuda"), "0.65")
    we = _d(costo_fondo.get("peso_capital"), "0.35")
    sp = _d(costo_fondo.get("spread_inversionista_anual_pct")) / Decimal("100")
    wacc_a = (kd * wd + ke * we + sp) * scenario_mult
    return ((Decimal("1") + wacc_a) ** (Decimal("1") / Decimal("12"))) - Decimal("1")


def _costos_operativos_mensuales(
    plantillas: list[dict[str, Any]],
    plazo: int,
    costo_mult: Decimal,
    km_anual: Decimal,
) -> tuple[list[Decimal], list[dict[str, Any]]]:
    n = max(int(plazo), 1)
    mes = [Decimal("0")] * n
    detalle: list[dict[str, Any]] = []
    for row in plantillas:
        per = str(row.get("periodicidad") or "MENSUAL").upper()
        base = _d(row.get("monto_mensual_equiv")) * costo_mult
        cod = row.get("codigo", "")
        if per == "MENSUAL":
            for t in range(n):
                mes[t] += base
            detalle.append({"codigo": cod, "tipo": "MENSUAL", "mensual": float(base)})
        elif per == "ANUAL":
            m = base / Decimal("12")
            for t in range(n):
                mes[t] += m
            detalle.append({"codigo": cod, "tipo": "ANUAL_PRORRATEO", "mensual": float(m)})
        elif per == "VAR_KM":
            m = km_anual * base / Decimal("12000")
            for t in range(n):
                mes[t] += m
            detalle.append({"codigo": cod, "tipo": "VAR_KM", "mensual": float(m)})
        elif per == "INICIAL":
            if n > 0:
                mes[0] += base
            detalle.append({"codigo": cod, "tipo": "INICIAL", "monto": float(base)})
        elif per == "FINAL":
            if n > 0:
                mes[n - 1] += base
            detalle.append({"codigo": cod, "tipo": "FINAL", "monto": float(base)})
    return mes, detalle


def _split_comercial(com_in: dict[str, Any], plazo: int) -> tuple[Decimal, Decimal, dict[str, float]]:
    """Separa costos upfront (mes 0 cash) vs recurrente prorrateado."""
    upfront_keys = ("evaluacion", "legal", "onboarding", "costo_adquisicion")
    recurring_keys = ("comision_vendedor", "comision_canal")
    upfront = sum((_d(com_in.get(k)) for k in upfront_keys), Decimal("0"))
    recurring_total = sum((_d(com_in.get(k)) for k in recurring_keys), Decimal("0"))
    n = max(int(plazo), 1)
    recurring_m = (recurring_total / Decimal(n)).quantize(Decimal("1"))
    return upfront, recurring_m, {
        "upfront_total": float(upfront),
        "recurring_mensual": float(recurring_m),
        "recurring_total": float(recurring_total),
    }


def _rentas_mensuales(
    plazo: int,
    renta_base: Decimal,
    indexacion_tipo: str,
    indexacion_pct: Decimal,
) -> list[Decimal]:
    idx_t = (indexacion_tipo or "NINGUNA").strip().upper()
    idx_p = _d(indexacion_pct)
    return [
        calcular_monto_cuota_indexada(
            nro=t + 1,
            renta_base=renta_base,
            indexacion_tipo=idx_t,
            indexacion_pct=idx_p,
        )
        for t in range(max(int(plazo), 1))
    ]


def _construir_flujos_caja_v2(
    *,
    inversion_inicial: Decimal,
    plazo: int,
    rentas: list[Decimal],
    op_m: list[Decimal],
    riesgo_m: Decimal,
    com_recurring_m: Decimal,
    upfront_comercial: Decimal,
    valor_terminal: Decimal,
) -> list[Decimal]:
    fl: list[Decimal] = [-(inversion_inicial + upfront_comercial)]
    n = max(int(plazo), 1)
    for t in range(n):
        renta_t = rentas[t] if t < len(rentas) else rentas[-1]
        cf = renta_t - op_m[t] - riesgo_m - com_recurring_m
        if t == n - 1:
            cf += valor_terminal
        fl.append(cf)
    return fl


def _waterfall_promedio(
    *,
    depreciacion_m: Decimal,
    fondo_prom: Decimal,
    op_prom: Decimal,
    riesgo_m: Decimal,
    com_m: Decimal,
    renta_sug: Decimal,
) -> list[dict[str, Any]]:
    spread = max(renta_sug - depreciacion_m - fondo_prom - op_prom - riesgo_m - com_m, Decimal("0"))
    items = [
        ("Depreciación económica", depreciacion_m),
        ("Costo de fondo (prom.)", fondo_prom),
        ("Costos operativos (prom.)", op_prom),
        ("Prima de riesgo", riesgo_m),
        ("Costo comercial (prom.)", com_m),
        ("Spread / margen", spread),
    ]
    return [{"concepto": k, "monto": float(v.quantize(Decimal("1")))} for k, v in items]


def _convertir_desde_clp(monto_clp: Decimal, moneda: str, uf_clp: Decimal, usd_clp: Decimal) -> Decimal:
    m = (moneda or "CLP").upper()
    if m == "UF" and uf_clp > 0:
        return (monto_clp / uf_clp).quantize(Decimal("0.0001"))
    if m == "USD" and usd_clp > 0:
        return (monto_clp / usd_clp).quantize(Decimal("0.01"))
    return monto_clp.quantize(Decimal("1"))


def _convertir_a_clp(monto: Decimal, moneda: str, uf_clp: Decimal, usd_clp: Decimal) -> Decimal:
    m = (moneda or "CLP").upper()
    if m == "CLP":
        return monto.quantize(Decimal("1"))
    if m == "UF" and uf_clp > 0:
        return (monto * uf_clp).quantize(Decimal("1"))
    if m == "USD" and usd_clp > 0:
        return (monto * usd_clp).quantize(Decimal("1"))
    return monto.quantize(Decimal("1"))


def run_economic_engine(
    *,
    inputs: dict[str, Any],
    tipo_activo: dict[str, Any],
    politica: dict[str, dict[str, Any]],
    plantillas_costo: list[dict[str, Any]],
) -> dict[str, Any]:
    esc = str(inputs.get("escenario") or "BASE").upper()
    moneda = str(inputs.get("moneda") or "CLP").upper()
    iva_pct = _d(inputs.get("iva_pct"), "19")
    indexacion_tipo = str(inputs.get("indexacion_tipo") or "NINGUNA").upper()
    indexacion_pct = _d(inputs.get("indexacion_pct"))
    pie_pct = _d(inputs.get("pie_inicial_pct"))
    opcion_pct = _d(inputs.get("opcion_compra_pct"))
    opcion_fijo = _d(inputs.get("opcion_compra_monto"))

    market = inputs.get("market_data") or {}
    uf_clp = _d(market.get("uf_clp"))
    usd_clp = _d(market.get("usd_clp"))
    escenarios = politica.get("escenarios_v1") or {}
    mult = escenarios.get(esc) or escenarios.get("BASE") or {}
    residual_mult = _d(mult.get("residual_mult"), "1")
    costo_mult = _d(mult.get("costo_mult"), "1")
    riesgo_mult = _d(mult.get("riesgo_mult"), "1")
    tasa_fondo_mult = _d(mult.get("tasa_fondo_mult"), "1")

    plazo = max(int(inputs.get("plazo_meses") or 36), 1)
    capex_bruto = _suma_capex(inputs)
    if moneda != "CLP":
        capex_bruto = _convertir_a_clp(capex_bruto, moneda, uf_clp, usd_clp)

    pie_inicial = (capex_bruto * pie_pct / Decimal("100")).quantize(Decimal("1"))
    capex_financiado = max(capex_bruto - pie_inicial, Decimal("0"))

    tipo = tipo_activo
    rb_pct = _d(tipo.get("residual_base_pct"), "15")
    rmax_pct = _d(tipo.get("residual_max_pct"), "45")
    liq_f = _d(tipo.get("liquidez_factor"), "1")
    obs_f = _d(tipo.get("obsolescencia_factor"), "1")
    dkm = _d(tipo.get("desgaste_km_factor"), "0.0001")
    dhr = _d(tipo.get("desgaste_hora_factor"), "0.0005")
    hair = _d(tipo.get("haircut_residual_pct"), "5")

    km_a = _d((inputs.get("uso") or {}).get("km_anual"))
    hr_a = _d((inputs.get("uso") or {}).get("horas_anual"))
    marca_f = _d((inputs.get("activo") or {}).get("marca_modelo_factor"), "1")
    sector_m = _d((inputs.get("activo") or {}).get("sector_economico_mult"), "1")
    infl_act = _d((inputs.get("activo") or {}).get("inflacion_activo_pct_anual"))
    cond_f = _d((inputs.get("activo") or {}).get("condicion_factor"), "1")

    from services.leasing_operativo.residual_model import residual_ajustado, residual_base_valor

    v_base = residual_base_valor(capex_financiado, rb_pct, plazo)
    res_info = residual_ajustado(
        valor_base=v_base * residual_mult,
        capex_total=capex_financiado,
        residual_max_pct=rmax_pct,
        scenario_mult=Decimal("1"),
        liquidez_factor=liq_f,
        obsolescencia_factor=obs_f,
        desgaste_km_factor=dkm,
        desgaste_hora_factor=dhr,
        haircut_pct=hair,
        km_anual=km_a,
        horas_anual=hr_a,
        marca_modelo_factor=marca_f,
        sector_economico_mult=sector_m,
        inflacion_activo_pct_anual=infl_act,
        condicion_factor=cond_f,
    )
    valor_residual = Decimal(str(res_info["valor_residual_ajustado"]))
    if opcion_fijo > 0:
        valor_terminal = valor_residual + opcion_fijo
    elif opcion_pct > 0:
        valor_terminal = valor_residual + (capex_financiado * opcion_pct / Decimal("100")).quantize(Decimal("1"))
    else:
        valor_terminal = valor_residual

    col_in = inputs.get("collateral") or {}
    ead = capex_financiado * _d((politica.get("riesgo_base_v1") or {}).get("EAD_pct_capex"), "1")
    vm_col = _d(col_in.get("valor_mercado"))
    warnings: list[str] = []
    if vm_col <= 0:
        if esc in {"CONSERVADOR", "ESTRES"}:
            vm_col = (capex_financiado * Decimal("0.82")).quantize(Decimal("1"))
            warnings.append("Valor de mercado no informado: se aplicó haircut conservador del 18% sobre CAPEX.")
        else:
            vm_col = capex_financiado
            warnings.append("Valor de mercado igual a CAPEX financiado (revisar tasación).")

    col_out = analizar_collateral(
        valor_mercado=vm_col,
        costo_repossession=_d(col_in.get("costo_repossession")),
        costo_legal=_d(col_in.get("costo_legal")),
        transporte=_d(col_in.get("transporte")),
        reacondicionamiento=_d(col_in.get("reacondicionamiento")),
        descuento_venta_forzada_pct=_d(col_in.get("descuento_venta_forzada_pct"), "12"),
        meses_liquidacion=int(col_in.get("meses_liquidacion") or 4),
        tasa_fin_liquidacion_mensual=_d(col_in.get("tasa_fin_liquidacion_mensual"), "0.008"),
        ead=ead,
    )
    ltv = Decimal(str(col_out["ltv_pct"]))
    lgd_pct = Decimal(str(col_out["lgd_pct"]))
    recovery_rate = Decimal(str(col_out.get("recovery_rate_pct", 0)))

    cfondo_cfg = politica.get("costo_fondo_v1") or {}
    i_m_prom = _wacc_mensual(cfondo_cfg, tasa_fondo_mult, 1)

    depreciacion_m = ((capex_financiado - valor_residual) / Decimal(plazo)).quantize(Decimal("1"))

    op_m, op_det = _costos_operativos_mensuales(plantillas_costo, plazo, costo_mult, km_a)

    com_in = inputs.get("comercial") or {}
    upfront_com, com_recurring_m, com_calendar = _split_comercial(com_in, plazo)

    from services.leasing_operativo.risk_model import pick_pd, prima_riesgo_mensual

    riesgo_cfg = politica.get("riesgo_base_v1") or {}
    seg = str((inputs.get("riesgo") or {}).get("segmento_cliente") or "MEDIO").upper()
    pd = pick_pd(seg, riesgo_cfg)
    pr = prima_riesgo_mensual(
        pd=pd,
        lgd_pct=lgd_pct,
        ead=ead,
        plazo_meses=plazo,
        riesgo_sector_mult=_d((inputs.get("riesgo") or {}).get("sector_mult"), "1") * riesgo_mult,
        riesgo_activo_mult=_d((inputs.get("riesgo") or {}).get("activo_mult"), "1"),
        uso_intensivo_mult=_d((inputs.get("riesgo") or {}).get("uso_intensivo_mult"), "1"),
        liquidez_mult=_d((inputs.get("riesgo") or {}).get("liquidez_mult"), "1"),
    )
    riesgo_m = Decimal(str(pr["prima_riesgo_mensual"]))

    saldo = capex_financiado
    fondo_m: list[Decimal] = []
    for t in range(plazo):
        i_m = _wacc_mensual(cfondo_cfg, tasa_fondo_mult, t + 1)
        cf = (saldo * i_m).quantize(Decimal("1"))
        fondo_m.append(cf)
        saldo = (saldo - depreciacion_m).quantize(Decimal("1"))
        saldo = max(saldo, valor_residual)

    costo_total_sin_renta_m = [
        (depreciacion_m + fondo_m[t] + op_m[t] + riesgo_m + com_recurring_m).quantize(Decimal("1")) for t in range(plazo)
    ]
    costo_prom = sum(costo_total_sin_renta_m, Decimal("0")) / Decimal(plazo)
    costo_pico_mes = max(costo_total_sin_renta_m) if costo_total_sin_renta_m else costo_prom
    renta_min_pico = costo_pico_mes.quantize(Decimal("1"))
    renta_min_prom = costo_prom.quantize(Decimal("1"))
    renta_min = max(renta_min_pico, renta_min_prom)

    met = str(inputs.get("metodo_pricing") or "COSTO_SPREAD").upper()
    spread_pct = _d(inputs.get("spread_pct"), "8")
    margen_pct = _d(inputs.get("margen_pct"), "12")
    tir_obj = _d(inputs.get("tir_objetivo_anual_pct"), "14")

    def _build_flujos_for_renta(r: Decimal) -> list[Decimal]:
        rentas = _rentas_mensuales(plazo, r, indexacion_tipo, indexacion_pct)
        return _construir_flujos_caja_v2(
            inversion_inicial=capex_financiado,
            plazo=plazo,
            rentas=rentas,
            op_m=op_m,
            riesgo_m=riesgo_m,
            com_recurring_m=com_recurring_m,
            upfront_comercial=upfront_com,
            valor_terminal=valor_terminal,
        )

    if met == "MARGEN_VENTA":
        renta = renta_margen_sobre_venta(costo_pico_mes, margen_pct)
    elif met == "TIR_OBJETIVO":
        renta = buscar_renta_por_tir(renta_min, capex_financiado, plazo, tir_obj, _build_flujos_for_renta)
    else:
        renta = renta_costo_mas_spread(costo_pico_mes, spread_pct)

    renta_sug = max(renta, renta_min)
    rentas_idx = _rentas_mensuales(plazo, renta_sug, indexacion_tipo, indexacion_pct)
    cron_res = resumen_cronograma(
        [{"monto_renta": float(x)} for x in rentas_idx]
    )

    iva_mensual = (rentas_idx[0] * iva_pct / Decimal("100")).quantize(Decimal("1"))
    renta_bruta = (rentas_idx[0] + iva_mensual).quantize(Decimal("1"))

    filas: list[dict[str, Any]] = []
    for t in range(plazo):
        venta = rentas_idx[t]
        c_f = fondo_m[t]
        dep = depreciacion_m
        op = op_m[t]
        ri = riesgo_m
        co = com_recurring_m
        if t == 0:
            co_display = co + upfront_com
        else:
            co_display = co
        res_op = (venta - c_f - dep - op - ri - co).quantize(Decimal("1"))
        mb = (res_op / venta * Decimal("100")) if venta > 0 else Decimal("0")
        filas.append(
            {
                "mes": t + 1,
                "venta": float(venta),
                "costo_fondo": float(c_f),
                "depreciacion": float(dep),
                "costos_operativos": float(op),
                "prima_riesgo": float(ri),
                "comercial": float(co_display),
                "resultado_operacional": float(res_op),
                "margen_bruto_pct": float(mb),
            }
        )

    flujos = _build_flujos_for_renta(renta_sug)
    tir_m = tir_mensual_bisec(flujos)
    tir_a = tir_anual_desde_mensual(tir_m) if tir_m is not None else None
    van = npv_mensual(flujos, i_m_prom)

    acum = Decimal("0")
    payback_m: int | None = None
    for t, cf in enumerate(flujos):
        acum += cf
        if payback_m is None and acum >= 0:
            payback_m = t

    margen_prom = sum(Decimal(str(x["margen_bruto_pct"])) for x in filas) / Decimal(plazo)
    roa = (
        sum(Decimal(str(x["resultado_operacional"])) for x in filas) / capex_financiado * Decimal("100")
        if capex_financiado > 0
        else Decimal("0")
    )

    spread_sobre_costo = Decimal("0")
    if costo_prom > 0:
        spread_sobre_costo = ((renta_sug - costo_prom) / costo_prom * Decimal("100")).quantize(Decimal("0.01"))

    fondo_prom = sum(fondo_m, Decimal("0")) / Decimal(plazo)
    op_prom = sum(op_m, Decimal("0")) / Decimal(plazo)
    waterfall = _waterfall_promedio(
        depreciacion_m=depreciacion_m,
        fondo_prom=fondo_prom,
        op_prom=op_prom,
        riesgo_m=riesgo_m,
        com_m=com_recurring_m + (upfront_com / Decimal(plazo)),
        renta_sug=renta_sug,
    )

    motor_params = politica.get("motor_decision_v1") or {}
    dec = evaluar_decision(
        van=van,
        tir_anual_pct=tir_a,
        margen_op_promedio_pct=margen_prom,
        ltv_pct=ltv,
        params={k: float(v) if hasattr(v, "real") else v for k, v in motor_params.items()},
        spread_sobre_costo_pct=spread_sobre_costo,
        payback_meses=payback_m,
        recovery_rate_pct=recovery_rate,
        warnings=warnings,
    )

    contabilidad = {
        "renta_neta": "110301",
        "iva_debito": "210201",
        "costo_fondo": "610501",
        "costos_mantencion": "610502",
        "spread_ganancia": "410701",
    }

    return {
        "engine_version": "2.0",
        "capex_total": float(capex_bruto),
        "capex_financiado": float(capex_financiado),
        "pie_inicial": float(pie_inicial),
        "pie_inicial_pct": float(pie_pct),
        "opcion_compra_terminal": float(valor_terminal - valor_residual),
        "valor_residual": res_info,
        "collateral": col_out,
        "ltv_pct": float(ltv),
        "lgd_pct": float(lgd_pct),
        "recovery_rate_pct": float(recovery_rate),
        "tasa_fondo_mensual_efectiva": float(i_m_prom * Decimal("100")),
        "depreciacion_economica_mensual": float(depreciacion_m),
        "costo_comercial_mensual": float(com_recurring_m),
        "costo_comercial_upfront": float(upfront_com),
        "comercial_calendar": com_calendar,
        "costo_total_mensual_promedio": float(costo_prom),
        "renta_minima": float(renta_min),
        "renta_minima_pico": float(renta_min_pico),
        "renta_minima_promedio": float(renta_min_prom),
        "renta_sugerida": float(renta_sug),
        "renta_mensual_neta": float(renta_sug),
        "indexacion_tipo": indexacion_tipo,
        "indexacion_pct": float(indexacion_pct),
        "cronograma_resumen": {k: float(v) if isinstance(v, Decimal) else v for k, v in cron_res.items()},
        "iva_pct": float(iva_pct),
        "iva_mensual": float(iva_mensual),
        "renta_mensual_bruta": float(renta_bruta),
        "moneda_cotizacion": moneda,
        "tipo_cambio_ref": {"uf_clp": float(uf_clp), "usd_clp": float(usd_clp)},
        "renta_moneda_cotizacion": float(_convertir_desde_clp(renta_sug, moneda, uf_clp, usd_clp)),
        "renta_bruta_moneda_cotizacion": float(_convertir_desde_clp(renta_bruta, moneda, uf_clp, usd_clp)),
        "desglose_renta_mensual": {
            "depreciacion_economica": float(depreciacion_m),
            "costo_fondo": float(fondo_prom),
            "costos_operativos": float(op_prom),
            "prima_riesgo": float(riesgo_m),
            "costo_comercial": float(com_recurring_m + upfront_com / Decimal(plazo)),
            "spread_ganancia": float((renta_sug - costo_prom).quantize(Decimal("1"))),
        },
        "spread_sobre_costo_pct": float(spread_sobre_costo),
        "contabilidad_recomendada": contabilidad,
        "waterfall": waterfall,
        "warnings": warnings,
        "margen_operacional_promedio_pct": float(margen_prom),
        "flujo_mensual": filas,
        "van": float(van),
        "tir_anual_pct": float(tir_a) if tir_a is not None else None,
        "payback_meses": payback_m,
        "roa_pct": float(roa.quantize(Decimal("0.01"))),
        "metodo_pricing": met,
        "escenario": esc,
        "costos_operativos_detalle": op_det,
        "decision": dec,
    }


def merge_politica(rows: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = getattr(r, "clave", None) or r.get("clave")
        v = getattr(r, "valor_json", None) or r.get("valor_json")
        if k and isinstance(v, dict):
            out[str(k)] = deepcopy(v)
    return out


def preparar_inputs_simulacion(
    *,
    inputs: dict[str, Any],
    tipo_activo_id: int,
    param_tipo: Any | None,
    plazo_meses: int,
    escenario: str,
    metodo_pricing: str,
    margen_pct: Any | None,
    spread_pct: Any | None,
    tir_objetivo: Any | None,
    indexacion_tipo: str | None = None,
    indexacion_pct: Any | None = None,
    pie_inicial_pct: Any | None = None,
    opcion_compra_pct: Any | None = None,
) -> dict[str, Any]:
    inp = dict(inputs)
    if param_tipo:
        inp.setdefault("moneda", param_tipo.moneda)
        inp.setdefault("iva_pct", float(param_tipo.iva_pct))
        base_perfil = param_tipo.perfil_json or {}
        for k in ("uso", "activo", "collateral", "comercial", "riesgo"):
            if not isinstance(inp.get(k), dict):
                inp[k] = {}
            src = base_perfil.get(k) if isinstance(base_perfil.get(k), dict) else {}
            for ck, cv in src.items():
                if inp[k].get(ck) in (None, "", 0, "0"):
                    inp[k][ck] = cv
    inp["plazo_meses"] = plazo_meses
    inp["escenario"] = escenario
    inp["metodo_pricing"] = metodo_pricing
    if margen_pct is not None:
        inp["margen_pct"] = margen_pct
    if spread_pct is not None:
        inp["spread_pct"] = spread_pct
    if tir_objetivo is not None:
        inp["tir_objetivo_anual_pct"] = tir_objetivo
    if indexacion_tipo:
        inp["indexacion_tipo"] = indexacion_tipo
    if indexacion_pct is not None:
        inp["indexacion_pct"] = indexacion_pct
    if pie_inicial_pct is not None:
        inp["pie_inicial_pct"] = pie_inicial_pct
    if opcion_compra_pct is not None:
        inp["opcion_compra_pct"] = opcion_compra_pct
    return inp
