# services/leasing_operativo/cotizacion_flota.py
# -*- coding: utf-8 -*-
"""Cotización LOP multi-unidad: residual editable + agregación de flota."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from crud.leasing_operativo import crud as lo_crud
from services.leasing_operativo.economic_engine import (
    merge_politica,
    preparar_inputs_simulacion,
    run_economic_engine,
)
from services.leasing_operativo.lease_profitability_service import compute_deal_score
from services.leasing_operativo.residual_model import TIPOS_USO
from services.leasing_operativo.residual_value_service import merge_residual_policy


def _d(v: Any, default: str = "0") -> Decimal:
    if v is None:
        return Decimal(default)
    if isinstance(v, Decimal):
        return v
    try:
        s = str(v).strip().replace(" ", "")
        if "," in s and "." in s:
            # 28.500.000,50 → 28500000.50
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        elif s.count(".") > 1:
            # 28.500.000 (CLP miles)
            s = s.replace(".", "")
        return Decimal(s)
    except Exception:
        return Decimal(default)


def _tipo_dict(tipo: Any) -> dict[str, Any]:
    return {
        "residual_base_pct": tipo.residual_base_pct,
        "residual_max_pct": tipo.residual_max_pct,
        "liquidez_factor": tipo.liquidez_factor,
        "obsolescencia_factor": tipo.obsolescencia_factor,
        "desgaste_km_factor": tipo.desgaste_km_factor,
        "desgaste_hora_factor": tipo.desgaste_hora_factor,
        "haircut_residual_pct": tipo.haircut_residual_pct,
    }


def normalizar_unidad(raw: dict[str, Any], idx: int = 0) -> dict[str, Any]:
    uid = str(raw.get("id") or f"u-{idx + 1}-{uuid4().hex[:6]}")
    cantidad = max(int(raw.get("cantidad") or 1), 1)
    valor = max(_d(raw.get("valor_bien") or raw.get("precio_compra")), Decimal("0"))
    tipo_uso = str(raw.get("tipo_uso") or "INTERURBANO").upper()
    if tipo_uso not in TIPOS_USO:
        tipo_uso = "INTERURBANO"
    marca = str(raw.get("marca") or "").strip()
    modelo = str(raw.get("modelo") or "").strip()
    anio = int(raw.get("anio") or 0) or None
    desc = str(raw.get("descripcion") or "").strip()
    if not desc:
        partes = [p for p in (marca, modelo, str(anio) if anio else "") if p]
        desc = " ".join(partes) or f"Unidad {idx + 1}"
    out = {
        "id": uid,
        "tipo_activo_id": int(raw.get("tipo_activo_id") or 0),
        "descripcion": desc[:200],
        "marca": marca,
        "modelo": modelo,
        "version": str(raw.get("version") or "").strip(),
        "anio": anio,
        "cantidad": cantidad,
        "valor_bien": float(valor),
        "tipo_uso": tipo_uso,
        "km_anual": float(max(_d(raw.get("km_anual"), "40000"), Decimal("0"))),
        "km_inicial": float(max(_d(raw.get("km_inicial")), Decimal("0"))),
        "residual_sugerido": float(max(_d(raw.get("residual_sugerido")), Decimal("0"))),
        "residual_aceptado": float(max(_d(raw.get("residual_aceptado") or raw.get("residual_sugerido")), Decimal("0"))),
        "residual_fuente": str(raw.get("residual_fuente") or "modelo_interno"),
    }
    # Preservar respaldo auditable y análisis (no re-scrapear en preview)
    if isinstance(raw.get("residual_estimacion"), dict):
        out["residual_estimacion"] = raw["residual_estimacion"]
    if isinstance(raw.get("analisis_residual"), dict):
        out["analisis_residual"] = raw["analisis_residual"]
    if raw.get("residual_override_motivo"):
        out["residual_override_motivo"] = str(raw.get("residual_override_motivo"))
    return out


def estimar_residual_unidad(
    unidad: dict[str, Any],
    *,
    plazo_meses: int,
    tipo_activo: Any,
    consultar_mercado: bool = True,
    politica: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Motor profesional RV (mercado ponderado + escenarios + libro/recupero/riesgo)."""
    from services.leasing_operativo.residual_value_service import enrich_unit_with_residual_engine

    pol = politica
    if pol is None and db is not None:
        pol = merge_politica(lo_crud.listar_politica(db))
    return enrich_unit_with_residual_engine(
        unidad,
        plazo_meses=plazo_meses,
        tipo_activo=tipo_activo,
        politica=pol,
        consultar_mercado=consultar_mercado,
    )


