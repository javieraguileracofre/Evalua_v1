# routes/ui/ventas_pos.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from db.session import get_db
from models import Cliente, NotaVenta, Producto

from services.comercial.ventas_service import crear_venta_pos, anular_venta_pos
from services.finanzas.integracion_ventas import eliminar_movimiento_contable_nota_venta
from crud.comercial import nota_venta as crud_nota_venta
from crud.inventario import inventario as crud_inventario


router = APIRouter(tags=["Ventas POS"])
logger = logging.getLogger("evalua.ventas_pos.ui")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================
# HELPERS
# ============================================================

def _redirect(
    request: Request,
    route_name: str,
    *,
    msg: str | None = None,
    sev: str = "info",
    status_code: int = status.HTTP_303_SEE_OTHER,
    **path_params: Any,
) -> RedirectResponse:
    url = str(request.url_for(route_name, **path_params))
    if msg:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}msg={msg}&sev={sev}"
    return RedirectResponse(url=url, status_code=status_code)


def _parse_date(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} inválida.") from exc


def _parse_items_json(items_json: str) -> list[dict]:
    try:
        items = json.loads(items_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("El detalle de ítems no tiene un formato JSON válido.") from exc

    if not isinstance(items, list) or not items:
        raise ValueError("Debes agregar al menos un producto a la nota de venta.")

    normalized_items: list[dict] = []

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"El ítem #{idx} tiene un formato inválido.")

        producto_id = item.get("producto_id")
        cantidad = item.get("cantidad")
        precio_unitario = item.get("precio_unitario")

        if producto_id in (None, "", 0):
            raise ValueError(f"El ítem #{idx} no tiene producto asociado.")

        if cantidad in (None, "", 0, "0"):
            raise ValueError(f"El ítem #{idx} debe tener una cantidad mayor a 0.")

        if precio_unitario in (None, ""):
            raise ValueError(f"El ítem #{idx} debe tener precio unitario.")

        try:
            normalized_items.append(
                {
                    "producto_id": int(producto_id),
                    "cantidad": float(cantidad),
                    "precio_unitario": float(precio_unitario),
                }
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"El ítem #{idx} contiene valores numéricos inválidos."
            ) from exc

    return normalized_items


# ============================================================
# BÚSQUEDA RÁPIDA POS / SCANNER
# ============================================================

@router.get("/ventas/pos/buscar-producto", name="pos_buscar_producto")
def pos_buscar_producto(
    codigo: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    termino = (codigo or "").strip()
    if not termino:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Debes indicar un código o término de búsqueda."},
        )

    producto = crud_inventario.get_producto_por_codigo_barra(db, termino)
    if not producto:
        producto = crud_inventario.get_producto_por_codigo(db, termino)

    if not producto:
        encontrados = crud_inventario.buscar_producto(db, termino)
        producto = encontrados[0] if encontrados else None

    if not producto:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "message": "Producto no encontrado."},
        )

    if not bool(getattr(producto, "activo", True)):
        return JSONResponse(
            status_code=409,
            content={"ok": False, "message": "El producto está inactivo."},
        )

    return JSONResponse(
        content={
            "ok": True,
            "producto": {
                "id": producto.id,
                "codigo": producto.codigo,
                "codigo_barra": getattr(producto, "codigo_barra", None),
                "nombre": producto.nombre,
                "precio_venta": float(producto.precio_venta or 0),
                "stock_actual": float(producto.stock_actual or 0),
                "controla_stock": bool(getattr(producto, "controla_stock", True)),
                "permite_venta_fraccionada": bool(getattr(producto, "permite_venta_fraccionada", False)),
                "es_servicio": bool(getattr(producto, "es_servicio", False)),
            }
        }
    )


# ============================================================
# FORMULARIO NOTA DE VENTA
# ============================================================

