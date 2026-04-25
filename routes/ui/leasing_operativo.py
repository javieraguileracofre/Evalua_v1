# routes/ui/leasing_operativo.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from crud.leasing_operativo import crud as lo_crud
from crud.maestros.cliente import listar_clientes
from db.session import get_db

router = APIRouter(prefix="/comercial/leasing-operativo", tags=["Comercial · Leasing operativo"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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


def _build_inputs_from_form(form: dict[str, str]) -> dict:
    return {
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
    return templates.TemplateResponse(
        "leasing_operativo/listado.html",
        {"request": request, "rows": rows, "active_menu": "leasing_operativo"},
    )


@router.get("/simulador", response_class=HTMLResponse, name="leasing_operativo_simulador")
def lo_simulador_get(request: Request, db: Session = Depends(get_db)):
    tipos = lo_crud.listar_tipos_activo(db)
    clientes, _ = listar_clientes(db, activos_solo=True, limit=400)
    return templates.TemplateResponse(
        "leasing_operativo/simulador.html",
        {"request": request, "tipos": tipos, "clientes": clientes, "active_menu": "leasing_operativo"},
    )


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
    res = sim.result_json or {}
    ctr = getattr(sim, "contrato", None)
    return templates.TemplateResponse(
        "leasing_operativo/operacion_detail.html",
        {"request": request, "sim": sim, "res": res, "contrato": ctr, "active_menu": "leasing_operativo"},
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
