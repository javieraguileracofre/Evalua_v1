# services/leasing_operativo/lop_service.py
# -*- coding: utf-8 -*-
"""Orquestación LOP v2: cálculo desde sesión DB (preview, persistencia)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from crud.leasing_operativo import crud as lo_crud
from services.leasing_operativo.economic_engine import merge_politica, preparar_inputs_simulacion, run_economic_engine
from services.leasing_operativo.sensitivity import run_escenarios_comparados, run_sensitivity_matrix


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


def cargar_contexto_motor(db: Session, tipo_activo_id: int) -> tuple[Any, dict, list, Any | None]:
    tipo = lo_crud.obtener_tipo(db, tipo_activo_id)
    if not tipo:
        raise ValueError("Tipo de activo inválido")
    politica = merge_politica(lo_crud.listar_politica(db))
    plantillas = lo_crud.plantillas_por_tipo(db, tipo_activo_id)
    param = lo_crud.obtener_parametro_tipo(db, tipo_activo_id)
    return tipo, politica, plantillas, param


def aplicar_riesgo_cliente(db: Session, inp: dict[str, Any], cliente_id: int | None) -> dict[str, Any]:
    if not cliente_id:
        return inp
    seg = lo_crud.segmento_riesgo_cliente(db, int(cliente_id))
    if not seg:
        return inp
    riesgo = dict(inp.get("riesgo") or {})
    if not riesgo.get("segmento_cliente"):
        riesgo["segmento_cliente"] = seg.get("segmento")
    if seg.get("sector_mult") and riesgo.get("sector_mult") in (None, "", 1, "1"):
        riesgo["sector_mult"] = seg.get("sector_mult")
    inp["riesgo"] = riesgo
    inp["_riesgo_cliente_ref"] = seg
    return inp


def calcular_preview(
    db: Session,
    *,
    tipo_activo_id: int,
    cliente_id: int | None,
    inputs: dict[str, Any],
    plazo_meses: int,
    escenario: str,
    metodo_pricing: str,
    margen_pct: Any = None,
    spread_pct: Any = None,
    tir_objetivo: Any = None,
    indexacion_tipo: str | None = None,
    indexacion_pct: Any = None,
    pie_inicial_pct: Any = None,
    opcion_compra_pct: Any = None,
    incluir_sensibilidad: bool = False,
    incluir_escenarios: bool = False,
) -> dict[str, Any]:
    tipo, politica, plantillas, param = cargar_contexto_motor(db, tipo_activo_id)
    inp = preparar_inputs_simulacion(
        inputs=inputs,
        tipo_activo_id=tipo_activo_id,
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
    inp = aplicar_riesgo_cliente(db, inp, cliente_id)
    result = run_economic_engine(
        inputs=inp,
        tipo_activo=_tipo_dict(tipo),
        politica=politica,
        plantillas_costo=plantillas,
    )
    payload: dict[str, Any] = {"inputs": inp, "result": result}
    if incluir_sensibilidad:
        payload["sensibilidad"] = run_sensitivity_matrix(
            inputs=inp,
            tipo_activo=_tipo_dict(tipo),
            politica=politica,
            plantillas_costo=plantillas,
        )
    if incluir_escenarios:
        payload["escenarios"] = run_escenarios_comparados(
            inputs=inp,
            tipo_activo=_tipo_dict(tipo),
            politica=politica,
            plantillas_costo=plantillas,
        )
    return payload
