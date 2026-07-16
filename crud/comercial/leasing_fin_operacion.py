# crud/comercial/leasing_fin_operacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion
from models.comercial.leasing_financiero_operacion import (
    LeasingFinancieroActivo,
    LeasingFinancieroAmortizacionLinea,
    LeasingFinancieroChecklistItem,
    LeasingFinancieroFacturaCompra,
    LeasingFinancieroOrdenCompra,
    LeasingFinancieroSolicitudPago,
)
from models.maestros.cliente import Cliente
from services.leasing_financiero import calcular_tabla_amortizacion
from services.leasing_financiero_compra import (
    crear_factura_compra_entidad,
    crear_orden_compra_entidad,
    crear_solicitud_pago,
    resolver_proveedor_id,
)
from services.leasing_financiero_workflow import (
    CHECKLIST_DEFINICION,
    marcar_checklist_item,
)


def inicializar_checklist(db: Session, cotizacion: LeasingFinancieroCotizacion) -> None:
    if getattr(cotizacion, "checklist_items", None):
        return
    if not hasattr(db, "add"):
        return
    for d in CHECKLIST_DEFINICION:
        db.add(
            LeasingFinancieroChecklistItem(
                cotizacion_id=int(cotizacion.id),
                codigo=d["codigo"],
                titulo=d["titulo"],
                es_automatico=bool(d.get("automatico", False)),
                es_bloqueante=bool(d.get("bloqueante", True)),
                orden=int(d.get("orden", 0)),
                estado="PENDIENTE",
            )
        )
    db.flush()


def sincronizar_checklist_automatico(
    db: Session,
    cotizacion: LeasingFinancieroCotizacion,
    *,
    usuario: str = "sistema",
) -> None:
    if not getattr(cotizacion, "checklist_items", None):
        inicializar_checklist(db, cotizacion)
    items = getattr(cotizacion, "checklist_items", None) or []
    if not items:
        return
    cliente = getattr(cotizacion, "cliente", None)
    if cliente is None and hasattr(db, "get"):
        cliente = db.get(Cliente, int(cotizacion.cliente_id))
    if cliente and getattr(cliente, "activo", True) and getattr(cliente, "rut", None):
        marcar_checklist_item(items, "cliente_validado", responsable=usuario)
    if cliente and (getattr(cliente, "direccion", None) or getattr(cliente, "direcciones", None)):
        marcar_checklist_item(items, "direccion_registrada", responsable=usuario)
    activo = getattr(cotizacion, "activo", None)
    if activo and getattr(activo, "descripcion", None):
        marcar_checklist_item(items, "activo_ingresado", responsable=usuario)
    if getattr(cotizacion, "monto_financiado", None) and cotizacion.monto_financiado > 0 and getattr(cotizacion, "plazo", None):
        marcar_checklist_item(items, "cotizacion_calculada", responsable=usuario)
    lineas = getattr(cotizacion, "amortizacion_lineas", None) or []
    if lineas:
        oficiales = [l for l in lineas if getattr(l, "es_oficial", False)]
        if oficiales:
            marcar_checklist_item(items, "amortizacion_generada", responsable=usuario)
    analisis = getattr(cotizacion, "analisis_credito", None)
    if analisis and str(getattr(analisis, "recomendacion", "") or "").upper() in {"APROBADO", "APROBADA_CONDICIONES"}:
        marcar_checklist_item(
            items,
            "credito_aprobado",
            estado="APROBADO",
            aprobado_por=getattr(analisis, "analista", usuario),
            responsable=getattr(analisis, "analista", usuario),
        )
    if getattr(cotizacion, "ordenes_compra", None):
        marcar_checklist_item(items, "orden_compra_generada", responsable=usuario)
    if getattr(cotizacion, "facturas_compra", None):
        marcar_checklist_item(items, "factura_registrada", responsable=usuario)
    if getattr(cotizacion, "asiento_id", None):
        marcar_checklist_item(
            items,
            "aprobacion_contabilizacion",
            estado="APROBADO",
            aprobado_por=usuario,
        )
        marcar_checklist_item(items, "validacion_contable", responsable=usuario)
    solicitudes = getattr(cotizacion, "solicitudes_pago", None) or []
    if solicitudes:
        pagada = any(str(getattr(s, "estado", "")).upper() in {"SOLICITADA", "APROBADA", "PAGADA"} for s in solicitudes)
        if pagada:
            marcar_checklist_item(items, "solicitud_pago", responsable=usuario)
    if hasattr(db, "flush"):
        db.flush()


