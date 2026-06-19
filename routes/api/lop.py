# routes/api/lop.py
# -*- coding: utf-8 -*-
"""API JSON leasing operativo v2 (preview, sensibilidad, escenarios)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.rbac import usuario_es_admin, usuario_puede_consultar_modulos_operacion, usuario_puede_mutar_modulos_operacion
from crud.leasing_operativo import crud as lo_crud
from db.session import get_db
from services.leasing_operativo.lop_service import calcular_preview
from services.leasing_operativo.sensitivity import run_escenarios_comparados, run_sensitivity_matrix
from services.leasing_operativo.economic_engine import merge_politica

router = APIRouter(tags=["API · Leasing operativo"])


class LOPSimularPreviewBody(BaseModel):
    tipo_activo_id: int = Field(..., gt=0)
    cliente_id: int | None = None
    plazo_meses: int = Field(36, ge=1, le=120)
    escenario: str = "BASE"
    metodo_pricing: str = "COSTO_SPREAD"
    spread_pct: Decimal | None = None
    margen_pct: Decimal | None = None
    tir_objetivo: Decimal | None = None
    indexacion_tipo: str = "NINGUNA"
    indexacion_pct: Decimal = Decimal("0")
    pie_inicial_pct: Decimal = Decimal("0")
    opcion_compra_pct: Decimal = Decimal("0")
    moneda: str = "CLP"
    iva_pct: Decimal = Decimal("19")
    inputs: dict[str, Any] = Field(default_factory=dict)
    incluir_sensibilidad: bool = False
    incluir_escenarios: bool = False


def _auth_consulta(request: Request) -> None:
    if not usuario_puede_consultar_modulos_operacion(getattr(request.state, "auth_user", None)):
        raise HTTPException(status_code=403, detail="Sin permiso para consultar leasing operativo.")


def _auth_mutacion(request: Request) -> None:
    if not usuario_puede_mutar_modulos_operacion(getattr(request.state, "auth_user", None)):
        raise HTTPException(status_code=403, detail="Sin permiso para modificar leasing operativo.")


def _build_inputs(body: LOPSimularPreviewBody) -> dict[str, Any]:
    inp = dict(body.inputs or {})
    inp.setdefault("moneda", body.moneda)
    inp.setdefault("iva_pct", body.iva_pct)
    inp.setdefault("plazo_meses", body.plazo_meses)
    return inp


@router.post("/simular/preview")
def api_simular_preview(
    request: Request,
    body: LOPSimularPreviewBody,
    db: Session = Depends(get_db),
):
    _auth_consulta(request)
    try:
        payload = calcular_preview(
            db,
            tipo_activo_id=body.tipo_activo_id,
            cliente_id=body.cliente_id,
            inputs=_build_inputs(body),
            plazo_meses=body.plazo_meses,
            escenario=body.escenario.upper(),
            metodo_pricing=body.metodo_pricing.upper(),
            margen_pct=body.margen_pct,
            spread_pct=body.spread_pct,
            tir_objetivo=body.tir_objetivo,
            indexacion_tipo=body.indexacion_tipo.upper(),
            indexacion_pct=body.indexacion_pct,
            pie_inicial_pct=body.pie_inicial_pct,
            opcion_compra_pct=body.opcion_compra_pct,
            incluir_sensibilidad=body.incluir_sensibilidad,
            incluir_escenarios=body.incluir_escenarios,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return payload


@router.post("/simular/sensibilidad")
def api_simular_sensibilidad(
    request: Request,
    body: LOPSimularPreviewBody,
    db: Session = Depends(get_db),
):
    _auth_consulta(request)
    from services.leasing_operativo.lop_service import aplicar_riesgo_cliente, cargar_contexto_motor
    from services.leasing_operativo.economic_engine import preparar_inputs_simulacion

    try:
        tipo, politica, plantillas, param = cargar_contexto_motor(db, body.tipo_activo_id)
        inp = preparar_inputs_simulacion(
            inputs=_build_inputs(body),
            tipo_activo_id=body.tipo_activo_id,
            param_tipo=param,
            plazo_meses=body.plazo_meses,
            escenario=body.escenario.upper(),
            metodo_pricing=body.metodo_pricing.upper(),
            margen_pct=body.margen_pct,
            spread_pct=body.spread_pct,
            tir_objetivo=body.tir_objetivo,
            indexacion_tipo=body.indexacion_tipo,
            indexacion_pct=body.indexacion_pct,
            pie_inicial_pct=body.pie_inicial_pct,
            opcion_compra_pct=body.opcion_compra_pct,
        )
        inp = aplicar_riesgo_cliente(db, inp, body.cliente_id)
        tipo_d = {
            "residual_base_pct": tipo.residual_base_pct,
            "residual_max_pct": tipo.residual_max_pct,
            "liquidez_factor": tipo.liquidez_factor,
            "obsolescencia_factor": tipo.obsolescencia_factor,
            "desgaste_km_factor": tipo.desgaste_km_factor,
            "desgaste_hora_factor": tipo.desgaste_hora_factor,
            "haircut_residual_pct": tipo.haircut_residual_pct,
        }
        return run_sensitivity_matrix(
            inputs=inp,
            tipo_activo=tipo_d,
            politica=politica,
            plantillas_costo=plantillas,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/simular/escenarios")
def api_simular_escenarios(
    request: Request,
    body: LOPSimularPreviewBody,
    db: Session = Depends(get_db),
):
    _auth_consulta(request)
    from services.leasing_operativo.lop_service import cargar_contexto_motor, aplicar_riesgo_cliente
    from services.leasing_operativo.economic_engine import preparar_inputs_simulacion

    try:
        tipo, politica, plantillas, param = cargar_contexto_motor(db, body.tipo_activo_id)
        inp = preparar_inputs_simulacion(
            inputs=_build_inputs(body),
            tipo_activo_id=body.tipo_activo_id,
            param_tipo=param,
            plazo_meses=body.plazo_meses,
            escenario="BASE",
            metodo_pricing=body.metodo_pricing.upper(),
            margen_pct=body.margen_pct,
            spread_pct=body.spread_pct,
            tir_objetivo=body.tir_objetivo,
            indexacion_tipo=body.indexacion_tipo,
            indexacion_pct=body.indexacion_pct,
            pie_inicial_pct=body.pie_inicial_pct,
            opcion_compra_pct=body.opcion_compra_pct,
        )
        inp = aplicar_riesgo_cliente(db, inp, body.cliente_id)
        tipo_d = {
            "residual_base_pct": tipo.residual_base_pct,
            "residual_max_pct": tipo.residual_max_pct,
            "liquidez_factor": tipo.liquidez_factor,
            "obsolescencia_factor": tipo.obsolescencia_factor,
            "desgaste_km_factor": tipo.desgaste_km_factor,
            "desgaste_hora_factor": tipo.desgaste_hora_factor,
            "haircut_residual_pct": tipo.haircut_residual_pct,
        }
        return run_escenarios_comparados(
            inputs=inp,
            tipo_activo=tipo_d,
            politica=politica,
            plantillas_costo=plantillas,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/simulaciones")
def api_crear_simulacion(
    request: Request,
    body: LOPSimularPreviewBody,
    db: Session = Depends(get_db),
):
    _auth_mutacion(request)
    nombre = str((body.inputs or {}).get("nombre") or "Simulación LOP v2")
    try:
        sim = lo_crud.crear_simulacion_y_calcular(
            db,
            tipo_activo_id=body.tipo_activo_id,
            cliente_id=body.cliente_id,
            nombre=nombre,
            plazo_meses=body.plazo_meses,
            escenario=body.escenario.upper(),
            metodo_pricing=body.metodo_pricing.upper(),
            margen_pct=body.margen_pct if body.metodo_pricing.upper() == "MARGEN_VENTA" else None,
            spread_pct=body.spread_pct if body.metodo_pricing.upper() == "COSTO_SPREAD" else None,
            tir_objetivo=body.tir_objetivo if body.metodo_pricing.upper() == "TIR_OBJETIVO" else None,
            inputs=_build_inputs(body),
            indexacion_tipo=body.indexacion_tipo.upper(),
            indexacion_pct=body.indexacion_pct,
            pie_inicial_pct=body.pie_inicial_pct,
            opcion_compra_pct=body.opcion_compra_pct,
            usuario=str(getattr(request.state, "auth_user", {}).get("email") or "api"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "id": int(sim.id),
        "codigo": sim.codigo,
        "decision": sim.decision_codigo,
        "result": sim.result_json,
        "url": f"/comercial/leasing-operativo/operacion/{sim.id}",
    }
