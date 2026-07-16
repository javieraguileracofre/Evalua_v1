# services/leasing_financiero_compra.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from crud.finanzas.cuentas_por_pagar import CuentasPorPagarCRUD
from models.finanzas.compras_finanzas import APDocumento
from schemas.finanzas.cuentas_por_pagar import DocumentoCreate, DocumentoDetalleCreate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion
    from models.comercial.leasing_financiero_operacion import (
        LeasingFinancieroFacturaCompra,
        LeasingFinancieroOrdenCompra,
        LeasingFinancieroSolicitudPago,
    )


def _parse_date_iso(value: object) -> date:
    if isinstance(value, date):
        return value
    s = str(value or "").strip()
    if not s:
        return date.today()
    return date.fromisoformat(s[:10])


def resolver_proveedor_id(
    db: Session,
    *,
    proveedor_id: object,
    proveedor_nombre: object,
) -> int | None:
    if proveedor_id:
        try:
            pid = int(proveedor_id)
            if pid > 0:
                return pid
        except (TypeError, ValueError):
            pass
    nombre = str(proveedor_nombre or "").strip()
    if not nombre:
        return None
    from models.maestros.proveedor import Proveedor

    row = db.scalars(
        select(Proveedor).where(Proveedor.razon_social.ilike(f"%{nombre}%")).limit(1)
    ).first()
    return int(row.id) if row else None


def calcular_diferencias_montos(
    *,
    referencia: Decimal | None,
    neto: Decimal,
    tolerancia_pct: Decimal = Decimal("2"),
) -> Decimal | None:
    if referencia is None or referencia <= 0:
        return None
    diff = neto - referencia
    pct = abs(diff) / referencia * Decimal("100")
    if pct > tolerancia_pct:
        return diff
    return diff


def registrar_factura_compra_ap(
    db: Session,
    cotizacion: LeasingFinancieroCotizacion,
    factura: LeasingFinancieroFacturaCompra,
    *,
    usuario: str,
) -> LeasingFinancieroFacturaCompra:
    if factura.ap_documento_id:
        return factura
    folio = str(factura.folio or f"LF-{cotizacion.id}").strip()
    ap_exist = db.scalars(
        select(APDocumento)
        .where(APDocumento.proveedor_id == int(factura.proveedor_id), APDocumento.folio == folio)
        .order_by(APDocumento.id.desc())
        .limit(1)
    ).first()
    if ap_exist:
        factura.ap_documento_id = int(ap_exist.id)
        factura.estado = "CONTABILIZADA"
        return factura

    neto = Decimal(str(factura.neto or 0))
    iva = Decimal(str(factura.iva or 0))
    fecha = factura.fecha_factura or date.today()
    payload = DocumentoCreate(
        proveedor_id=int(factura.proveedor_id),
        tipo="FACTURA",
        folio=folio,
        fecha_emision=fecha,
        fecha_recepcion=fecha,
        fecha_vencimiento=fecha + timedelta(days=30),
        moneda=str(factura.cotizacion.moneda or "CLP")[:10] if hasattr(factura, "cotizacion") else "CLP",
        tipo_cambio=Decimal("1"),
        es_exento="NO" if iva > 0 else "SI",
        referencia=f"LF {cotizacion.numero_operacion or cotizacion.id}",
        observaciones=f"Compra activo leasing financiero operación {cotizacion.id}",
        detalles=[
            DocumentoDetalleCreate(
                descripcion=f"Compra activo LF #{cotizacion.id}",
                cantidad=Decimal("1"),
                precio_unitario=neto,
                descuento=Decimal("0"),
                categoria_gasto_id=None,
                centro_costo_id=None,
            )
        ],
        impuestos=[],
        tipo_compra_contable="INVENTARIO",
        cuenta_gasto_codigo=None,
        cuenta_proveedores_codigo=None,
        generar_asiento_contable=True,
    )
    ap = CuentasPorPagarCRUD().create_documento(db, payload, user_email=usuario)
    factura.ap_documento_id = int(ap.id)
    factura.estado = "CONTABILIZADA"
    return factura