def upsert_activo(
    db: Session,
    cotizacion: LeasingFinancieroCotizacion,
    *,
    data: dict[str, Any],
) -> LeasingFinancieroActivo:
    activo = getattr(cotizacion, "activo", None)
    neto = data.get("valor_neto") or cotizacion.valor_neto
    iva = data.get("iva_monto")
    total = data.get("valor_total")
    if neto and iva is None and cotizacion.iva_aplica and cotizacion.iva_tasa:
        iva = (Decimal(str(neto)) * Decimal(str(cotizacion.iva_tasa))).quantize(Decimal("0.01"))
    if neto and total is None and iva is not None:
        total = Decimal(str(neto)) + Decimal(str(iva))
    payload = {
        "proveedor_id": data.get("proveedor_id") or cotizacion.proveedor_id,
        "categoria": data.get("categoria") or data.get("bien_tipo") or cotizacion.bien_tipo,
        "marca": data.get("marca"),
        "modelo": data.get("modelo"),
        "descripcion": data.get("descripcion") or data.get("bien_descripcion") or cotizacion.bien_descripcion or "",
        "numero_serie": data.get("numero_serie"),
        "numero_chasis": data.get("numero_chasis"),
        "valor_neto": neto,
        "iva_monto": iva,
        "valor_total": total or neto,
        "estado": data.get("estado") or "COTIZADO",
    }
    if activo:
        for k, v in payload.items():
            if v is not None:
                setattr(activo, k, v)
    else:
        activo = LeasingFinancieroActivo(cotizacion_id=int(cotizacion.id), **{k: v for k, v in payload.items() if v is not None})
        db.add(activo)
    if payload.get("descripcion"):
        cotizacion.bien_descripcion = str(payload["descripcion"])
    if payload.get("categoria"):
        cotizacion.bien_tipo = str(payload["categoria"])
    if payload.get("proveedor_id"):
        cotizacion.proveedor_id = int(payload["proveedor_id"])
    db.flush()
    return activo


def persistir_amortizacion_oficial(
    db: Session,
    cotizacion: LeasingFinancieroCotizacion,
    *,
    usuario: str = "sistema",
    congelar: bool = False,
) -> int:
    tabla = calcular_tabla_amortizacion(cotizacion)
    version = int(cotizacion.escenario_oficial_version or 0) + 1
    for line in list(getattr(cotizacion, "amortizacion_lineas", None) or []):
        if line.es_oficial:
            db.delete(line)
    iva_tasa = Decimal(str(cotizacion.iva_tasa or 0)) if cotizacion.iva_aplica else Decimal("0")
    for row in tabla:
        iva_cuota = None
        if iva_tasa > 0 and not row.es_gracia:
            iva_cuota = (row.cuota * iva_tasa).quantize(Decimal("0.01"))
        db.add(
            LeasingFinancieroAmortizacionLinea(
                cotizacion_id=int(cotizacion.id),
                version_n=version,
                numero_cuota=int(row.numero_cuota),
                fecha_cuota=row.fecha_cuota,
                saldo_inicial=row.saldo_inicial,
                cuota=row.cuota,
                interes=row.interes,
                amortizacion=row.amortizacion,
                saldo_final=row.saldo_final,
                iva_cuota=iva_cuota,
                es_gracia=bool(row.es_gracia),
                es_opcion_compra=bool(row.es_opcion_compra),
                es_oficial=True,
            )
        )
    cotizacion.escenario_oficial_version = version
    if congelar:
        cotizacion.condiciones_congeladas = True
    db.flush()
    sincronizar_checklist_automatico(db, cotizacion, usuario=usuario)
    return version


def registrar_orden_compra(
    db: Session,
    cotizacion: LeasingFinancieroCotizacion,
    *,
    data: dict[str, Any],
    usuario: str,
) -> LeasingFinancieroOrdenCompra:
    proveedor_id = resolver_proveedor_id(
        db,
        proveedor_id=data.get("proveedor_id") or cotizacion.proveedor_id,
        proveedor_nombre=data.get("proveedor_nombre") or cotizacion.concesionario,
    )
    if not proveedor_id:
        raise ValueError("Debe indicar proveedor válido para la orden de compra.")
    neto = Decimal(str(data.get("neto") or cotizacion.valor_neto or getattr(getattr(cotizacion, "activo", None), "valor_neto", None) or 0))
    iva = Decimal(str(data.get("iva") or 0))
    total = Decimal(str(data.get("total") or (neto + iva)))
    oc = crear_orden_compra_entidad(
        db,
        cotizacion=cotizacion,
        proveedor_id=proveedor_id,
        numero=str(data.get("numero") or data.get("numero_documento") or f"OC-LF-{cotizacion.id}"),
        fecha_emision=date.fromisoformat(str(data.get("fecha_emision") or data.get("fecha_documento") or date.today())[:10]),
        neto=neto,
        iva=iva,
        total=total,
        usuario=usuario,
        fecha_entrega_estimada=(
            date.fromisoformat(str(data["fecha_entrega_estimada"])[:10])
            if data.get("fecha_entrega_estimada")
            else None
        ),
        condiciones=data.get("condiciones"),
        estado=str(data.get("estado") or "APROBADA").upper(),
    )
    marcar_checklist_item(cotizacion.checklist_items, "orden_compra_generada", responsable=usuario)
    sincronizar_checklist_automatico(db, cotizacion, usuario=usuario)
    return oc