@router.get("/ventas/nota", response_class=HTMLResponse, name="nota_venta_form")
def nota_venta_form(
    request: Request,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    clientes = list(
        db.scalars(
            select(Cliente)
            .where(Cliente.activo.is_(True))
            .order_by(Cliente.razon_social.asc())
        )
    )

    productos = list(
        db.scalars(
            select(Producto)
            .where(Producto.activo.is_(True))
            .order_by(Producto.nombre.asc())
        )
    )

    return templates.TemplateResponse(
        "comercial/nota_venta_form.html",
        {
            "request": request,
            "clientes": clientes,
            "productos": productos,
            "hoy": date.today().isoformat(),
            "msg": msg,
            "sev": sev,
            "active_menu": "ventas",
        },
    )


# ============================================================
# CREAR NOTA DE VENTA
# ============================================================

@router.post("/ventas/nota", name="nota_venta_create")
async def nota_venta_create(
    request: Request,
    db: Session = Depends(get_db),
):
    # No usar Form(...) en la firma: FastAPI valida el cuerpo antes del handler y devuelve 422 JSON
    # si el stream llega vacío (middleware/proxy). Aquí leemos el formulario en el handler.
    try:
        fd = await request.form()
    except Exception:
        logger.exception("Leer formulario crear nota de venta")
        return _redirect(
            request,
            "nota_venta_form",
            msg="No se pudo leer el envío del formulario. Recarga la página (F5) e inténtalo de nuevo.",
            sev="danger",
        )

    def _field_str(name: str) -> str | None:
        v = fd.get(name)
        if v is None:
            return None
        if hasattr(v, "read"):
            return None
        s = str(v).strip()
        return s if s else None

    cliente_raw = _field_str("cliente_id")
    fecha = _field_str("fecha")
    items_json = _field_str("items_json")
    fecha_vencimiento = _field_str("fecha_vencimiento")
    tipo_pago = _field_str("tipo_pago") or "CONTADO"
    afecta_iva = _field_str("afecta_iva") or "true"

    if not cliente_raw or not fecha or not items_json:
        return _redirect(
            request,
            "nota_venta_form",
            msg="Faltan datos obligatorios (cliente, fecha o productos). Recarga (F5) y confirma la venta de nuevo.",
            sev="warning",
        )

    try:
        cliente_id = int(cliente_raw)
    except ValueError:
        return _redirect(
            request,
            "nota_venta_form",
            msg="Cliente no válido.",
            sev="warning",
        )

    try:
        fecha_emision = _parse_date(fecha, "La fecha de emisión")
        if fecha_emision is None:
            raise ValueError("La fecha de emisión es obligatoria.")

        fecha_venc = _parse_date(fecha_vencimiento, "La fecha de vencimiento")
        items = _parse_items_json(items_json)

        nota = crear_venta_pos(
            db=db,
            cliente_id=cliente_id,
            fecha_emision=fecha_emision,
            fecha_vencimiento=fecha_venc,
            tipo_pago=(tipo_pago or "CONTADO").strip().upper(),
            items=items,
            afecta_iva=str(afecta_iva or "").strip().lower() in ("true", "1", "si", "sí", "on"),
            usuario="sistema",
        )

    except ValueError as exc:
        return _redirect(
            request,
            "nota_venta_form",
            msg=public_error_message(exc),
            sev="warning",
        )
    except Exception as exc:
        logger.exception("Crear nota de venta POS")
        return _redirect(
            request,
            "nota_venta_form",
            msg=public_error_message(exc, default="No fue posible crear la nota de venta."),
            sev="danger",
        )

    # CAMINO DORADO:
    # al guardar, abre inmediatamente el ticket térmico
    return _redirect(
        request,
        "nota_venta_ticket",
        nota_id=nota.id,
        msg=f"Nota de venta {nota.numero} creada correctamente.",
        sev="success",
    )


# ============================================================
# LISTADO NOTAS
# ============================================================

@router.get("/ventas/notas", response_class=HTMLResponse, name="nota_venta_lista")
def nota_venta_lista(
    request: Request,
    desde: str | None = Query(None),
    hasta: str | None = Query(None),
    cliente: str | None = Query(None),
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    try:
        d_desde = _parse_date(desde, "La fecha desde")
        d_hasta = _parse_date(hasta, "La fecha hasta")
    except ValueError as exc:
        return templates.TemplateResponse(
            "comercial/nota_venta_lista.html",
            {
                "request": request,
                "notas": [],
                "desde": desde,
                "hasta": hasta,
                "cliente": cliente,
                "msg": public_error_message(exc),
                "sev": "warning",
                "active_menu": "ventas",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    notas: list[NotaVenta] = crud_nota_venta.listar_notas_venta(
        db=db,
        desde=d_desde,
        hasta=d_hasta,
        cliente_busqueda=cliente,
    )

    return templates.TemplateResponse(
        "comercial/nota_venta_lista.html",
        {
            "request": request,
            "notas": notas,
            "desde": desde,
            "hasta": hasta,
            "cliente": cliente,
            "msg": msg,
            "sev": sev,
            "active_menu": "ventas",
        },
    )


# ============================================================
# DETALLE
# ============================================================

@router.get("/ventas/notas/{nota_id}", response_class=HTMLResponse, name="nota_venta_detalle")
def nota_venta_detalle(
    request: Request,
    nota_id: int,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    nota = crud_nota_venta.get_nota_venta(db, nota_id)
    if not nota:
        raise HTTPException(status_code=404, detail="Nota de venta no encontrada.")

    return templates.TemplateResponse(
        "comercial/nota_venta_detalle.html",
        {
            "request": request,
            "nota": nota,
            "msg": msg,
            "sev": sev,
            "active_menu": "ventas",
        },
    )


# ============================================================
# TICKET TÉRMICO 80MM
# ============================================================

@router.get("/ventas/notas/{nota_id}/ticket", response_class=HTMLResponse, name="nota_venta_ticket")
def nota_venta_ticket(
    request: Request,
    nota_id: int,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    auto_print: bool = Query(True),
    volver_a: str | None = Query("detalle"),
    db: Session = Depends(get_db),
):
    nota = crud_nota_venta.get_nota_venta(db, nota_id)
    if not nota:
        raise HTTPException(status_code=404, detail="Nota de venta no encontrada.")

    return templates.TemplateResponse(
        "comercial/ticket_80mm.html",
        {
            "request": request,
            "nota": nota,
            "msg": msg,
            "sev": sev,
            "auto_print": auto_print,
            "volver_a": volver_a or "detalle",
        },
    )


# ============================================================
# ANULAR
# ============================================================

@router.post("/ventas/notas/{nota_id}/anular", name="nota_venta_anular")
def nota_venta_anular(
    request: Request,
    nota_id: int,
    db: Session = Depends(get_db),
):
    nota = crud_nota_venta.get_nota_venta(db, nota_id)
    if not nota:
        raise HTTPException(status_code=404, detail="Nota de venta no encontrada.")

    try:
        anular_venta_pos(db, nota)

    except ValueError as exc:
        return _redirect(
            request,
            "nota_venta_detalle",
            nota_id=nota_id,
            msg=public_error_message(exc),
            sev="warning",
        )
    except Exception as exc:
        logger.exception("Anular nota de venta nota_id=%s", nota_id)
        return _redirect(
            request,
            "nota_venta_detalle",
            nota_id=nota_id,
            msg=public_error_message(exc, default="No fue posible anular la nota de venta."),
            sev="danger",
        )

    return _redirect(
        request,
        "nota_venta_lista",
        msg=f"Nota de venta {nota.numero} anulada correctamente.",
        sev="success",
    )


# ============================================================
# ELIMINAR
# ============================================================

@router.post("/ventas/notas/{nota_id}/eliminar", name="nota_venta_eliminar")
def nota_venta_eliminar(
    request: Request,
    nota_id: int,
    db: Session = Depends(get_db),
):
    nota = crud_nota_venta.get_nota_venta(db, nota_id)
    if not nota:
        raise HTTPException(status_code=404, detail="Nota de venta no encontrada.")

    try:
        eliminar_movimiento_contable_nota_venta(
            db,
            nota_venta_id=nota.id,
        )
        crud_nota_venta.eliminar_nota_venta(db, nota)
    except ValueError as exc:
        return _redirect(
            request,
            "nota_venta_detalle",
            nota_id=nota_id,
            msg=public_error_message(exc),
            sev="warning",
        )
    except Exception as exc:
        logger.exception("Eliminar nota de venta nota_id=%s", nota_id)
        return _redirect(
            request,
            "nota_venta_detalle",
            nota_id=nota_id,
            msg=public_error_message(exc, default="No fue posible eliminar la nota de venta."),
            sev="danger",
        )

    return _redirect(
        request,
        "nota_venta_lista",
        msg="Nota de venta eliminada correctamente.",
        sev="success",
    )