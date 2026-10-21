# routes/api/lop.py
# -*- coding: utf-8 -*-
"""API JSON leasing operativo v2 (preview, sensibilidad, escenarios)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.rbac import usuario_es_admin, usuario_puede_consultar_modulos_operacion, usuario_puede_mutar_modulos_operacion
from crud.leasing_operativo import crud as lo_crud
from db.session import get_db
from services.leasing_operativo.lop_service import calcular_preview
from services.leasing_operativo.sensitivity import run_escenarios_comparados, run_sensitivity_matrix
from services.leasing_operativo.economic_engine import merge_politica

router = APIRouter(tags=["API · Leasing operativo"])


class LOPSimularPreviewBody(BaseModel):
    tipo_activo_id: int = Field(0, ge=0)
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
    unidades: list[dict[str, Any]] | None = None
    incluir_sensibilidad: bool = False
    incluir_escenarios: bool = False


class LOPResidualEstimateBody(BaseModel):
    plazo_meses: int = Field(36, ge=1, le=120)
    unidades: list[dict[str, Any]] = Field(default_factory=list)


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
    if body.unidades:
        inp["unidades"] = body.unidades
    return inp


@router.post("/simular/preview")
def api_simular_preview(
    request: Request,
    body: LOPSimularPreviewBody,
    db: Session = Depends(get_db),
):
    _auth_consulta(request)
    inp = _build_inputs(body)
    unidades = inp.get("unidades") if isinstance(inp.get("unidades"), list) else []
    tid = int(body.tipo_activo_id or 0)
    if unidades and tid <= 0:
        tid = int((unidades[0] or {}).get("tipo_activo_id") or 0)
    if tid <= 0 and not unidades:
        raise HTTPException(status_code=400, detail="tipo_activo_id o unidades requeridos")
    try:
        payload = calcular_preview(
            db,
            tipo_activo_id=tid or 1,
            cliente_id=body.cliente_id,
            inputs=inp,
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
            incluir_sensibilidad=body.incluir_sensibilidad and not unidades,
            incluir_escenarios=body.incluir_escenarios and not unidades,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return payload


@router.post("/cotizacion/estimar-residual")
def api_estimar_residual(
    request: Request,
    body: LOPResidualEstimateBody,
    db: Session = Depends(get_db),
):
    _auth_consulta(request)
    from services.leasing_operativo.cotizacion_flota import estimar_residuales_flota

    try:
        unidades = estimar_residuales_flota(db, unidades=body.unidades, plazo_meses=body.plazo_meses)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"unidades": unidades, "plazo_meses": body.plazo_meses}


_MARKET_IMG_HOST_SUFFIXES = (
    "chileautos.pxcrush.net",
    "pxcrush.net",
    "acroadtrip.blob.core.windows.net",
    "mlstatic.com",
)


def _market_img_host_ok(host: str) -> bool:
    h = (host or "").lower().strip(".")
    if not h:
        return False
    for suf in _MARKET_IMG_HOST_SUFFIXES:
        if h == suf or h.endswith("." + suf):
            return True
    return False


@router.get("/cotizacion/market-image")
def api_market_image(
    request: Request,
    u: str = Query(..., min_length=12, description="URL https de miniatura del portal"),
):
    """Proxy same-origin de miniaturas de comparables (evita bloqueo CSP img-src)."""
    from urllib.parse import urlparse, unquote

    import httpx
    from fastapi.responses import Response

    _auth_consulta(request)
    raw = unquote(str(u or "").strip())
    if not raw.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL de imagen inválida")
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not _market_img_host_ok(parsed.hostname or ""):
        raise HTTPException(status_code=400, detail="Host de imagen no permitido")
    try:
        with httpx.Client(
            timeout=12.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": "https://www.chileautos.cl/",
            },
        ) as client:
            upstream = client.get(raw)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo obtener la imagen: {exc}") from exc
    if upstream.status_code >= 400:
        raise HTTPException(status_code=404, detail="Imagen no disponible")
    ctype = (upstream.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
    if ctype in {"application/octet-stream", "binary/octet-stream"}:
        ctype = "image/jpeg"
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=400, detail="El recurso no es una imagen")
    return Response(
        content=upstream.content,
        media_type=ctype,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
    inp = _build_inputs(body)
    unidades = inp.get("unidades") if isinstance(inp.get("unidades"), list) else []
    tid = int(body.tipo_activo_id or 0)
    if unidades and tid <= 0:
        tid = int((unidades[0] or {}).get("tipo_activo_id") or 0)
    if tid <= 0:
        raise HTTPException(status_code=400, detail="tipo_activo_id o unidades requeridos")
    nombre = str((body.inputs or {}).get("nombre") or "Cotización leasing operativo")
    try:
        sim = lo_crud.crear_simulacion_y_calcular(
            db,
            tipo_activo_id=tid,
            cliente_id=body.cliente_id,
            nombre=nombre,
            plazo_meses=body.plazo_meses,
            escenario=body.escenario.upper(),
            metodo_pricing=body.metodo_pricing.upper(),
            margen_pct=body.margen_pct if body.metodo_pricing.upper() == "MARGEN_VENTA" else None,
            spread_pct=body.spread_pct if body.metodo_pricing.upper() == "COSTO_SPREAD" else None,
            tir_objetivo=body.tir_objetivo if body.metodo_pricing.upper() == "TIR_OBJETIVO" else None,
            inputs=inp,
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


class ResidualCalculateBody(BaseModel):
    marca: str = ""
    modelo: str = ""
    version: str = ""
    anio: int | None = None
    valor_adquisicion: Decimal = Decimal("0")
    plazo_meses: int = Field(36, ge=1, le=120)
    km_inicial: Decimal = Decimal("0")
    km_anual: Decimal = Decimal("40000")
    km_mensual: Decimal | None = None
    tipo_uso: str = "MIXTO"
    tipo_contrato: str = "ARRENDAMIENTO_OPERATIVO"
    tipo_activo_id: int | None = None
    consultar_mercado: bool = True
    cotizacion_id: int | None = None
    unidad_id: str | None = None
    persist_snapshot: bool = False


class ResidualMarketSearchBody(BaseModel):
    marca: str
    modelo: str
    version: str = ""
    anio: int | None = None
    year_min: int | None = None
    year_max: int | None = None
    km_target: Decimal | None = None
    km_min: int = 0
    km_max: int | None = None


class ResidualOverrideBody(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    cotizacion_id: int | None = None
    unidad_id: str = ""
    valor_anterior: Decimal
    valor_nuevo: Decimal
    motivo: str = Field(..., min_length=3, max_length=200)
    observacion: str = ""
    model_version: str = ""


@router.post("/residual-value/calculate")
def api_residual_calculate(
    request: Request,
    body: ResidualCalculateBody,
    db: Session = Depends(get_db),
):
    _auth_consulta(request)
    from services.leasing_operativo.economic_engine import merge_politica
    from services.leasing_operativo.residual_value_service import (
        build_profitability_report,
        calculate_residual_engine,
        persist_valuation_snapshot,
    )

    politica = merge_politica(lo_crud.listar_politica(db))
    tipo = lo_crud.obtener_tipo(db, int(body.tipo_activo_id)) if body.tipo_activo_id else None
    try:
        est = calculate_residual_engine(
            marca=body.marca,
            modelo=body.modelo,
            version=body.version,
            anio=body.anio,
            valor_adquisicion=body.valor_adquisicion,
            plazo_meses=body.plazo_meses,
            km_inicial=body.km_inicial,
            km_anual=body.km_anual,
            km_mensual=body.km_mensual,
            tipo_uso=body.tipo_uso,
            tipo_contrato=body.tipo_contrato,
            politica=politica,
            consultar_mercado=body.consultar_mercado,
            haircut_tipo_pct=getattr(tipo, "haircut_residual_pct", 5) if tipo else 5,
            liquidez_factor=getattr(tipo, "liquidez_factor", 1) if tipo else 1,
            obsolescencia_factor=getattr(tipo, "obsolescencia_factor", 1) if tipo else 1,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    snap_id = None
    if body.persist_snapshot:
        row = persist_valuation_snapshot(
            db,
            cotizacion_id=body.cotizacion_id,
            unidad_id=body.unidad_id,
            payload=est,
            usuario=str(getattr(getattr(request.state, "auth_user", None), "email", None) or "api"),
        )
        if row is not None:
            try:
                db.commit()
                snap_id = int(row.id)
            except Exception:
                db.rollback()
    return {
        "estimacion": est,
        "escenarios": est.get("escenarios"),
        "profitability_report": build_profitability_report(est),
        "snapshot_id": snap_id,
        "model_version": est.get("model_version"),
    }


@router.post("/residual-value/market-search")
def api_residual_market_search(
    request: Request,
    body: ResidualMarketSearchBody,
    db: Session = Depends(get_db),
):
    _auth_consulta(request)
    from services.leasing_operativo.economic_engine import merge_politica
    from services.leasing_operativo.market_data.valuation import search_and_value

    politica = merge_politica(lo_crud.listar_politica(db))
    weights = (politica.get("residual_value_v1") or {}).get("market_data_weights")
    result = search_and_value(
        brand=body.marca,
        model=body.modelo,
        version=body.version,
        year=body.anio,
        year_min=body.year_min,
        year_max=body.year_max,
        km_target=float(body.km_target) if body.km_target is not None else None,
        km_min=body.km_min,
        km_max=body.km_max,
        source_weights=weights,
    )
    return result


@router.get("/residual-value/{cotizacion_id}")
def api_residual_get(request: Request, cotizacion_id: int, db: Session = Depends(get_db)):
    _auth_consulta(request)
    sim = lo_crud.obtener_simulacion(db, cotizacion_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    inputs = sim.inputs_json or {}
    unidades = inputs.get("unidades") if isinstance(inputs.get("unidades"), list) else []
    analisis = []
    for u in unidades:
        if isinstance(u, dict) and u.get("residual_estimacion"):
            analisis.append(
                {
                    "unidad_id": u.get("id"),
                    "descripcion": u.get("descripcion"),
                    "residual_estimacion": u.get("residual_estimacion"),
                    "analisis_residual": u.get("analisis_residual"),
                }
            )
    return {
        "cotizacion_id": cotizacion_id,
        "codigo": sim.codigo,
        "result": sim.result_json,
        "unidades_residual": analisis,
    }


@router.get("/residual-value/{cotizacion_id}/comparables")
def api_residual_comparables(request: Request, cotizacion_id: int, db: Session = Depends(get_db)):
    _auth_consulta(request)
    sim = lo_crud.obtener_simulacion(db, cotizacion_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    out = []
    for u in (sim.inputs_json or {}).get("unidades") or []:
        if not isinstance(u, dict):
            continue
        est = u.get("residual_estimacion") or {}
        out.append(
            {
                "unidad_id": u.get("id"),
                "comparables": est.get("comparables") or [],
                "search_urls": est.get("search_urls") or {},
                "portales": est.get("portales") or [],
            }
        )
    return {"cotizacion_id": cotizacion_id, "items": out}


@router.get("/residual-value/{cotizacion_id}/scenarios")
def api_residual_scenarios(request: Request, cotizacion_id: int, db: Session = Depends(get_db)):
    _auth_consulta(request)
    sim = lo_crud.obtener_simulacion(db, cotizacion_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    items = []
    for u in (sim.inputs_json or {}).get("unidades") or []:
        if not isinstance(u, dict):
            continue
        est = u.get("residual_estimacion") or {}
        items.append({"unidad_id": u.get("id"), "escenarios": est.get("escenarios") or {}})
    return {"cotizacion_id": cotizacion_id, "items": items}


@router.get("/residual-value/{cotizacion_id}/profitability")
def api_residual_profitability(request: Request, cotizacion_id: int, db: Session = Depends(get_db)):
    _auth_consulta(request)
    from services.leasing_operativo.residual_value_service import build_profitability_report

    sim = lo_crud.obtener_simulacion(db, cotizacion_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    rent = sim.result_json or {}
    reports = []
    for u in (sim.inputs_json or {}).get("unidades") or []:
        if not isinstance(u, dict):
            continue
        est = u.get("residual_estimacion") or {}
        if est:
            reports.append(build_profitability_report(est, rentabilidad=rent))
    return {
        "cotizacion_id": cotizacion_id,
        "tir_anual_pct": rent.get("tir_anual_pct"),
        "van": rent.get("van"),
        "margen_operacional_promedio_pct": rent.get("margen_operacional_promedio_pct"),
        "decision": rent.get("decision"),
        "reports": reports,
    }


@router.post("/residual-value/override")
def api_residual_override(
    request: Request,
    body: ResidualOverrideBody,
    db: Session = Depends(get_db),
):
    """Registra override manual obligatorio (usuario, valores, motivo)."""
    _auth_mutacion(request)
    from models.leasing_operativo.models import LeasingOpResidualOverride

    user = getattr(request.state, "auth_user", None)
    email = str(getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None) or "api")
    row = LeasingOpResidualOverride(
        cotizacion_id=body.cotizacion_id,
        unidad_id=body.unidad_id or "",
        valor_anterior=body.valor_anterior,
        valor_nuevo=body.valor_nuevo,
        motivo=body.motivo.strip(),
        observacion=(body.observacion or "").strip(),
        model_version=body.model_version or "",
        usuario=email,
    )
    db.add(row)
    if body.cotizacion_id:
        from models.leasing_operativo.models import LeasingOpHistorial

        db.add(
            LeasingOpHistorial(
                simulacion_id=int(body.cotizacion_id),
                evento="RESIDUAL_OVERRIDE",
                detalle_json={
                    "unidad_id": body.unidad_id,
                    "valor_anterior": float(body.valor_anterior),
                    "valor_nuevo": float(body.valor_nuevo),
                    "motivo": body.motivo,
                    "observacion": body.observacion,
                },
                usuario=email,
            )
        )
    try:
        db.commit()
        db.refresh(row)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"No se pudo registrar override: {exc}") from exc
    return {
        "id": int(row.id),
        "MANUAL_OVERRIDE": True,
        "advertencia": "El valor residual fue modificado manualmente respecto del modelo de mercado.",
    }