def _enrich_unit_deal_with_pricing(
    unidad: dict[str, Any],
    *,
    result_unit: dict[str, Any],
    politica: dict[str, Any],
) -> dict[str, Any]:
    """Recalcula DEAL_SCORE con TIR/VAN/margen/LTV del motor económico (fase final usuario)."""
    out = dict(unidad)
    est = dict(out.get("residual_estimacion") or {})
    if not est:
        return out
    rv_pol = merge_residual_policy(politica)
    costo = _d(out.get("valor_bien"))
    residual = _d(out.get("residual_aceptado") or out.get("residual_sugerido") or est.get("valor_residual_sugerido"))
    residual_pct = float((residual / costo * Decimal("100")).quantize(Decimal("0.01"))) if costo > 0 else 0.0
    risk_score = ((est.get("riesgo") or {}).get("RESIDUAL_RISK_SCORE"))
    if risk_score is None:
        risk_score = 40.0
    collateral = result_unit.get("collateral") if isinstance(result_unit.get("collateral"), dict) else {}
    ltv = result_unit.get("ltv_pct")
    if ltv is None:
        ltv = collateral.get("ltv_pct")
    deal = compute_deal_score(
        tir_anual_pct=result_unit.get("tir_anual_pct"),
        van=result_unit.get("van"),
        margen_pct=result_unit.get("margen_operacional_promedio_pct"),
        residual_pct=residual_pct,
        residual_risk_score=risk_score,
        ltv_pct=ltv,
        thresholds=rv_pol.get("deal_thresholds"),
    )
    rentabilidad = {
        "tir_anual_pct": result_unit.get("tir_anual_pct"),
        "van": result_unit.get("van"),
        "margen_operacional_promedio_pct": result_unit.get("margen_operacional_promedio_pct"),
        "ltv_pct": ltv,
        "renta_sugerida": result_unit.get("renta_sugerida"),
        "renta_mensual_bruta": result_unit.get("renta_mensual_bruta"),
        "decision_motor": (result_unit.get("decision") or {}).get("decision_codigo"),
    }
    est["deal"] = deal
    est["rentabilidad"] = rentabilidad
    est["deal_con_pricing"] = True
    out["residual_estimacion"] = est
    analisis = dict(out.get("analisis_residual") or {})
    analisis["deal"] = deal
    analisis["rentabilidad"] = rentabilidad
    analisis["decision"] = deal.get("DECISION")
    out["analisis_residual"] = analisis
    return out


def _inputs_desde_unidad(
    unidad: dict[str, Any],
    *,
    base_inputs: dict[str, Any],
) -> dict[str, Any]:
    inp = deepcopy(base_inputs)
    valor = _d(unidad.get("valor_bien"))
    residual = _d(unidad.get("residual_aceptado") or unidad.get("residual_sugerido"))
    capex = dict(inp.get("capex") or {})
    capex["precio_compra"] = float(valor)
    for k in (
        "importacion",
        "inscripcion",
        "patente",
        "gps_telemetria",
        "traslado",
        "acondicionamiento",
        "puesta_marcha",
        "comision_proveedor",
        "otros_activables",
    ):
        capex.setdefault(k, 0)
    inp["capex"] = capex
    inp["uso"] = {
        "km_anual": unidad.get("km_anual") or 0,
        "horas_anual": (inp.get("uso") or {}).get("horas_anual") or 0,
        "tipo_uso": unidad.get("tipo_uso"),
    }
    activo = dict(inp.get("activo") or {})
    activo["marca"] = unidad.get("marca")
    activo["modelo"] = unidad.get("modelo")
    activo["anio"] = unidad.get("anio")
    activo.setdefault("marca_modelo_factor", 1)
    activo.setdefault("condicion_factor", 1)
    inp["activo"] = activo
    col = dict(inp.get("collateral") or {})
    if _d(col.get("valor_mercado")) <= 0:
        col["valor_mercado"] = float(valor)
    inp["collateral"] = col
    inp["residual"] = {
        "valor_sugerido": unidad.get("residual_sugerido"),
        "valor_aceptado": float(residual),
        "fuente": unidad.get("residual_fuente") or "modelo_interno",
        "estimacion": unidad.get("residual_estimacion"),
    }
    inp["valor_residual_override"] = float(residual)
    return inp


