# services/leasing_operativo/economic_engine.py
# -*- coding: utf-8 -*-
"""
Núcleo económico leasing operativo: CAPEX, residual, collateral, costo de fondo,
depreciación económica, costos operativos/comercial, prima riesgo, pricing (3 métodos),
flujo mensual, VAN, TIR, payback, ROA y decisión.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from services.leasing_operativo.collateral_model import analizar_collateral
from services.leasing_operativo.decision_engine import evaluar_decision
from services.leasing_operativo.pricing_model import (
    buscar_renta_por_tir,
    construir_flujos_caja_inversionista,
    construir_flujos_inversionista,
    npv_mensual,
    renta_costo_mas_spread,
    renta_margen_sobre_venta,
    tir_anual_desde_mensual,
    tir_mensual_bisec,
)
from services.leasing_operativo.residual_model import residual_ajustado, residual_base_valor
from services.leasing_operativo.risk_model import pick_pd, prima_riesgo_mensual


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
    return sum((_d(inp.get(k)) for k in keys), Decimal("0")).quantize(Decimal("1"))


def _wacc_mensual(costo_fondo: dict[str, Any], scenario_mult: Decimal) -> Decimal:
    kd = _d(costo_fondo.get("costo_deuda_anual_pct")) / Decimal("100")
    ke = _d(costo_fondo.get("costo_capital_anual_pct")) / Decimal("100")
    wd = _d(costo_fondo.get("peso_deuda"), "0.65")
    we = _d(costo_fondo.get("peso_capital"), "0.35")
    sp = _d(costo_fondo.get("spread_inversionista_anual_pct")) / Decimal("100")
    wacc_a = kd * wd + ke * we + sp
    wacc_a = wacc_a * scenario_mult
    im = ((Decimal("1") + wacc_a) ** (Decimal("1") / Decimal("12"))) - Decimal("1")
    return im


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


def _convertir_desde_clp(monto_clp: Decimal, moneda: str, uf_clp: Decimal, usd_clp: Decimal) -> Decimal:
    m = (moneda or "CLP").upper()
    if m == "UF" and uf_clp > 0:
        return (monto_clp / uf_clp).quantize(Decimal("0.0001"))
    if m == "USD" and usd_clp > 0:
        return (monto_clp / usd_clp).quantize(Decimal("0.01"))
    return monto_clp.quantize(Decimal("1"))


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
    capex = _suma_capex(inputs.get("capex") or inputs)

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

    v_base = residual_base_valor(capex, rb_pct, plazo)
    res_info = residual_ajustado(
        valor_base=v_base * residual_mult,
        capex_total=capex,
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

    col_in = inputs.get("collateral") or {}
    ead = capex * _d((politica.get("riesgo_base_v1") or {}).get("EAD_pct_capex"), "1")
    vm_col = _d(col_in.get("valor_mercado"))
    if vm_col <= 0:
        vm_col = capex
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

    cfondo_cfg = politica.get("costo_fondo_v1") or {}
    i_m = _wacc_mensual(cfondo_cfg, tasa_fondo_mult)

    depreciacion_m = ((capex - valor_residual) / Decimal(plazo)).quantize(Decimal("1"))

    op_m, op_det = _costos_operativos_mensuales(plantillas_costo, plazo, costo_mult, km_a)

    com_in = inputs.get("comercial") or {}
    total_com = sum(
        (
            _d(com_in.get("comision_vendedor")),
            _d(com_in.get("comision_canal")),
            _d(com_in.get("costo_adquisicion")),
            _d(com_in.get("evaluacion")),
            _d(com_in.get("legal")),
            _d(com_in.get("onboarding")),
        ),
        Decimal("0"),
    )
    com_m = (total_com / Decimal(plazo)).quantize(Decimal("1"))

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

    saldo = capex
    fondo_m: list[Decimal] = []
    for _ in range(plazo):
        cf = (saldo * i_m).quantize(Decimal("1"))
        fondo_m.append(cf)
        saldo = (saldo - depreciacion_m).quantize(Decimal("1"))
        saldo = max(saldo, valor_residual)

    costo_total_sin_renta_m = [
        (depreciacion_m + fondo_m[t] + op_m[t] + riesgo_m + com_m).quantize(Decimal("1")) for t in range(plazo)
    ]
    costo_prom = sum(costo_total_sin_renta_m, Decimal("0")) / Decimal(plazo)
    costo_pico_mes = max(costo_total_sin_renta_m) if costo_total_sin_renta_m else costo_prom
    renta_min = costo_pico_mes.quantize(Decimal("1"))

    met = str(inputs.get("metodo_pricing") or "COSTO_SPREAD").upper()
    spread_pct = _d(inputs.get("spread_pct"), "8")
    margen_pct = _d(inputs.get("margen_pct"), "12")
    tir_obj = _d(inputs.get("tir_objetivo_anual_pct"), "14")

    if met == "MARGEN_VENTA":
        renta = renta_margen_sobre_venta(costo_pico_mes, margen_pct)
    elif met == "TIR_OBJETIVO":

        def _fl(r: Decimal) -> list[Decimal]:
            return construir_flujos_caja_inversionista(
                capex,
                plazo,
                r,
                op_m=op_m,
                riesgo_m=riesgo_m,
                comercial_m=com_m,
                valor_residual_terminal=valor_residual,
            )

        renta = buscar_renta_por_tir(renta_min, capex, plazo, tir_obj, _fl)
    else:
        renta = renta_costo_mas_spread(costo_pico_mes, spread_pct)

    renta_sug = max(renta, renta_min)
    iva_mensual = (renta_sug * iva_pct / Decimal("100")).quantize(Decimal("1"))
    renta_bruta = (renta_sug + iva_mensual).quantize(Decimal("1"))

    filas: list[dict[str, Any]] = []
    for t in range(plazo):
        venta = renta_sug
        c_f = fondo_m[t]
        dep = depreciacion_m
        op = op_m[t]
        ri = riesgo_m
        co = com_m
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
                "comercial": float(co),
                "resultado_operacional": float(res_op),
                "margen_bruto_pct": float(mb),
            }
        )

    flujos = construir_flujos_caja_inversionista(
        capex,
        plazo,
        renta_sug,
        op_m=op_m,
        riesgo_m=riesgo_m,
        comercial_m=com_m,
        valor_residual_terminal=valor_residual,
    )
    tir_m = tir_mensual_bisec(flujos)
    tir_a = tir_anual_desde_mensual(tir_m) if tir_m is not None else None
    van = npv_mensual(flujos, i_m)

    acum = Decimal("0")
    payback_m: int | None = None
    for t, cf in enumerate(flujos):
        acum += cf
        if payback_m is None and acum >= 0:
            payback_m = t

    margen_prom = sum(Decimal(str(x["margen_bruto_pct"])) for x in filas) / Decimal(plazo)
    roa = (sum(Decimal(str(x["resultado_operacional"])) for x in filas) / capex * Decimal("100")) if capex > 0 else Decimal("0")

    motor_params = politica.get("motor_decision_v1") or {}
    dec = evaluar_decision(
        van=van,
        tir_anual_pct=tir_a,
        margen_op_promedio_pct=margen_prom,
        ltv_pct=ltv,
        params={k: float(v) if hasattr(v, "real") else v for k, v in motor_params.items()},
    )

    out: dict[str, Any] = {
        "capex_total": float(capex),
        "valor_residual": res_info,
        "collateral": col_out,
        "ltv_pct": float(ltv),
        "lgd_pct": float(lgd_pct),
        "tasa_fondo_mensual_efectiva": float(i_m * Decimal("100")),
        "depreciacion_economica_mensual": float(depreciacion_m),
        "costo_comercial_mensual": float(com_m),
        "prima_riesgo_mensual": float(riesgo_m),
        "costo_total_mensual_promedio": float(costo_prom),
        "renta_minima": float(renta_min),
        "renta_sugerida": float(renta_sug),
        "renta_mensual_neta": float(renta_sug),
        "iva_pct": float(iva_pct),
        "iva_mensual": float(iva_mensual),
        "renta_mensual_bruta": float(renta_bruta),
        "moneda_cotizacion": moneda,
        "tipo_cambio_ref": {
            "uf_clp": float(uf_clp),
            "usd_clp": float(usd_clp),
        },
        "renta_moneda_cotizacion": float(_convertir_desde_clp(renta_sug, moneda, uf_clp, usd_clp)),
        "renta_bruta_moneda_cotizacion": float(_convertir_desde_clp(renta_bruta, moneda, uf_clp, usd_clp)),
        "desglose_renta_mensual": {
            "depreciacion_economica": float(depreciacion_m),
            "costo_fondo": float(sum(fondo_m, Decimal("0")) / Decimal(plazo)),
            "costos_operativos": float(sum(op_m, Decimal("0")) / Decimal(plazo)),
            "prima_riesgo": float(riesgo_m),
            "costo_comercial": float(com_m),
            "spread_ganancia": float((renta_sug - costo_prom).quantize(Decimal("1"))),
        },
        "contabilidad_recomendada": {
            "renta_neta": "CUENTAS_POR_COBRAR",
            "iva_debito": "IVA_DEBITO_FISCAL",
            "costo_fondo": "COSTO_DE_VENTA",
            "costos_mantencion": "COSTO_DE_VENTA",
            "spread_ganancia": "INGRESO_OPERACIONAL",
        },
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
    return out


def merge_politica(rows: list[Any]) -> dict[str, dict[str, Any]]:
    """Convierte filas ORM-like (clave, valor_json) en dict anidado."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = getattr(r, "clave", None) or r.get("clave")
        v = getattr(r, "valor_json", None) or r.get("valor_json")
        if k and isinstance(v, dict):
            out[str(k)] = deepcopy(v)
    return out