def crear_solicitud_pago(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    factura: LeasingFinancieroFacturaCompra,
    usuario: str,
) -> LeasingFinancieroSolicitudPago:
    from models.comercial.leasing_financiero_operacion import LeasingFinancieroSolicitudPago

    idem = f"LF-PAY-{cotizacion.id}-{factura.id}"
    existente = db.scalars(
        select(LeasingFinancieroSolicitudPago).where(LeasingFinancieroSolicitudPago.idempotency_key == idem)
    ).first()
    if existente:
        return existente
    sol = LeasingFinancieroSolicitudPago(
        cotizacion_id=int(cotizacion.id),
        factura_compra_id=int(factura.id),
        proveedor_id=int(factura.proveedor_id),
        monto=Decimal(str(factura.total or 0)),
        moneda=str(cotizacion.moneda or "CLP"),
        estado="SOLICITADA",
        idempotency_key=idem,
        usuario=usuario,
    )
    db.add(sol)
    db.flush()
    return sol


def crear_orden_compra_entidad(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    proveedor_id: int,
    numero: str,
    fecha_emision: date,
    neto: Decimal,
    iva: Decimal,
    total: Decimal,
    usuario: str,
    fecha_entrega_estimada: date | None = None,
    condiciones: str | None = None,
    estado: str = "APROBADA",
) -> LeasingFinancieroOrdenCompra:
    from models.comercial.leasing_financiero_operacion import LeasingFinancieroOrdenCompra

    oc = LeasingFinancieroOrdenCompra(
        cotizacion_id=int(cotizacion.id),
        proveedor_id=int(proveedor_id),
        numero=str(numero).strip(),
        fecha_emision=fecha_emision,
        fecha_entrega_estimada=fecha_entrega_estimada,
        neto=neto,
        iva=iva,
        total=total,
        moneda=str(cotizacion.moneda or "CLP"),
        condiciones=condiciones,
        estado=estado,
        usuario=usuario,
    )
    db.add(oc)
    db.flush()
    if cotizacion.activo:
        cotizacion.activo.estado = "OC_EMITIDA"
        cotizacion.activo.proveedor_id = int(proveedor_id)
    return oc


def crear_factura_compra_entidad(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    proveedor_id: int,
    folio: str,
    fecha_factura: date,
    neto: Decimal,
    iva: Decimal,
    total: Decimal,
    usuario: str,
    orden_compra_id: int | None = None,
) -> LeasingFinancieroFacturaCompra:
    from models.comercial.leasing_financiero_operacion import LeasingFinancieroFacturaCompra

    ref_cot = cotizacion.valor_neto or cotizacion.activo.valor_neto if cotizacion.activo else None
    diff_cot = calcular_diferencias_montos(referencia=ref_cot, neto=neto) if ref_cot else None
    diff_oc = None
    if orden_compra_id:
        from models.comercial.leasing_financiero_operacion import LeasingFinancieroOrdenCompra

        oc = db.get(LeasingFinancieroOrdenCompra, orden_compra_id)
        if oc:
            diff_oc = calcular_diferencias_montos(referencia=oc.neto, neto=neto)

    factura = LeasingFinancieroFacturaCompra(
        cotizacion_id=int(cotizacion.id),
        orden_compra_id=orden_compra_id,
        proveedor_id=int(proveedor_id),
        folio=str(folio).strip(),
        fecha_factura=fecha_factura,
        neto=neto,
        iva=iva,
        total=total,
        diferencia_cotizacion=diff_cot,
        diferencia_oc=diff_oc,
        estado="REGISTRADA",
        usuario=usuario,
    )
    db.add(factura)
    db.flush()
    registrar_factura_compra_ap(db, cotizacion, factura, usuario=usuario)
    if cotizacion.activo:
        cotizacion.activo.estado = "FACTURADO"
    return factura
