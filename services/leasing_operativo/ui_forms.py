# services/leasing_operativo/ui_forms.py
# -*- coding: utf-8 -*-
"""Parsers y builders de formularios UI del leasing operativo."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException


def parse_dec(raw: str | None, default: str = "0") -> Decimal:
    v = str(raw or "").strip()
    if not v:
        return Decimal(default)
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except Exception:
        return Decimal(default)


def parse_int(raw: str | None, d: int = 0) -> int:
    try:
        return int(str(raw or "").strip())
    except Exception:
        return d


def parse_date(raw: str | None) -> date:
    v = (raw or "").strip()
    if not v:
        return datetime.utcnow().date()
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return datetime.utcnow().date()


def parse_num(raw: str | None, default: str = "0") -> float:
    return float(parse_dec(raw, default))


def build_inputs_from_form(form: dict[str, str]) -> dict:
    return {
        "moneda": (form.get("moneda") or "CLP").upper(),
        "iva_pct": form.get("iva_pct") or "19",
        "market_data": {
            "uf_clp": form.get("uf_clp"),
            "usd_clp": form.get("usd_clp"),
            "ipc_pct": form.get("ipc_pct"),
            "source": form.get("market_source"),
            "as_of": form.get("market_as_of"),
        },
        "capex": {
            "precio_compra": form.get("precio_compra"),
            "importacion": form.get("importacion"),
            "inscripcion": form.get("inscripcion"),
            "patente": form.get("patente"),
            "gps_telemetria": form.get("gps_telemetria"),
            "traslado": form.get("traslado"),
            "acondicionamiento": form.get("acondicionamiento"),
            "puesta_marcha": form.get("puesta_marcha"),
            "comision_proveedor": form.get("comision_proveedor"),
            "otros_activables": form.get("otros_activables"),
        },
        "uso": {"km_anual": form.get("km_anual"), "horas_anual": form.get("horas_anual")},
        "activo": {
            "marca_modelo_factor": form.get("marca_modelo_factor"),
            "sector_economico_mult": form.get("sector_economico_mult"),
            "inflacion_activo_pct_anual": form.get("inflacion_activo_pct_anual"),
            "condicion_factor": form.get("condicion_factor"),
        },
        "collateral": {
            "valor_mercado": form.get("col_valor_mercado"),
            "costo_repossession": form.get("col_repossession"),
            "costo_legal": form.get("col_legal"),
            "transporte": form.get("col_transporte"),
            "reacondicionamiento": form.get("col_reacond"),
            "descuento_venta_forzada_pct": form.get("col_desc_forzada_pct"),
            "meses_liquidacion": form.get("col_meses_liq"),
            "tasa_fin_liquidacion_mensual": form.get("col_tasa_fin_m"),
        },
        "comercial": {
            "comision_vendedor": form.get("com_vendedor"),
            "comision_canal": form.get("com_canal"),
            "costo_adquisicion": form.get("com_adq"),
            "evaluacion": form.get("com_eval"),
            "legal": form.get("com_legal"),
            "onboarding": form.get("com_onb"),
        },
        "riesgo": {
            "segmento_cliente": (form.get("riesgo_segmento") or "MEDIO").upper(),
            "sector_mult": form.get("riesgo_sector_mult"),
            "activo_mult": form.get("riesgo_activo_mult"),
            "uso_intensivo_mult": form.get("riesgo_uso_mult"),
            "liquidez_mult": form.get("riesgo_liq_mult"),
        },
    }


def parse_unidades_y_inputs(
    *,
    unidades_json: str,
    tipo_activo_id: str,
    moneda: str,
    iva_pct: str,
    uf_clp: str,
    usd_clp: str,
    ipc_pct: str,
    market_source: str,
    market_as_of: str,
    cliente_id: str,
    metodo_pricing: str,
    activo_marca: str = "",
    activo_modelo: str = "",
    activo_anio: str = "",
    precio_compra: str = "0",
    km_anual: str = "0",
    horas_anual: str = "0",
    importacion: str = "0",
    inscripcion: str = "0",
    patente: str = "0",
    gps_telemetria: str = "0",
    traslado: str = "0",
    acondicionamiento: str = "0",
    puesta_marcha: str = "0",
    comision_proveedor: str = "0",
    otros_activables: str = "0",
    marca_modelo_factor: str = "1",
    sector_economico_mult: str = "1",
    inflacion_activo_pct_anual: str = "0",
    condicion_factor: str = "1",
    col_valor_mercado: str = "0",
    col_repossession: str = "0",
    col_legal: str = "0",
    col_transporte: str = "0",
    col_reacond: str = "0",
    col_desc_forzada_pct: str = "12",
    col_meses_liq: str = "4",
    col_tasa_fin_m: str = "0.008",
    com_vendedor: str = "0",
    com_canal: str = "0",
    com_adq: str = "0",
    com_eval: str = "0",
    com_legal: str = "0",
    com_onb: str = "0",
    riesgo_segmento: str = "MEDIO",
    riesgo_sector_mult: str = "1",
    riesgo_activo_mult: str = "1",
    riesgo_uso_mult: str = "1",
    riesgo_liq_mult: str = "1",
) -> tuple[int, int | None, str, dict]:
    cid_raw = str(cliente_id or "").strip()
    cid = parse_int(cid_raw, 0) or None
    met = str(metodo_pricing or "COSTO_SPREAD").upper()[:24]
    unidades: list = []
    try:
        parsed = json.loads(unidades_json or "[]")
        if isinstance(parsed, list):
            unidades = [u for u in parsed if isinstance(u, dict)]
    except Exception:
        unidades = []

    if unidades:
        tid = parse_int(str(unidades[0].get("tipo_activo_id") or tipo_activo_id), 0)
        inputs = {
            "moneda": (moneda or "CLP").upper(),
            "iva_pct": iva_pct or "19",
            "market_data": {
                "uf_clp": uf_clp,
                "usd_clp": usd_clp,
                "ipc_pct": ipc_pct,
                "source": market_source,
                "as_of": market_as_of,
            },
            "unidades": unidades,
            "cotizacion_modo": "FLOTA",
        }
    else:
        tid = parse_int(tipo_activo_id, 0)
        if tid <= 0:
            raise HTTPException(400, "Agregue al menos una unidad o indique tipo de activo")
        form = {
            "precio_compra": precio_compra,
            "moneda": moneda,
            "iva_pct": iva_pct,
            "uf_clp": uf_clp,
            "usd_clp": usd_clp,
            "ipc_pct": ipc_pct,
            "market_source": market_source,
            "market_as_of": market_as_of,
            "importacion": importacion,
            "inscripcion": inscripcion,
            "patente": patente,
            "gps_telemetria": gps_telemetria,
            "traslado": traslado,
            "acondicionamiento": acondicionamiento,
            "puesta_marcha": puesta_marcha,
            "comision_proveedor": comision_proveedor,
            "otros_activables": otros_activables,
            "km_anual": km_anual,
            "horas_anual": horas_anual,
            "marca_modelo_factor": marca_modelo_factor,
            "sector_economico_mult": sector_economico_mult,
            "inflacion_activo_pct_anual": inflacion_activo_pct_anual,
            "condicion_factor": condicion_factor,
            "activo_marca": activo_marca,
            "activo_modelo": activo_modelo,
            "activo_anio": activo_anio,
            "col_valor_mercado": col_valor_mercado,
            "col_repossession": col_repossession,
            "col_legal": col_legal,
            "col_transporte": col_transporte,
            "col_reacond": col_reacond,
            "col_desc_forzada_pct": col_desc_forzada_pct,
            "col_meses_liq": col_meses_liq,
            "col_tasa_fin_m": col_tasa_fin_m,
            "com_vendedor": com_vendedor,
            "com_canal": com_canal,
            "com_adq": com_adq,
            "com_eval": com_eval,
            "com_legal": com_legal,
            "com_onb": com_onb,
            "riesgo_segmento": riesgo_segmento,
            "riesgo_sector_mult": riesgo_sector_mult,
            "riesgo_activo_mult": riesgo_activo_mult,
            "riesgo_uso_mult": riesgo_uso_mult,
            "riesgo_liq_mult": riesgo_liq_mult,
        }
        inputs = build_inputs_from_form(form)
        inputs["activo"]["marca"] = activo_marca
        inputs["activo"]["modelo"] = activo_modelo
        inputs["activo"]["anio"] = parse_int(activo_anio, 0)

    if tid <= 0:
        raise HTTPException(400, "Tipo de activo requerido")
    return tid, cid, met, inputs