def _escalar_result(result: dict[str, Any], cantidad: int) -> dict[str, Any]:
    qty = max(int(cantidad), 1)
    if qty == 1:
        out = dict(result)
        out["cantidad"] = 1
        return out
    money_keys = (
        "capex_total",
        "capex_financiado",
        "pie_inicial",
        "renta_minima",
        "renta_minima_pico",
        "renta_minima_promedio",
        "renta_sugerida",
        "renta_mensual_neta",
        "renta_mensual_bruta",
        "iva_mensual",
        "renta_moneda_cotizacion",
        "renta_bruta_moneda_cotizacion",
        "van",
        "depreciacion_economica_mensual",
        "costo_comercial_mensual",
        "costo_comercial_upfront",
        "costo_total_mensual_promedio",
        "prima_riesgo_mensual",
        "capital_amortizable",
    )
    out = deepcopy(result)
    for k in money_keys:
        if k in out and out[k] is not None:
            try:
                out[k] = float(out[k]) * qty
            except (TypeError, ValueError):
                pass
    vr = dict(out.get("valor_residual") or {})
    for k in ("valor_residual_base", "valor_residual_ajustado", "valor_residual_sugerido"):
        if k in vr and vr[k] is not None:
            try:
                vr[k] = float(vr[k]) * qty
            except (TypeError, ValueError):
                pass
    out["valor_residual"] = vr
    desg = dict(out.get("desglose_renta_mensual") or {})
    for k, v in list(desg.items()):
        try:
            desg[k] = float(v) * qty
        except (TypeError, ValueError):
            pass
    out["desglose_renta_mensual"] = desg
    wf = []
    for item in out.get("waterfall") or []:
        it = dict(item)
        try:
            it["monto"] = float(it.get("monto") or 0) * qty
        except (TypeError, ValueError):
            pass
        wf.append(it)
    out["waterfall"] = wf
    out["cantidad"] = qty
    out["renta_unitaria"] = float(result.get("renta_sugerida") or 0)
    return out


def _agregar_resultados(lineas: list[dict[str, Any]]) -> dict[str, Any]:
    if not lineas:
        raise ValueError("Debe incluir al menos una unidad en la cotización.")
    base = deepcopy(lineas[0]["result"])
    keys = (
        "capex_total",
        "capex_financiado",
        "pie_inicial",
        "renta_minima",
        "renta_minima_pico",
        "renta_sugerida",
        "renta_mensual_neta",
        "renta_mensual_bruta",
        "iva_mensual",
        "renta_moneda_cotizacion",
        "renta_bruta_moneda_cotizacion",
        "van",
        "depreciacion_economica_mensual",
        "costo_total_mensual_promedio",
        "capital_amortizable",
    )
    for k in keys:
        base[k] = 0.0
    residual_total = 0.0
    unidades_totales = 0
    for ln in lineas:
        r = ln["result"]
        qty = int(ln.get("cantidad") or 1)
        unidades_totales += qty
        for k in keys:
            try:
                base[k] = float(base.get(k) or 0) + float(r.get(k) or 0)
            except (TypeError, ValueError):
                pass
        vr = (r.get("valor_residual") or {}).get("valor_residual_ajustado") or 0
        residual_total += float(vr)
    # TIR / margen / decisión: ponderar por CAPEX de línea
    capex_w = sum(float(ln["result"].get("capex_total") or 0) for ln in lineas) or 1.0
    tir_acc = 0.0
    margen_acc = 0.0
    for ln in lineas:
        w = float(ln["result"].get("capex_total") or 0) / capex_w
        if ln["result"].get("tir_anual_pct") is not None:
            tir_acc += float(ln["result"]["tir_anual_pct"]) * w
        margen_acc += float(ln["result"].get("margen_operacional_promedio_pct") or 0) * w
    base["tir_anual_pct"] = round(tir_acc, 4)
    base["margen_operacional_promedio_pct"] = round(margen_acc, 4)
    base["valor_residual"] = {
        "valor_residual_ajustado": residual_total,
        "agregado_flota": True,
    }
    base["flota"] = {
        "unidades_totales": unidades_totales,
        "lineas": len(lineas),
        "renta_mensual_flota": base.get("renta_sugerida"),
        "capital_amortizable_flota": base.get("capital_amortizable"),
    }
    # Decisión: peor semáforo entre líneas
    orden = {"RECHAZAR": 3, "OBSERVAR": 2, "PENDIENTE": 1, "APROBAR": 0}
    peor = lineas[0]["result"].get("decision") or {}
    peor_score = orden.get(str(peor.get("decision_codigo") or "PENDIENTE"), 1)
    for ln in lineas[1:]:
        d = ln["result"].get("decision") or {}
        sc = orden.get(str(d.get("decision_codigo") or "PENDIENTE"), 1)
        if sc > peor_score:
            peor, peor_score = d, sc
    base["decision"] = peor
    base["engine_version"] = "2.1-flota"
    return base


