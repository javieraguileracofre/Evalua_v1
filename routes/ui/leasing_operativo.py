# routes/ui/leasing_operativo.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime
from io import BytesIO

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from sqlalchemy.orm import Session

from core.rbac import usuario_es_admin
from core.paths import TEMPLATES_DIR
from crud.leasing_operativo import crud as lo_crud
from crud.maestros.cliente import listar_clientes
from db.session import get_db
from services.leasing_operativo.market_data import fetch_cl_market_indicators

router = APIRouter(prefix="/comercial/leasing-operativo", tags=["Comercial · Leasing operativo"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _guard_param_admin(request: Request) -> RedirectResponse | None:
    if usuario_es_admin(getattr(request.state, "auth_user", None)):
        return None
    return RedirectResponse(
        url="/?msg=Solo+jefe+comercial%2Fadmin+puede+modificar+parametros+LOP&sev=danger",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _dec(raw: str | None, default: str = "0") -> Decimal:
    v = str(raw or "").strip()
    if not v:
        return Decimal(default)
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except Exception:
        return Decimal(default)


def _int(raw: str | None, d: int = 0) -> int:
    try:
        return int(str(raw or "").strip())
    except Exception:
        return d


def _date(raw: str | None) -> date:
    v = (raw or "").strip()
    if not v:
        return datetime.utcnow().date()
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return datetime.utcnow().date()


def _num(raw: str | None, default: str = "0") -> float:
    return float(_dec(raw, default))


def _build_inputs_from_form(form: dict[str, str]) -> dict:
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


@router.get("/", name="leasing_operativo_root")
def lo_root():
    return RedirectResponse("/comercial/leasing-operativo/simulaciones", status_code=status.HTTP_302_FOUND)


@router.get("/simulaciones", response_class=HTMLResponse, name="leasing_operativo_list")
def lo_list(request: Request, db: Session = Depends(get_db)):
    rows = lo_crud.listar_simulaciones(db, limit=300)
    resumen = {
        "total": len(rows),
        "cotizado": 0,
        "credito_ok": 0,
        "contrato": 0,
        "activo_contable": 0,
        "aprobadas": 0,
        "rechazadas": 0,
    }
    for r in rows:
        j = r.result_json or {}
        wf = j.get("workflow_v1") if isinstance(j, dict) else {}
        h = wf.get("hitos", {}) if isinstance(wf, dict) else {}
        cred = wf.get("credito", {}) if isinstance(wf, dict) else {}
        if r.estado in {"COTIZADO", "COMITE", "APROBADO", "CONTRATO"}:
            resumen["cotizado"] += 1
        if str(cred.get("dictamen") or "").upper() in {"APROBAR", "OBSERVAR"}:
            resumen["credito_ok"] += 1
        if bool(h.get("contrato_confeccionado")):
            resumen["contrato"] += 1
        if bool(h.get("activacion_contable")):
            resumen["activo_contable"] += 1
        if r.decision_codigo == "APROBAR":
            resumen["aprobadas"] += 1
        if r.decision_codigo == "RECHAZAR":
            resumen["rechazadas"] += 1
    return templates.TemplateResponse(
        "leasing_operativo/listado.html",
        {"request": request, "rows": rows, "resumen": resumen, "active_menu": "leasing_operativo"},
    )


@router.get("/tablero", response_class=HTMLResponse, name="leasing_operativo_tablero")
def lo_tablero(request: Request, db: Session = Depends(get_db)):
    rows = lo_crud.listar_simulaciones(db, limit=400)
    etapas = [
        "COTIZACION",
        "CREDITO_APROBADO",
        "CONTRATO_CONFECCIONADO",
        "ORDEN_COMPRA",
        "ENTREGA_RECEPCION",
        "FACTURA_COMPRA",
        "ACTIVADO_CONTABLE",
    ]
    board: dict[str, list] = {k: [] for k in etapas}
    board["OTROS"] = []
    for r in rows:
        j = r.result_json or {}
        wf = j.get("workflow_v1") if isinstance(j, dict) else {}
        etapa = str((wf or {}).get("etapa_actual") or "COTIZACION").upper()
        if etapa not in board:
            etapa = "OTROS"
        board[etapa].append(r)
    return templates.TemplateResponse(
        "leasing_operativo/tablero.html",
        {
            "request": request,
            "board": board,
            "etapas": etapas + ["OTROS"],
            "active_menu": "leasing_operativo",
        },
    )


@router.get("/simulador", response_class=HTMLResponse, name="leasing_operativo_simulador")
def lo_simulador_get(request: Request, db: Session = Depends(get_db)):
    lo_crud.asegurar_parametros_tipo_default(db)
    tipos = lo_crud.listar_tipos_activo(db)
    params = lo_crud.listar_parametros_tipo(db)
    params_by_tipo = {int(p.tipo_activo_id): p for p in params}
    clientes, _ = listar_clientes(db, activos_solo=True, limit=400)
    mkt = fetch_cl_market_indicators()
    marcas = [
        "Toyota", "Chevrolet", "Hyundai", "Kia", "Mitsubishi", "Volvo", "Scania", "Caterpillar", "Komatsu", "JCB"
    ]
    modelos = [
        "Hilux", "D-Max", "NPR", "FH", "R450", "320D", "WB97", "PC200", "Actros", "Otro"
    ]
    anios = list(range(2010, 2027))
    return templates.TemplateResponse(
        "leasing_operativo/simulador.html",
        {
            "request": request,
            "tipos": tipos,
            "params_by_tipo": params_by_tipo,
            "clientes": clientes,
            "market": mkt,
            "marcas": marcas,
            "modelos": modelos,
            "anios": anios,
            "active_menu": "leasing_operativo",
        },
    )


@router.get("/parametros", response_class=HTMLResponse, name="leasing_operativo_parametros")
def lo_parametros_get(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard_param_admin(request)) is not None:
        return redir
    lo_crud.asegurar_parametros_tipo_default(db)
    tipos = lo_crud.listar_tipos_activo(db)
    rows = lo_crud.listar_parametros_tipo(db)
    by_tipo = {int(r.tipo_activo_id): r for r in rows}
    return templates.TemplateResponse(
        "leasing_operativo/parametros.html",
        {"request": request, "tipos": tipos, "by_tipo": by_tipo, "active_menu": "leasing_operativo"},
    )


@router.post("/parametros/{tipo_id}", name="leasing_operativo_parametros_save")
def lo_parametros_save(
    request: Request,
    tipo_id: int,
    db: Session = Depends(get_db),
    moneda: str = Form("CLP"),
    iva_pct: str = Form("19"),
    plazo_default: str = Form("36"),
    spread_default_pct: str = Form("8"),
    margen_default_pct: str = Form("12"),
    tir_default_pct: str = Form("14"),
    km_anual: str = Form("80000"),
    horas_anual: str = Form("0"),
    marca_modelo_factor: str = Form("1"),
    sector_economico_mult: str = Form("1"),
    inflacion_activo_pct_anual: str = Form("3"),
    condicion_factor: str = Form("1"),
    col_costo_repossession: str = Form("0"),
    col_costo_legal: str = Form("0"),
    col_transporte: str = Form("0"),
    col_reacondicionamiento: str = Form("0"),
    col_descuento_venta_forzada_pct: str = Form("12"),
    col_meses_liquidacion: str = Form("4"),
    col_tasa_fin_liquidacion_mensual: str = Form("0.008"),
    riesgo_segmento_cliente: str = Form("MEDIO"),
    riesgo_sector_mult: str = Form("1"),
    riesgo_activo_mult: str = Form("1"),
    riesgo_uso_intensivo_mult: str = Form("1"),
    riesgo_liquidez_mult: str = Form("1"),
    comision_vendedor: str = Form("0"),
    comision_canal: str = Form("0"),
    costo_adquisicion: str = Form("0"),
    evaluacion: str = Form("0"),
    legal: str = Form("0"),
    onboarding: str = Form("0"),
):
    if (redir := _guard_param_admin(request)) is not None:
        return redir
    perfil = {
        "uso": {"km_anual": _num(km_anual), "horas_anual": _num(horas_anual)},
        "activo": {
            "marca_modelo_factor": _num(marca_modelo_factor, "1"),
            "sector_economico_mult": _num(sector_economico_mult, "1"),
            "inflacion_activo_pct_anual": _num(inflacion_activo_pct_anual, "3"),
            "condicion_factor": _num(condicion_factor, "1"),
        },
        "collateral": {
            "costo_repossession": _num(col_costo_repossession),
            "costo_legal": _num(col_costo_legal),
            "transporte": _num(col_transporte),
            "reacondicionamiento": _num(col_reacondicionamiento),
            "descuento_venta_forzada_pct": _num(col_descuento_venta_forzada_pct, "12"),
            "meses_liquidacion": _int(col_meses_liquidacion, 4),
            "tasa_fin_liquidacion_mensual": _num(col_tasa_fin_liquidacion_mensual, "0.008"),
        },
        "riesgo": {
            "segmento_cliente": (riesgo_segmento_cliente or "MEDIO").upper(),
            "sector_mult": _num(riesgo_sector_mult, "1"),
            "activo_mult": _num(riesgo_activo_mult, "1"),
            "uso_intensivo_mult": _num(riesgo_uso_intensivo_mult, "1"),
            "liquidez_mult": _num(riesgo_liquidez_mult, "1"),
        },
        "comercial": {
            "comision_vendedor": _num(comision_vendedor),
            "comision_canal": _num(comision_canal),
            "costo_adquisicion": _num(costo_adquisicion),
            "evaluacion": _num(evaluacion),
            "legal": _num(legal),
            "onboarding": _num(onboarding),
        },
    }
    lo_crud.upsert_parametro_tipo(
        db,
        tipo_activo_id=tipo_id,
        moneda=(moneda or "CLP").upper(),
        iva_pct=_dec(iva_pct, "19"),
        plazo_default=_int(plazo_default, 36),
        spread_default_pct=_dec(spread_default_pct, "8"),
        margen_default_pct=_dec(margen_default_pct, "12"),
        tir_default_pct=_dec(tir_default_pct, "14"),
        perfil_json=perfil,
    )
    return RedirectResponse(str(request.url_for("leasing_operativo_parametros")), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/simulador", name="leasing_operativo_simulador_post")
def lo_simulador_post(
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    tipo_activo_id: str = Form(...),
    cliente_id: str = Form(""),
    plazo_meses: str = Form("36"),
    escenario: str = Form("BASE"),
    metodo_pricing: str = Form("COSTO_SPREAD"),
    spread_pct: str = Form("8"),
    margen_pct: str = Form("12"),
    tir_objetivo_anual: str = Form("14"),
    moneda: str = Form("CLP"),
    iva_pct: str = Form("19"),
    uf_clp: str = Form("0"),
    usd_clp: str = Form("0"),
    ipc_pct: str = Form("0"),
    market_source: str = Form(""),
    market_as_of: str = Form(""),
    activo_marca: str = Form(""),
    activo_modelo: str = Form(""),
    activo_anio: str = Form(""),
    precio_compra: str = Form("0"),
    importacion: str = Form("0"),
    inscripcion: str = Form("0"),
    patente: str = Form("0"),
    gps_telemetria: str = Form("0"),
    traslado: str = Form("0"),
    acondicionamiento: str = Form("0"),
    puesta_marcha: str = Form("0"),
    comision_proveedor: str = Form("0"),
    otros_activables: str = Form("0"),
    km_anual: str = Form("0"),
    horas_anual: str = Form("0"),
    marca_modelo_factor: str = Form("1"),
    sector_economico_mult: str = Form("1"),
    inflacion_activo_pct_anual: str = Form("0"),
    condicion_factor: str = Form("1"),
    col_valor_mercado: str = Form("0"),
    col_repossession: str = Form("0"),
    col_legal: str = Form("0"),
    col_transporte: str = Form("0"),
    col_reacond: str = Form("0"),
    col_desc_forzada_pct: str = Form("12"),
    col_meses_liq: str = Form("4"),
    col_tasa_fin_m: str = Form("0.008"),
    com_vendedor: str = Form("0"),
    com_canal: str = Form("0"),
    com_adq: str = Form("0"),
    com_eval: str = Form("0"),
    com_legal: str = Form("0"),
    com_onb: str = Form("0"),
    riesgo_segmento: str = Form("MEDIO"),
    riesgo_sector_mult: str = Form("1"),
    riesgo_activo_mult: str = Form("1"),
    riesgo_uso_mult: str = Form("1"),
    riesgo_liq_mult: str = Form("1"),
):
    tid = _int(tipo_activo_id, 0)
    if tid <= 0:
        raise HTTPException(400, "Tipo de activo requerido")
    cid_raw = str(cliente_id or "").strip()
    cid = _int(cid_raw, 0) or None
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
    inputs = _build_inputs_from_form(form)
    inputs["activo"]["marca"] = activo_marca
    inputs["activo"]["modelo"] = activo_modelo
    inputs["activo"]["anio"] = _int(activo_anio, 0)
    try:
        sim = lo_crud.crear_simulacion_y_calcular(
            db,
            tipo_activo_id=tid,
            cliente_id=cid,
            nombre=nombre,
            plazo_meses=_int(plazo_meses, 36),
            escenario=str(escenario).upper()[:24],
            metodo_pricing=str(metodo_pricing).upper()[:24],
            margen_pct=_dec(margen_pct) if str(metodo_pricing).upper() == "MARGEN_VENTA" else None,
            spread_pct=_dec(spread_pct) if str(metodo_pricing).upper() == "COSTO_SPREAD" else None,
            tir_objetivo=_dec(tir_objetivo_anual) if str(metodo_pricing).upper() == "TIR_OBJETIVO" else None,
            inputs=inputs,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(
        str(request.url_for("leasing_operativo_detail", sim_id=int(sim.id))),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/operacion/{sim_id}", response_class=HTMLResponse, name="leasing_operativo_detail")
def lo_detail(request: Request, sim_id: int, db: Session = Depends(get_db)):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404, "Simulación no encontrada")
    try:
        sim = lo_crud.sincronizar_estado_credito(db, sim, usuario="sistema")
    except Exception:
        pass
    res = sim.result_json or {}
    ctr = getattr(sim, "contrato", None)
    workflow = (res.get("workflow_v1") or {}) if isinstance(res, dict) else {}
    return templates.TemplateResponse(
        "leasing_operativo/operacion_detail.html",
        {"request": request, "sim": sim, "res": res, "workflow": workflow, "contrato": ctr, "active_menu": "leasing_operativo"},
    )


@router.get("/operacion/{sim_id}/cotizacion.pdf", name="leasing_operativo_cotizacion_pdf")
def lo_cotizacion_pdf(sim_id: int, db: Session = Depends(get_db)):
    try:
        from services.leasing_operativo.cotizacion_pdf import generar_cotizacion_pdf_bytes
    except ImportError as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Falta dependencia PDF: instale reportlab (requirements.txt).",
        ) from e
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    res = sim.result_json or {}
    cli = sim.cliente
    cli_nombre = None
    if cli is not None:
        cli_nombre = (cli.nombre_fantasia or cli.razon_social or "").strip() or None
    tipo_n = sim.tipo.nombre if sim.tipo else ""
    pdf = generar_cotizacion_pdf_bytes(
        codigo=sim.codigo or str(sim_id),
        nombre=sim.nombre or "",
        tipo_nombre=tipo_n,
        cliente_nombre=cli_nombre,
        sim_meta={
            "escenario": sim.escenario,
            "plazo_meses": sim.plazo_meses,
            "metodo_pricing": sim.metodo_pricing,
            "decision_codigo": sim.decision_codigo,
        },
        result=res,
    )
    fn = f"{sim.codigo or sim_id}_cotizacion_lo.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.post("/operacion/{sim_id}/contrato", name="leasing_operativo_crear_contrato")
def lo_crear_contrato(request: Request, sim_id: int, db: Session = Depends(get_db)):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    try:
        lo_crud.crear_contrato_y_cuotas(db, sim, usuario="sistema")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(
        str(request.url_for("leasing_operativo_detail", sim_id=sim_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/operacion/{sim_id}/credito/derivar", name="leasing_operativo_derivar_credito")
def lo_derivar_credito(
    request: Request,
    sim_id: int,
    db: Session = Depends(get_db),
):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    try:
        _, sol = lo_crud.derivar_a_credito(db, sim, usuario="sistema")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    # abrir ficha de crédito/riesgo para evaluación formal
    return RedirectResponse(
        str(request.url_for("credito_riesgo_solicitud_detalle", solicitud_id=int(sol.id))),
        status_code=303,
    )


@router.post("/operacion/{sim_id}/credito/sync", name="leasing_operativo_sync_credito")
def lo_sync_credito(
    request: Request,
    sim_id: int,
    db: Session = Depends(get_db),
):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    lo_crud.sincronizar_estado_credito(db, sim, usuario="sistema")
    return RedirectResponse(str(request.url_for("leasing_operativo_detail", sim_id=sim_id)), status_code=303)


@router.post("/operacion/{sim_id}/hito", name="leasing_operativo_registrar_hito")
def lo_registrar_hito(
    request: Request,
    sim_id: int,
    db: Session = Depends(get_db),
    hito: str = Form(...),
):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    try:
        lo_crud.registrar_hito_operativo(db, sim, hito=hito, usuario="sistema")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(str(request.url_for("leasing_operativo_detail", sim_id=sim_id)), status_code=303)


@router.get("/operacion/{sim_id}/contrato", response_class=HTMLResponse, name="leasing_operativo_contrato_builder")
def lo_contrato_builder(request: Request, sim_id: int, db: Session = Depends(get_db)):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    drow = lo_crud.obtener_documento_proceso_actual(db, sim_id, "contrato")
    doc = (drow.payload_json if drow else {}) or {}
    return templates.TemplateResponse(
        "leasing_operativo/contrato_builder.html",
        {"request": request, "sim": sim, "doc": doc, "active_menu": "leasing_operativo"},
    )


@router.post("/operacion/{sim_id}/contrato", name="leasing_operativo_contrato_builder_save")
def lo_contrato_builder_save(
    request: Request,
    sim_id: int,
    db: Session = Depends(get_db),
    nro_contrato: str = Form(""),
    fecha_contrato: str = Form(""),
    lugar_firma: str = Form(""),
    observaciones: str = Form(""),
):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    lo_crud.guardar_documento_proceso(
        db,
        sim,
        modulo="contrato",
        data={
            "nro_contrato": nro_contrato,
            "fecha_contrato": fecha_contrato,
            "lugar_firma": lugar_firma,
            "observaciones": observaciones,
        },
        usuario="sistema",
    )
    return RedirectResponse(str(request.url_for("leasing_operativo_detail", sim_id=sim_id)), status_code=303)


@router.get("/operacion/{sim_id}/orden-compra", response_class=HTMLResponse, name="leasing_operativo_oc_builder")
def lo_oc_builder(request: Request, sim_id: int, db: Session = Depends(get_db)):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    drow = lo_crud.obtener_documento_proceso_actual(db, sim_id, "orden_compra")
    doc = (drow.payload_json if drow else {}) or {}
    tipos = lo_crud.listar_tipos_activo(db)
    return templates.TemplateResponse(
        "leasing_operativo/oc_builder.html",
        {"request": request, "sim": sim, "doc": doc, "tipos": tipos, "active_menu": "leasing_operativo"},
    )


@router.post("/operacion/{sim_id}/orden-compra", name="leasing_operativo_oc_builder_save")
def lo_oc_builder_save(
    request: Request,
    sim_id: int,
    db: Session = Depends(get_db),
    proveedor_nombre: str = Form(""),
    oc_numero: str = Form(""),
    fecha_oc: str = Form(""),
    monto_oc: str = Form("0"),
    crear_activo: str = Form(""),
    tipo_activo_id: str = Form(""),
    marca: str = Form(""),
    modelo: str = Form(""),
    anio: str = Form("2024"),
    vin_serie: str = Form(""),
):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    activo_creado = None
    if str(crear_activo).lower() in {"on", "1", "true", "si"}:
        activo_creado = lo_crud.crear_activo_fijo(
            db,
            tipo_activo_id=_int(tipo_activo_id) or None,
            marca=marca,
            modelo=modelo,
            anio=_int(anio, 2024),
            vin_serie=vin_serie,
            fecha_compra=_date(fecha_oc),
            costo_compra=_dec(monto_oc),
            valor_residual_esperado=_dec("0"),
            vida_util_meses_sii=60,
        )
    lo_crud.guardar_documento_proceso(
        db,
        sim,
        modulo="orden_compra",
        data={
            "proveedor_nombre": proveedor_nombre,
            "oc_numero": oc_numero,
            "fecha_oc": fecha_oc,
            "monto_oc": float(_dec(monto_oc)),
            "activo_fijo_id": int(activo_creado.id) if activo_creado else None,
            "activo_fijo_codigo": getattr(activo_creado, "codigo", None),
        },
        usuario="sistema",
    )
    return RedirectResponse(str(request.url_for("leasing_operativo_detail", sim_id=sim_id)), status_code=303)


@router.get("/operacion/{sim_id}/acta-entrega", response_class=HTMLResponse, name="leasing_operativo_acta_builder")
def lo_acta_builder(request: Request, sim_id: int, db: Session = Depends(get_db)):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    drow = lo_crud.obtener_documento_proceso_actual(db, sim_id, "acta_entrega")
    doc = (drow.payload_json if drow else {}) or {}
    return templates.TemplateResponse(
        "leasing_operativo/acta_builder.html",
        {"request": request, "sim": sim, "doc": doc, "active_menu": "leasing_operativo"},
    )


@router.post("/operacion/{sim_id}/acta-entrega", name="leasing_operativo_acta_builder_save")
def lo_acta_builder_save(
    request: Request,
    sim_id: int,
    db: Session = Depends(get_db),
    fecha_entrega: str = Form(""),
    lugar_entrega: str = Form(""),
    km_horas: str = Form(""),
    combustible: str = Form(""),
    checklist_seguridad: str = Form(""),
    observaciones: str = Form(""),
):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    lo_crud.guardar_documento_proceso(
        db,
        sim,
        modulo="acta_entrega",
        data={
            "fecha_entrega": fecha_entrega,
            "lugar_entrega": lugar_entrega,
            "km_horas": km_horas,
            "combustible": combustible,
            "checklist_seguridad": checklist_seguridad,
            "observaciones": observaciones,
        },
        usuario="sistema",
    )
    return RedirectResponse(str(request.url_for("leasing_operativo_detail", sim_id=sim_id)), status_code=303)


@router.get("/operacion/{sim_id}/factura-compra", response_class=HTMLResponse, name="leasing_operativo_factura_builder")
def lo_factura_builder(request: Request, sim_id: int, db: Session = Depends(get_db)):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    drow = lo_crud.obtener_documento_proceso_actual(db, sim_id, "factura_compra")
    doc = (drow.payload_json if drow else {}) or {}
    return templates.TemplateResponse(
        "leasing_operativo/factura_builder.html",
        {"request": request, "sim": sim, "doc": doc, "active_menu": "leasing_operativo"},
    )


@router.post("/operacion/{sim_id}/factura-compra", name="leasing_operativo_factura_builder_save")
def lo_factura_builder_save(
    request: Request,
    sim_id: int,
    db: Session = Depends(get_db),
    nro_factura: str = Form(""),
    fecha_factura: str = Form(""),
    neto: str = Form("0"),
    iva: str = Form("0"),
    total: str = Form("0"),
    asiento_manual_ref: str = Form(""),
):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    lo_crud.guardar_documento_proceso(
        db,
        sim,
        modulo="factura_compra",
        data={
            "nro_factura": nro_factura,
            "fecha_factura": fecha_factura,
            "neto": float(_dec(neto)),
            "iva": float(_dec(iva)),
            "total": float(_dec(total)),
            "asiento_manual_ref": asiento_manual_ref,
        },
        usuario="sistema",
    )
    return RedirectResponse(str(request.url_for("leasing_operativo_detail", sim_id=sim_id)), status_code=303)


@router.get("/cartera", response_class=HTMLResponse, name="leasing_operativo_cartera")
def lo_cartera(request: Request, db: Session = Depends(get_db)):
    items = lo_crud.listar_contratos_cartera(db, limit=400)
    return templates.TemplateResponse(
        "leasing_operativo/cartera.html",
        {"request": request, "items": items, "active_menu": "leasing_operativo"},
    )


@router.get("/cartera/contrato/{cid}", response_class=HTMLResponse, name="leasing_operativo_contrato_detail")
def lo_contrato_detail(request: Request, cid: int, db: Session = Depends(get_db)):
    ctr = lo_crud.obtener_contrato(db, cid)
    if not ctr:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "leasing_operativo/contrato_detail.html",
        {"request": request, "ctr": ctr, "active_menu": "leasing_operativo"},
    )


@router.get("/operacion/{sim_id}/export.xlsx", name="leasing_operativo_export_xlsx")
def lo_export_xlsx(request: Request, sim_id: int, db: Session = Depends(get_db)):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    res = sim.result_json or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "Flujo"
    ws.append(["Mes", "Venta", "Costo fondo", "Deprec.", "Op.", "Riesgo", "Comercial", "Resultado op."])
    for row in res.get("flujo_mensual") or []:
        ws.append(
            [
                row.get("mes"),
                row.get("venta"),
                row.get("costo_fondo"),
                row.get("depreciacion"),
                row.get("costos_operativos"),
                row.get("prima_riesgo"),
                row.get("comercial"),
                row.get("resultado_operacional"),
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fn = f"{sim.codigo or sim_id}_leasing_op.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/comite", response_class=HTMLResponse, name="leasing_operativo_comite_list")
def lo_comite_list(request: Request, db: Session = Depends(get_db)):
    items = lo_crud.listar_comite_pendiente(db)
    return templates.TemplateResponse(
        "leasing_operativo/comite.html",
        {"request": request, "items": items, "modo": "lista", "active_menu": "leasing_operativo"},
    )


@router.get("/comite/{cid}", response_class=HTMLResponse, name="leasing_operativo_comite_detail")
def lo_comite_detail(request: Request, cid: int, db: Session = Depends(get_db)):
    c = lo_crud.obtener_comite(db, cid)
    if not c:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "leasing_operativo/comite.html",
        {"request": request, "items": [], "comite": c, "modo": "detalle", "active_menu": "leasing_operativo"},
    )


@router.post("/comite/{cid}/resolver", name="leasing_operativo_comite_resolver")
def lo_comite_resolver(
    request: Request,
    cid: int,
    db: Session = Depends(get_db),
    decision: str = Form(...),
    comentario: str = Form(""),
):
    c = lo_crud.obtener_comite(db, cid)
    if not c or c.estado != "PENDIENTE":
        raise HTTPException(400, "Comité no disponible")
    d = str(decision).strip().upper()
    if d not in ("APROBAR", "RECHAZAR", "CONDICIONES"):
        raise HTTPException(400, "Decisión inválida")
    lo_crud.resolver_comite(db, c, d, comentario or "", "sistema")
    return RedirectResponse(str(request.url_for("leasing_operativo_comite_list")), status_code=303)


@router.post("/operacion/{sim_id}/comite", name="leasing_operativo_comite_abrir")
def lo_comite_abrir(request: Request, sim_id: int, db: Session = Depends(get_db), resumen: str = Form("")):
    sim = lo_crud.obtener_simulacion(db, sim_id)
    if not sim:
        raise HTTPException(404)
    lo_crud.abrir_comite(db, sim, resumen or "Evaluación comité leasing operativo.")
    return RedirectResponse(str(request.url_for("leasing_operativo_comite_list")), status_code=303)


@router.get("/activos", response_class=HTMLResponse, name="leasing_operativo_activos")
def lo_activos(request: Request, db: Session = Depends(get_db)):
    items = lo_crud.listar_activos_fijos(db, limit=300)
    tipos = lo_crud.listar_tipos_activo(db)
    return templates.TemplateResponse(
        "leasing_operativo/activos.html",
        {"request": request, "items": items, "tipos": tipos, "active_menu": "leasing_operativo"},
    )


@router.post("/activos", name="leasing_operativo_activos_post")
def lo_activos_post(
    request: Request,
    db: Session = Depends(get_db),
    tipo_activo_id: str = Form(""),
    marca: str = Form(""),
    modelo: str = Form(""),
    anio: str = Form("2024"),
    vin_serie: str = Form(""),
    fecha_compra: str = Form(""),
    costo_compra: str = Form("0"),
    valor_residual_esperado: str = Form("0"),
    vida_util_meses_sii: str = Form("60"),
):
    tid = _int(tipo_activo_id, 0) or None
    lo_crud.crear_activo_fijo(
        db,
        tipo_activo_id=tid,
        marca=marca,
        modelo=modelo,
        anio=_int(anio, 2024),
        vin_serie=vin_serie,
        fecha_compra=_date(fecha_compra),
        costo_compra=_dec(costo_compra),
        valor_residual_esperado=_dec(valor_residual_esperado),
        vida_util_meses_sii=_int(vida_util_meses_sii, 60),
    )
    return RedirectResponse(str(request.url_for("leasing_operativo_activos")), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/activos/{aid}", response_class=HTMLResponse, name="leasing_operativo_activo_detail")
def lo_activo_detail(request: Request, aid: int, db: Session = Depends(get_db)):
    a = lo_crud.obtener_activo_fijo(db, aid)
    if not a:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "leasing_operativo/activo_detail.html",
        {"request": request, "a": a, "active_menu": "leasing_operativo"},
    )


@router.post("/activos/{aid}/depreciar", name="leasing_operativo_activo_depreciar")
def lo_activo_depreciar(
    request: Request,
    aid: int,
    db: Session = Depends(get_db),
    periodo_yyyymm: str = Form(...),
    asiento_ref: str = Form(""),
):
    a = lo_crud.obtener_activo_fijo(db, aid)
    if not a:
        raise HTTPException(404)
    try:
        lo_crud.generar_depreciacion_mensual_activo(db, activo=a, periodo_yyyymm=periodo_yyyymm, asiento_ref=asiento_ref)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(
        str(request.url_for("leasing_operativo_activo_detail", aid=aid)),
        status_code=status.HTTP_303_SEE_OTHER,
    )
