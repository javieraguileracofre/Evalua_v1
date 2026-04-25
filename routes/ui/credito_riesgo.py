# routes/ui/credito_riesgo.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from crud.comercial import credito_riesgo as crud_cr
from crud.maestros.cliente import listar_clientes
from db.session import get_db
from models.comercial.credito_riesgo import CreditoSolicitud

router = APIRouter(prefix="/comercial/credito-riesgo", tags=["Comercial · Crédito y riesgo"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _parse_decimal(raw: str | None, default: str = "0") -> Decimal:
    v = str(raw or "").strip()
    if not v:
        return Decimal(default)
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except Exception:
        return Decimal(default)


def _parse_int(raw: str | None, default: int = 0) -> int:
    try:
        return int(str(raw or "").strip())
    except Exception:
        return default


@router.get("/", name="credito_riesgo_root")
def credito_riesgo_root():
    return RedirectResponse(url="/comercial/credito-riesgo/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard", response_class=HTMLResponse, name="credito_riesgo_dashboard")
def credito_riesgo_dashboard(request: Request, db: Session = Depends(get_db)):
    kpi = crud_cr.dashboard_kpis(db)
    return templates.TemplateResponse(
        "comercial/credito_riesgo/dashboard_riesgo.html",
        {"request": request, "kpi": kpi, "active_menu": "credito_riesgo"},
    )


@router.get("/solicitudes", response_class=HTMLResponse, name="credito_riesgo_solicitudes_list")
def listado_solicitudes(request: Request, db: Session = Depends(get_db)):
    solicitudes = crud_cr.listar_solicitudes(db, limit=300)
    return templates.TemplateResponse(
        "comercial/credito_riesgo/listado_solicitudes_credito.html",
        {"request": request, "solicitudes": solicitudes, "active_menu": "credito_riesgo"},
    )


@router.get("/solicitudes/nueva", response_class=HTMLResponse, name="credito_riesgo_solicitud_nueva_get")
def form_solicitud_get(request: Request, db: Session = Depends(get_db)):
    clientes, _ = listar_clientes(db, activos_solo=True, limit=400)
    return templates.TemplateResponse(
        "comercial/credito_riesgo/form_solicitud_credito.html",
        {"request": request, "clientes": clientes, "active_menu": "credito_riesgo", "sol": None},
    )


@router.post("/solicitudes/nueva", name="credito_riesgo_solicitud_nueva_post")
def form_solicitud_post(
    request: Request,
    db: Session = Depends(get_db),
    cliente_id: str = Form(...),
    tipo_persona: str = Form("NATURAL"),
    producto: str = Form("LEASING_FIN"),
    sector_actividad: str = Form(""),
    moneda: str = Form("CLP"),
    monto_solicitado: str = Form("0"),
    plazo_solicitado: str = Form("12"),
    comercial_lf_cotizacion_id: str = Form(""),
    ingreso_mensual: str = Form("0"),
    gastos_mensual: str = Form("0"),
    deuda_cuotas_mensual: str = Form("0"),
    cuota_propuesta: str = Form("0"),
    tipo_contrato: str = Form(""),
    mora_max_dias_12m: str = Form("0"),
    protestos: str = Form("0"),
    castigos: str = Form("0"),
    reprogramaciones: str = Form("0"),
    ventas_anual: str = Form("0"),
    margen_bruto_pct: str = Form("0"),
    ebitda_anual: str = Form("0"),
    utilidad_neta_anual: str = Form("0"),
    flujo_caja_mensual: str = Form("0"),
    capital_trabajo: str = Form("0"),
    deuda_total: str = Form("0"),
    patrimonio: str = Form("0"),
    liquidez_corriente: str = Form(""),
    antiguedad_meses_natural: str = Form("0"),
    anios_operacion_empresa: str = Form("0"),
    garantia_tipo: str = Form(""),
    garantia_valor_comercial: str = Form("0"),
    garantia_valor_liquidacion: str = Form("0"),
    exposicion_usd_pct: str = Form("0"),
    observaciones: str = Form(""),
):
    cid = _parse_int(cliente_id, 0)
    if cid <= 0:
        raise HTTPException(status_code=400, detail="Cliente requerido")

    cot_id = _parse_int(comercial_lf_cotizacion_id, 0) or None
    liq_raw = str(liquidez_corriente or "").strip()
    liq = _parse_decimal(liq_raw) if liq_raw else None

    sol = CreditoSolicitud(
        cliente_id=cid,
        comercial_lf_cotizacion_id=cot_id,
        tipo_persona="JURIDICA" if str(tipo_persona).upper().startswith("J") else "NATURAL",
        producto=(producto or "LEASING_FIN")[:40],
        sector_actividad=(sector_actividad or "")[:120] or None,
        moneda=(moneda or "CLP")[:10],
        monto_solicitado=_parse_decimal(monto_solicitado),
        plazo_solicitado=max(_parse_int(plazo_solicitado, 12), 1),
        ingreso_mensual=_parse_decimal(ingreso_mensual),
        gastos_mensual=_parse_decimal(gastos_mensual),
        deuda_cuotas_mensual=_parse_decimal(deuda_cuotas_mensual),
        cuota_propuesta=_parse_decimal(cuota_propuesta),
        tipo_contrato=(tipo_contrato or None) or None,
        mora_max_dias_12m=_parse_int(mora_max_dias_12m, 0),
        protestos=_parse_int(protestos, 0),
        castigos=_parse_int(castigos, 0),
        reprogramaciones=_parse_int(reprogramaciones, 0),
        ventas_anual=_parse_decimal(ventas_anual),
        margen_bruto_pct=_parse_decimal(margen_bruto_pct),
        ebitda_anual=_parse_decimal(ebitda_anual),
        utilidad_neta_anual=_parse_decimal(utilidad_neta_anual),
        flujo_caja_mensual=_parse_decimal(flujo_caja_mensual),
        capital_trabajo=_parse_decimal(capital_trabajo),
        deuda_total=_parse_decimal(deuda_total),
        patrimonio=_parse_decimal(patrimonio),
        liquidez_corriente=liq,
        antiguedad_meses_natural=_parse_int(antiguedad_meses_natural, 0),
        anios_operacion_empresa=_parse_int(anios_operacion_empresa, 0),
        garantia_tipo=(garantia_tipo or None) or None,
        garantia_valor_comercial=_parse_decimal(garantia_valor_comercial),
        garantia_valor_liquidacion=_parse_decimal(garantia_valor_liquidacion),
        exposicion_usd_pct=_parse_decimal(exposicion_usd_pct),
        observaciones=observaciones or "",
        estado="BORRADOR",
    )
    crud_cr.crear_solicitud(db, sol)
    return RedirectResponse(
        url=str(request.url_for("credito_riesgo_solicitud_detalle", solicitud_id=int(sol.id))),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/solicitudes/{solicitud_id}", response_class=HTMLResponse, name="credito_riesgo_solicitud_detalle")
def solicitud_detalle(request: Request, solicitud_id: int, db: Session = Depends(get_db)):
    sol = crud_cr.obtener_solicitud(db, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return templates.TemplateResponse(
        "comercial/credito_riesgo/evaluacion_riesgo.html",
        {"request": request, "sol": sol, "active_menu": "credito_riesgo"},
    )


@router.post("/solicitudes/{solicitud_id}/evaluar", name="credito_riesgo_evaluar")
def solicitud_evaluar(request: Request, solicitud_id: int, db: Session = Depends(get_db)):
    sol = crud_cr.obtener_solicitud(db, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    ev = crud_cr.ejecutar_evaluacion(db, sol)
    return RedirectResponse(
        url=str(request.url_for("credito_riesgo_score_detalle", eval_id=int(ev.id))),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/score/{eval_id}", response_class=HTMLResponse, name="credito_riesgo_score_detalle")
def detalle_score(request: Request, eval_id: int, db: Session = Depends(get_db)):
    ev = crud_cr.obtener_evaluacion(db, eval_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")
    return templates.TemplateResponse(
        "comercial/credito_riesgo/detalle_score.html",
        {"request": request, "ev": ev, "sol": ev.solicitud, "active_menu": "credito_riesgo"},
    )


@router.get("/comite", response_class=HTMLResponse, name="credito_riesgo_comite_list")
def comite_list(request: Request, db: Session = Depends(get_db)):
    items = crud_cr.listar_comite_pendientes(db, limit=150)
    return templates.TemplateResponse(
        "comercial/credito_riesgo/comite_credito.html",
        {"request": request, "items": items, "modo": "lista", "active_menu": "credito_riesgo"},
    )


@router.get("/comite/{comite_id}", response_class=HTMLResponse, name="credito_riesgo_comite_detalle")
def comite_detalle(request: Request, comite_id: int, db: Session = Depends(get_db)):
    c = crud_cr.obtener_comite(db, comite_id)
    if not c:
        raise HTTPException(status_code=404, detail="Registro de comité no encontrado")
    return templates.TemplateResponse(
        "comercial/credito_riesgo/comite_credito.html",
        {"request": request, "items": [], "comite": c, "modo": "detalle", "active_menu": "credito_riesgo"},
    )


@router.post("/comite/{comite_id}/resolver", name="credito_riesgo_comite_resolver")
def comite_resolver(
    request: Request,
    comite_id: int,
    db: Session = Depends(get_db),
    decision: str = Form(...),
    comentario: str = Form(""),
):
    c = crud_cr.obtener_comite(db, comite_id)
    if not c or c.estado != "PENDIENTE":
        raise HTTPException(status_code=400, detail="Comité no disponible")
    d = str(decision).strip().upper()
    if d not in ("APROBAR", "RECHAZAR", "CONDICIONES"):
        raise HTTPException(status_code=400, detail="Decisión inválida")
    crud_cr.resolver_comite(db, c, d, comentario or "")
    return RedirectResponse(
        url=str(request.url_for("credito_riesgo_comite_list")),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/solicitudes/{solicitud_id}/comite", name="credito_riesgo_comite_abrir")
def comite_abrir_desde_solicitud(
    request: Request,
    solicitud_id: int,
    db: Session = Depends(get_db),
    resumen: str = Form(""),
):
    sol = crud_cr.obtener_solicitud(db, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    crud_cr.abrir_comite(db, sol, resumen or "Derivado manualmente a comité.")
    return RedirectResponse(
        url=str(request.url_for("credito_riesgo_comite_list")),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/solicitudes/{solicitud_id}/export/excel", name="credito_riesgo_export_excel")
def export_excel_solicitud(request: Request, solicitud_id: int, db: Session = Depends(get_db)):
    sol = crud_cr.obtener_solicitud(db, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    wb = Workbook()
    ws = wb.active
    ws.title = "Ficha"
    rows = [
        ("EvaluaERP — Ficha evaluación crediticia",),
        ("Código", sol.codigo),
        ("Cliente", sol.cliente.razon_social if sol.cliente else ""),
        ("Monto solicitado", float(sol.monto_solicitado)),
        ("Plazo", sol.plazo_solicitado),
        ("Estado", sol.estado),
    ]
    evs_sorted = sorted(sol.evaluaciones or [], key=lambda e: int(e.id), reverse=True)
    for ev in evs_sorted[:5]:
        rows.append((f"Eval #{ev.id} score", float(ev.score_total)))
        rows.append((f"Eval #{ev.id} categoría", ev.categoria))
        rows.append((f"Eval #{ev.id} recomendación", ev.recomendacion))
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"ficha_credito_{sol.codigo or solicitud_id}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/solicitudes/{solicitud_id}/export/pdf", name="credito_riesgo_export_pdf")
def export_pdf_solicitud(request: Request, solicitud_id: int, db: Session = Depends(get_db)):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Exportación PDF requiere el paquete reportlab (pip install reportlab).",
        ) from exc

    sol = crud_cr.obtener_solicitud(db, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    buf = BytesIO()
    cnv = rl_canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 50
    cnv.setFont("Helvetica-Bold", 14)
    cnv.drawString(40, y, "EvaluaERP — Resumen comité / crédito")
    y -= 28
    cnv.setFont("Helvetica", 10)
    cli = sol.cliente.razon_social if sol.cliente else ""
    for line in (
        f"Código: {sol.codigo or solicitud_id}",
        f"Cliente: {cli}",
        f"Monto solicitado: {sol.monto_solicitado} {sol.moneda}",
        f"Plazo: {sol.plazo_solicitado} meses",
        f"Estado workflow: {sol.estado}",
    ):
        cnv.drawString(40, y, line[:100])
        y -= 16
    evs_sorted = sorted(sol.evaluaciones or [], key=lambda e: int(e.id), reverse=True)
    if evs_sorted:
        ev = evs_sorted[0]
        y -= 10
        cnv.drawString(40, y, f"Última evaluación: score {ev.score_total} · {ev.categoria} · {ev.recomendacion}")
        y -= 16
        for chunk in ev.explicacion.split("\n")[:18]:
            cnv.drawString(40, y, chunk[:95])
            y -= 14
            if y < 60:
                cnv.showPage()
                y = h - 50
    cnv.save()
    buf.seek(0)
    fn = f"resumen_credito_{sol.codigo or solicitud_id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/cliente/{cliente_id}/historial", response_class=HTMLResponse, name="credito_riesgo_historial_cliente")
def historial_por_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    evs = crud_cr.listar_evaluaciones_cliente(db, cliente_id, limit=80)
    return templates.TemplateResponse(
        "comercial/credito_riesgo/historial_cliente.html",
        {"request": request, "evaluaciones": evs, "cliente_id": cliente_id, "active_menu": "credito_riesgo"},
    )