def calcular_cotizacion_flota(
    db: Session,
    *,
    unidades: list[dict[str, Any]],
    plazo_meses: int,
    escenario: str = "BASE",
    metodo_pricing: str = "COSTO_SPREAD",
    margen_pct: Any = None,
    spread_pct: Any = None,
    tir_objetivo: Any = None,
    cliente_id: int | None = None,
    indexacion_tipo: str = "NINGUNA",
    indexacion_pct: Any = 0,
    pie_inicial_pct: Any = 0,
    opcion_compra_pct: Any = 0,
    moneda: str = "CLP",
    iva_pct: Any = 19,
    market_data: dict[str, Any] | None = None,
    estimar_residual_si_falta: bool = True,
) -> dict[str, Any]:
    """
    Calcula una cotización con 1..N líneas (cantidad por línea).
    Retorna result agregado + detalle por línea + unidades normalizadas.
    """
    if not unidades:
        raise ValueError("Debe agregar al menos una unidad a la cotización.")

    politica = merge_politica(lo_crud.listar_politica(db))
    lineas_out: list[dict[str, Any]] = []
    unidades_norm: list[dict[str, Any]] = []

    for i, raw in enumerate(unidades):
        u = normalizar_unidad(raw, i)
        tid = int(u.get("tipo_activo_id") or 0)
        if tid <= 0:
            raise ValueError(f"Unidad {i + 1}: tipo de activo requerido.")
        tipo = lo_crud.obtener_tipo(db, tid)
        if not tipo:
            raise ValueError(f"Unidad {i + 1}: tipo de activo inválido.")
        if _d(u.get("valor_bien")) <= 0:
            raise ValueError(f"Unidad {i + 1}: indique el valor del bien.")

        # Solo estimar residual (y consultar mercado) si falta; evita 503/timeouts en preview.
        needs_residual = _d(u.get("residual_sugerido")) <= 0 and _d(u.get("residual_aceptado")) <= 0
        if estimar_residual_si_falta and needs_residual:
            u = estimar_residual_unidad(
                u, plazo_meses=plazo_meses, tipo_activo=tipo, politica=politica, db=db
            )
        else:
            u["capital_amortizable_unitario"] = float(
                max(_d(u["valor_bien"]) - _d(u.get("residual_aceptado") or u.get("residual_sugerido")), Decimal("0"))
            )

        if _d(u.get("residual_aceptado")) <= 0:
            u["residual_aceptado"] = u.get("residual_sugerido") or 0

        plantillas = lo_crud.plantillas_por_tipo(db, tid)
        if not plantillas:
            raise ValueError(f"El tipo «{tipo.nombre}» no tiene plantillas de costo configuradas.")
        param = lo_crud.obtener_parametro_tipo(db, tid)

        base_inputs: dict[str, Any] = {
            "moneda": moneda,
            "iva_pct": iva_pct,
            "market_data": market_data or {},
        }
        inp = _inputs_desde_unidad(u, base_inputs=base_inputs)
        inp = preparar_inputs_simulacion(
            inputs=inp,
            tipo_activo_id=tid,
            param_tipo=param,
            plazo_meses=plazo_meses,
            escenario=escenario,
            metodo_pricing=metodo_pricing,
            margen_pct=margen_pct,
            spread_pct=spread_pct,
            tir_objetivo=tir_objetivo,
            indexacion_tipo=indexacion_tipo,
            indexacion_pct=indexacion_pct,
            pie_inicial_pct=pie_inicial_pct,
            opcion_compra_pct=opcion_compra_pct,
        )
        if cliente_id:
            inp = lo_crud.aplicar_segmento_cliente_inputs(db, inp, cliente_id)

        result_unit = run_economic_engine(
            inputs=inp,
            tipo_activo=_tipo_dict(tipo),
            politica=politica,
            plantillas_costo=plantillas,
        )
        # Fase final: enriquecer deal score con TIR/VAN/margen reales del pricing
        u = _enrich_unit_deal_with_pricing(u, result_unit=result_unit, politica=politica)
        result_line = _escalar_result(result_unit, int(u["cantidad"]))
        lineas_out.append(
            {
                "id": u["id"],
                "descripcion": u["descripcion"],
                "tipo_activo_id": tid,
                "tipo_nombre": tipo.nombre,
                "cantidad": int(u["cantidad"]),
                "valor_bien_unitario": u["valor_bien"],
                "residual_aceptado_unitario": u["residual_aceptado"],
                "capital_amortizable_unitario": u.get("capital_amortizable_unitario"),
                "tipo_uso": u["tipo_uso"],
                "km_anual": u["km_anual"],
                "result": result_line,
                "result_unitario": result_unit,
                "deal": (u.get("analisis_residual") or {}).get("deal")
                or (u.get("residual_estimacion") or {}).get("deal"),
            }
        )
        unidades_norm.append(u)

    agregado = _agregar_resultados(lineas_out)
    # Deal de flota: peor clasificación entre líneas
    deal_rank = {
        "NO RECOMENDADO": 5,
        "REVISAR": 4,
        "APROBAR CON CONDICIONES": 3,
        "PENDIENTE_PRICING": 2,
        "APROBAR": 1,
    }
    peor_deal = None
    peor_rank = -1
    for ln in lineas_out:
        d = ln.get("deal") or {}
        sc = deal_rank.get(str(d.get("DECISION") or ""), 0)
        if sc > peor_rank:
            peor_rank, peor_deal = sc, d
    agregado["evaluacion_economica"] = {
        "tir_anual_pct": agregado.get("tir_anual_pct"),
        "van": agregado.get("van"),
        "margen_operacional_promedio_pct": agregado.get("margen_operacional_promedio_pct"),
        "deal": peor_deal,
        "decision": (peor_deal or {}).get("DECISION"),
        "deal_score": (peor_deal or {}).get("DEAL_SCORE"),
    }
    agregado["lineas"] = [
        {
            "id": ln["id"],
            "descripcion": ln["descripcion"],
            "tipo_nombre": ln["tipo_nombre"],
            "cantidad": ln["cantidad"],
            "valor_bien_unitario": ln["valor_bien_unitario"],
            "residual_aceptado_unitario": ln["residual_aceptado_unitario"],
            "capital_amortizable_unitario": ln["capital_amortizable_unitario"],
            "renta_unitaria": float((ln["result_unitario"] or {}).get("renta_sugerida") or 0),
            "renta_linea": float((ln["result"] or {}).get("renta_sugerida") or 0),
            "capex_linea": float((ln["result"] or {}).get("capex_total") or 0),
            "tipo_uso": ln["tipo_uso"],
            "km_anual": ln["km_anual"],
            "decision": (ln["result_unitario"] or {}).get("decision"),
            "deal": ln.get("deal"),
            "tir_anual_pct": (ln["result_unitario"] or {}).get("tir_anual_pct"),
            "van": (ln["result_unitario"] or {}).get("van"),
        }
        for ln in lineas_out
    ]
    return {
        "unidades": unidades_norm,
        "result": agregado,
        "tipo_activo_id_principal": int(unidades_norm[0]["tipo_activo_id"]),
        "total_unidades": sum(int(u["cantidad"]) for u in unidades_norm),
    }


def estimar_residuales_flota(
    db: Session,
    *,
    unidades: list[dict[str, Any]],
    plazo_meses: int,
) -> list[dict[str, Any]]:
    politica = merge_politica(lo_crud.listar_politica(db))
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(unidades or []):
        u = normalizar_unidad(raw, i)
        tid = int(u.get("tipo_activo_id") or 0)
        tipo = lo_crud.obtener_tipo(db, tid) if tid else None
        if not tipo:
            raise ValueError(f"Unidad {i + 1}: tipo de activo inválido.")
        out.append(
            estimar_residual_unidad(
                u,
                plazo_meses=plazo_meses,
                tipo_activo=tipo,
                politica=politica,
                db=db,
            )
        )
    return out
