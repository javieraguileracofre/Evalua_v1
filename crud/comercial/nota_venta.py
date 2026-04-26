# crud/comercial/nota_venta.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from models import (
    Caja,
    Cliente,
    CuentaPorCobrar,
    InventarioMovimiento,
    MovimientoCaja,
    NotaVenta,
    NotaVentaDetalle,
    PagoCliente,
    Producto,
)


TIPOS_COSTEO_ENTRADA = {
    "ENTRADA",
    "AJUSTE_POSITIVO",
    "INVENTARIO_INICIAL",
    "DEVOLUCION_CLIENTE",
}

TIPOS_COSTEO_SALIDA = {
    "SALIDA",
    "AJUSTE_NEGATIVO",
    "MERMA",
    "DEVOLUCION_PROVEEDOR",
}


def _d(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _utc_now() -> datetime:
    return datetime.utcnow()


def _date_to_datetime(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _producto_controla_stock(producto: Producto) -> bool:
    return bool(getattr(producto, "controla_stock", True)) and not bool(
        getattr(producto, "es_servicio", False)
    )


def _resolver_costo_unitario_promedio(db: Session, producto: Producto) -> Decimal:
    """
    Camino dorado pragmático:
    - calcula un costo promedio operativo desde los movimientos históricos
    - las entradas valorizadas recalculan promedio
    - las salidas descuentan cantidad al costo promedio vigente
    - si no hay historial valorizado, usa precio_compra del producto
    """
    fallback = _d(getattr(producto, "precio_compra", 0)).quantize(Decimal("0.0001"))
    if fallback < 0:
        fallback = Decimal("0.0000")

    stmt = (
        select(InventarioMovimiento)
        .where(InventarioMovimiento.producto_id == producto.id)
        .order_by(InventarioMovimiento.fecha.asc(), InventarioMovimiento.id.asc())
    )
    movimientos = list(db.scalars(stmt))

    if not movimientos:
        return fallback

    stock = Decimal("0")
    costo_promedio = fallback if fallback > 0 else Decimal("0")

    for mov in movimientos:
        tipo = str(getattr(mov, "tipo_movimiento", "") or "").strip().upper()
        cantidad = _d(getattr(mov, "cantidad", 0))
        costo_unitario = _d(getattr(mov, "costo_unitario", 0))

        if cantidad <= 0:
            continue

        if tipo in TIPOS_COSTEO_ENTRADA:
            costo_entrada = costo_unitario if costo_unitario > 0 else costo_promedio
            if costo_entrada <= 0:
                costo_entrada = fallback

            nuevo_stock = stock + cantidad
            if nuevo_stock > 0:
                costo_promedio = (
                    ((stock * costo_promedio) + (cantidad * costo_entrada)) / nuevo_stock
                ).quantize(Decimal("0.0001"))
                stock = nuevo_stock

        elif tipo in TIPOS_COSTEO_SALIDA:
            stock -= cantidad
            if stock < 0:
                stock = Decimal("0")

    if costo_promedio <= 0:
        return fallback

    return costo_promedio.quantize(Decimal("0.0001"))


def get_or_create_caja_principal(db: Session) -> Caja:
    stmt = select(Caja).where(Caja.activa.is_(True)).order_by(Caja.id.asc())
    caja = db.scalar(stmt)
    if caja:
        return caja

    caja = Caja(
        nombre="Caja Principal",
        descripcion="Caja por defecto del sistema",
        saldo_inicial=Decimal("0.00"),
        saldo_actual=Decimal("0.00"),
        fecha_apertura=_utc_now(),
        estado="ABIERTA",
        activa=True,
    )
    db.add(caja)
    db.flush()
    return caja


def generar_numero_nota_venta(db: Session) -> str:
    hoy = date.today().strftime("%Y%m%d")
    prefix = f"NV-{hoy}-"

    stmt = select(func.max(NotaVenta.numero)).where(NotaVenta.numero.like(f"{prefix}%"))
    ultimo = db.scalar(stmt)

    correlativo = 1
    if ultimo:
        try:
            correlativo = int(str(ultimo).split("-")[-1]) + 1
        except Exception:
            correlativo = 1

    return f"{prefix}{correlativo:05d}"


def get_nota_venta(db: Session, nota_id: int) -> NotaVenta | None:
    stmt = (
        select(NotaVenta)
        .where(NotaVenta.id == nota_id)
        .options(
            selectinload(NotaVenta.detalles),
            selectinload(NotaVenta.cliente),
            selectinload(NotaVenta.cuentas_por_cobrar),
        )
    )
    return db.scalar(stmt)


def listar_notas_venta(
    db: Session,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    cliente_busqueda: str | None = None,
) -> list[NotaVenta]:
    stmt = select(NotaVenta).options(selectinload(NotaVenta.cliente))

    if desde:
        stmt = stmt.where(NotaVenta.fecha >= datetime.combine(desde, time.min))

    if hasta:
        stmt = stmt.where(NotaVenta.fecha <= datetime.combine(hasta, time.max))

    if cliente_busqueda:
        pattern = f"%{cliente_busqueda.strip()}%"
        stmt = stmt.join(Cliente).where(
            (Cliente.razon_social.ilike(pattern))
            | (Cliente.rut.ilike(pattern))
        )

    stmt = stmt.order_by(NotaVenta.fecha.desc())
    return list(db.scalars(stmt))


def crear_nota_venta_desde_form(
    db: Session,
    *,
    cliente_id: int,
    fecha_emision: date,
    fecha_vencimiento: date | None,
    tipo_pago: str,
    items: list[dict],
    afecta_iva: bool = True,
    auto_commit: bool = True,
) -> NotaVenta:
    if not items:
        raise ValueError("Debe existir al menos un ítem en la nota de venta.")

    cliente = db.get(Cliente, int(cliente_id))
    if not cliente:
        raise ValueError("Cliente no existe.")

    tipo_pago = (tipo_pago or "").strip().upper()
    if tipo_pago not in {"CONTADO", "CREDITO"}:
        raise ValueError("tipo_pago inválido. Use CONTADO o CREDITO.")

    fecha_venc = fecha_emision if tipo_pago == "CONTADO" else (fecha_vencimiento or fecha_emision)
    if fecha_venc < fecha_emision:
        raise ValueError("La fecha de vencimiento no puede ser anterior a la fecha de emisión.")

    caja = get_or_create_caja_principal(db)
    numero = generar_numero_nota_venta(db)

    subtotal_neto = Decimal("0.00")
    detalles: list[NotaVentaDetalle] = []
    productos_operacion: list[tuple[Producto, Decimal, Decimal, Decimal, bool]] = []

    for item in items:
        producto_id = int(item["producto_id"])
        cantidad = _d(item.get("cantidad"))
        precio_unitario = _d(item.get("precio_unitario"))

        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a 0.")

        if precio_unitario < 0:
            raise ValueError("El precio unitario no puede ser negativo.")

        producto = db.get(Producto, producto_id)
        if not producto:
            raise ValueError(f"Producto ID {producto_id} no existe.")

        if not bool(getattr(producto, "activo", True)):
            raise ValueError(f"El producto '{producto.nombre}' está inactivo.")

        controla_stock = _producto_controla_stock(producto)

        if controla_stock:
            stock_actual = _d(producto.stock_actual)
            if stock_actual < cantidad:
                raise ValueError(
                    f"Stock insuficiente para {producto.nombre}. "
                    f"Disponible: {stock_actual}, requerido: {cantidad}"
                )
            costo_unitario = _resolver_costo_unitario_promedio(db, producto)
        else:
            costo_unitario = Decimal("0.0000")

        subtotal = (cantidad * precio_unitario).quantize(Decimal("0.01"))
        subtotal_neto += subtotal

        detalle = NotaVentaDetalle(
            producto_id=producto.id,
            descripcion=producto.nombre,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            descuento_porcentaje=Decimal("0.00"),
            descuento_monto=Decimal("0.00"),
            subtotal=subtotal,
        )
        detalles.append(detalle)
        productos_operacion.append((producto, cantidad, precio_unitario, costo_unitario, controla_stock))

    descuento_total = Decimal("0.00")
    total_neto = (subtotal_neto - descuento_total).quantize(Decimal("0.01"))

    if afecta_iva:
        total_iva = (total_neto * Decimal("0.19")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    else:
        total_iva = Decimal("0.00")

    total_total = (total_neto + total_iva).quantize(Decimal("0.01"))

    nota = NotaVenta(
        numero=numero,
        fecha=_date_to_datetime(fecha_emision),
        fecha_vencimiento=fecha_venc,
        cliente_id=cliente.id,
        caja_id=caja.id,
        tipo_pago=tipo_pago,
        estado="EMITIDA",
        subtotal_neto=total_neto,
        descuento_total=descuento_total,
        total_neto=total_neto,
        total_iva=total_iva,
        total_total=total_total,
        usuario_emisor="POS",
    )
    db.add(nota)
    db.flush()

    for detalle, (producto, cantidad, _precio_unitario, costo_unitario, controla_stock) in zip(detalles, productos_operacion):
        detalle.nota_venta_id = nota.id
        db.add(detalle)

        if controla_stock:
            mov = InventarioMovimiento(
                producto_id=detalle.producto_id,
                tipo_movimiento="SALIDA",
                fecha=_utc_now(),
                cantidad=detalle.cantidad,
                costo_unitario=costo_unitario.quantize(Decimal("0.0001")),
                referencia_tipo="VENTA",
                referencia_id=nota.id,
                observacion=f"Venta {nota.numero}",
            )
            db.add(mov)

            producto.stock_actual = (_d(producto.stock_actual) - cantidad).quantize(Decimal("0.01"))

    if tipo_pago == "CONTADO":
        mov_caja = MovimientoCaja(
            caja_id=caja.id,
            fecha=_utc_now(),
            tipo_movimiento="VENTA",
            medio_pago="EFECTIVO",
            monto=total_total,
            referencia_tipo="NOTA_VENTA",
            referencia_id=nota.id,
            observacion=f"Venta {nota.numero}",
        )
        db.add(mov_caja)

        caja.saldo_actual = (_d(caja.saldo_actual) + total_total).quantize(Decimal("0.01"))

    cxc_estado = "PAGADA" if tipo_pago == "CONTADO" else "PENDIENTE"
    saldo_pendiente = Decimal("0.00") if tipo_pago == "CONTADO" else total_total

    cxc = CuentaPorCobrar(
        cliente_id=cliente.id,
        nota_venta_id=nota.id,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_venc,
        monto_original=total_total,
        saldo_pendiente=saldo_pendiente,
        estado=cxc_estado,
        observacion=f"Venta {tipo_pago.lower()} {nota.numero}",
    )
    db.add(cxc)
    db.flush()

    if tipo_pago == "CONTADO":
        pago = PagoCliente(
            cuenta_cobrar_id=cxc.id,
            fecha_pago=_date_to_datetime(fecha_emision),
            monto_pago=total_total,
            forma_pago="EFECTIVO",
            caja_id=caja.id,
            referencia=f"Pago en caja {nota.numero}",
            observacion="Pago automático por venta al contado",
        )
        db.add(pago)

    if auto_commit:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError("No fue posible crear la nota de venta por una restricción de base de datos.")
    else:
        db.flush()

    db.refresh(nota)
    return nota


def anular_nota_venta(db: Session, nota: NotaVenta) -> NotaVenta:
    if nota.estado == "ANULADA":
        return nota

    nota_db = get_nota_venta(db, nota.id)
    if not nota_db:
        raise ValueError("La nota de venta no existe.")

    stmt_movs = select(InventarioMovimiento).where(
        InventarioMovimiento.referencia_tipo == "VENTA",
        InventarioMovimiento.referencia_id == nota_db.id,
    )
    movimientos_venta = list(db.scalars(stmt_movs))

    costos_por_producto: dict[int, Decimal] = {}
    for mov in movimientos_venta:
        producto_id = int(mov.producto_id)
        costos_por_producto[producto_id] = _d(getattr(mov, "costo_unitario", 0)).quantize(Decimal("0.0001"))

    for det in nota_db.detalles:
        producto = db.get(Producto, det.producto_id)
        controla_stock = bool(producto) and _producto_controla_stock(producto)

        if controla_stock:
            costo_reversa = costos_por_producto.get(det.producto_id, Decimal("0.0000"))

            mov = InventarioMovimiento(
                producto_id=det.producto_id,
                tipo_movimiento="ENTRADA",
                fecha=_utc_now(),
                cantidad=det.cantidad,
                costo_unitario=costo_reversa,
                referencia_tipo="ANULACION_VENTA",
                referencia_id=nota_db.id,
                observacion=f"Anulación venta {nota_db.numero}",
            )
            db.add(mov)

            producto.stock_actual = (_d(producto.stock_actual) + _d(det.cantidad)).quantize(Decimal("0.01"))

    if nota_db.tipo_pago == "CONTADO" and nota_db.caja_id:
        caja = db.get(Caja, nota_db.caja_id)
        if caja:
            caja.saldo_actual = (_d(caja.saldo_actual) - _d(nota_db.total_total)).quantize(Decimal("0.01"))

            mov_caja = MovimientoCaja(
                caja_id=caja.id,
                fecha=_utc_now(),
                tipo_movimiento="ANULACION_VENTA",
                medio_pago="EFECTIVO",
                monto=_d(nota_db.total_total) * Decimal("-1"),
                referencia_tipo="NOTA_VENTA",
                referencia_id=nota_db.id,
                observacion=f"Reversa venta {nota_db.numero}",
            )
            db.add(mov_caja)

    for cxc in nota_db.cuentas_por_cobrar:
        cxc.estado = "ANULADA"
        cxc.saldo_pendiente = Decimal("0.00")
        observacion_actual = (cxc.observacion or "").strip()
        sufijo = f" | Anulada por reversa de nota {nota_db.numero}"
        cxc.observacion = f"{observacion_actual}{sufijo}" if observacion_actual else f"Anulada por reversa de nota {nota_db.numero}"

    nota_db.estado = "ANULADA"

    db.commit()
    db.refresh(nota_db)
    return nota_db


def eliminar_nota_venta(db: Session, nota: NotaVenta) -> None:
    for det in nota.detalles:
        producto = db.get(Producto, det.producto_id)
        if producto and _producto_controla_stock(producto):
            producto.stock_actual = (_d(producto.stock_actual) + _d(det.cantidad)).quantize(Decimal("0.01"))

    db.query(InventarioMovimiento).filter(
        InventarioMovimiento.referencia_tipo == "VENTA",
        InventarioMovimiento.referencia_id == nota.id,
    ).delete(synchronize_session=False)

    db.query(InventarioMovimiento).filter(
        InventarioMovimiento.referencia_tipo == "ANULACION_VENTA",
        InventarioMovimiento.referencia_id == nota.id,
    ).delete(synchronize_session=False)

    if nota.tipo_pago == "CONTADO":
        caja = db.get(Caja, nota.caja_id) if nota.caja_id else None
        if caja:
            caja.saldo_actual = (_d(caja.saldo_actual) - _d(nota.total_total)).quantize(Decimal("0.01"))

        db.query(MovimientoCaja).filter(
            MovimientoCaja.referencia_tipo == "NOTA_VENTA",
            MovimientoCaja.referencia_id == nota.id,
        ).delete(synchronize_session=False)

    cxcs = db.query(CuentaPorCobrar).filter(
        CuentaPorCobrar.nota_venta_id == nota.id
    ).all()

    for cxc in cxcs:
        db.query(PagoCliente).filter(
            PagoCliente.cuenta_cobrar_id == cxc.id
        ).delete(synchronize_session=False)

    db.query(CuentaPorCobrar).filter(
        CuentaPorCobrar.nota_venta_id == nota.id
    ).delete(synchronize_session=False)

    db.query(NotaVentaDetalle).filter(
        NotaVentaDetalle.nota_venta_id == nota.id
    ).delete(synchronize_session=False)

    db.delete(nota)
    db.commit()