def registrar_factura_compra(
    db: Session,
    cotizacion: LeasingFinancieroCotizacion,
    *,
    data: dict[str, Any],
    usuario: str,
) -> LeasingFinancieroFacturaCompra:
    proveedor_id = resolver_proveedor_id(
        db,
        proveedor_id=data.get("proveedor_id") or cotizacion.proveedor_id,
        proveedor_nombre=data.get("proveedor_nombre") or cotizacion.concesionario,
    )
    if not proveedor_id:
        raise ValueError("Debe indicar proveedor válido para la factura de compra.")
    neto = Decimal(str(data.get("neto") or 0))
    iva = Decimal(str(data.get("iva") or 0))
    total = Decimal(str(data.get("total") or (neto + iva)))
    if total <= 0:
        raise ValueError("Total de factura debe ser mayor a 0.")
    orden_id = data.get("orden_compra_id")
    if not orden_id and cotizacion.ordenes_compra:
        orden_id = cotizacion.ordenes_compra[-1].id
    factura = crear_factura_compra_entidad(
        db,
        cotizacion=cotizacion,
        proveedor_id=proveedor_id,
        folio=str(data.get("folio") or data.get("nro_factura") or f"F-LF-{cotizacion.id}"),
        fecha_factura=date.fromisoformat(str(data.get("fecha_factura") or date.today())[:10]),
        neto=neto,
        iva=iva,
        total=total,
        usuario=usuario,
        orden_compra_id=int(orden_id) if orden_id else None,
    )
    marcar_checklist_item(cotizacion.checklist_items, "factura_registrada", responsable=usuario)
    marcar_checklist_item(cotizacion.checklist_items, "validacion_contable", responsable=usuario)
    sincronizar_checklist_automatico(db, cotizacion, usuario=usuario)
    return factura


def solicitar_pago_proveedor(
    db: Session,
    cotizacion: LeasingFinancieroCotizacion,
    *,
    factura_id: int | None,
    usuario: str,
    aprobado_por: str | None = None,
) -> LeasingFinancieroSolicitudPago:
    factura = None
    if factura_id:
        factura = db.get(LeasingFinancieroFacturaCompra, int(factura_id))
    elif cotizacion.facturas_compra:
        factura = cotizacion.facturas_compra[-1]
    if not factura:
        raise ValueError("Debe registrar factura de compra antes de solicitar pago.")
    if not factura.ap_documento_id:
        raise ValueError("La factura debe estar contabilizada en CxP antes de solicitar pago.")
    sol = crear_solicitud_pago(db, cotizacion=cotizacion, factura=factura, usuario=usuario)
    if aprobado_por:
        sol.estado = "APROBADA"
        sol.aprobado_por = aprobado_por
        sol.fecha_aprobacion = datetime.utcnow()
    marcar_checklist_item(cotizacion.checklist_items, "solicitud_pago", responsable=usuario, aprobado_por=aprobado_por)
    wf = cotizacion.workflow_json if isinstance(cotizacion.workflow_json, dict) else {}
    hitos = wf.get("hitos") or {}
    hitos["solicitud_pago"] = True
    wf["hitos"] = hitos
    cotizacion.workflow_json = wf
    db.flush()
    return sol


def get_cotizacion_completa(db: Session, cotizacion_id: int) -> LeasingFinancieroCotizacion | None:
    stmt = (
        select(LeasingFinancieroCotizacion)
        .options(
            selectinload(LeasingFinancieroCotizacion.cliente).selectinload(Cliente.direcciones),
            selectinload(LeasingFinancieroCotizacion.proyeccion_lineas),
            selectinload(LeasingFinancieroCotizacion.analisis_credito),
            selectinload(LeasingFinancieroCotizacion.activo),
            selectinload(LeasingFinancieroCotizacion.amortizacion_lineas),
            selectinload(LeasingFinancieroCotizacion.ordenes_compra),
            selectinload(LeasingFinancieroCotizacion.facturas_compra),
            selectinload(LeasingFinancieroCotizacion.solicitudes_pago),
            selectinload(LeasingFinancieroCotizacion.checklist_items),
            selectinload(LeasingFinancieroCotizacion.proveedor),
        )
        .where(LeasingFinancieroCotizacion.id == cotizacion_id)
    )
    return db.scalars(stmt).first()
