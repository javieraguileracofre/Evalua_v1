# crud/inventario/inventario.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from models import CategoriaProducto, InventarioMovimiento, Producto, UnidadMedida
from schemas.inventario.inventario import (
    CategoriaProductoCreate,
    InventarioAjusteCreate,
    InventarioIngresoStockCreate,
    ProductoCreate,
    ProductoUpdate,
    UnidadMedidaCreate,
)
from services.finanzas.integracion_inventario import contabilizar_ingreso_compra_sin_factura

PRODUCTO_CODIGO_PREFIJO = "PRD"
PRODUCTO_CODIGO_DIGITOS = 6
PRODUCTO_CODIGO_INTENTOS = 5

TIPOS_AJUSTE_VALIDOS = {
    "ENTRADA",
    "SALIDA",
    "AJUSTE_POSITIVO",
    "AJUSTE_NEGATIVO",
    "INVENTARIO_INICIAL",
    "DEVOLUCION_CLIENTE",
    "DEVOLUCION_PROVEEDOR",
    "MERMA",
}

TIPOS_AJUSTE_CONTABILIZABLE_INGRESO = {
    "ENTRADA",
    "AJUSTE_POSITIVO",
    "INVENTARIO_INICIAL",
    "DEVOLUCION_CLIENTE",
}


def _d(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _norm_str(value: str | None) -> str:
    return (value or "").strip()


def _norm_upper(value: str | None) -> str:
    return _norm_str(value).upper()


def _build_producto_codigo(numero: int) -> str:
    return f"{PRODUCTO_CODIGO_PREFIJO}-{numero:0{PRODUCTO_CODIGO_DIGITOS}d}"


def _extraer_numero_codigo_producto(codigo: str) -> int | None:
    codigo = _norm_upper(codigo)
    prefijo = f"{PRODUCTO_CODIGO_PREFIJO}-"

    if not codigo.startswith(prefijo):
        return None

    sufijo = codigo[len(prefijo):]
    if not sufijo.isdigit():
        return None

    return int(sufijo)


def get_siguiente_numero_codigo_producto(db: Session) -> int:
    # Evita duplicados por carrera: bloquea el cálculo en esta transacción.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": "inventario_producto_codigo"},
    )
    return int(
        db.execute(
            text(
                """
                SELECT COALESCE(
                    MAX(
                        CASE
                            WHEN codigo ~ :re_codigo THEN (regexp_match(codigo, :re_codigo))[1]::int
                            ELSE NULL
                        END
                    ),
                    0
                ) + 1
                FROM productos
                WHERE codigo LIKE :pref_like
                """
            ),
            {
                "re_codigo": rf"^{PRODUCTO_CODIGO_PREFIJO}-(\d+)$",
                "pref_like": f"{PRODUCTO_CODIGO_PREFIJO}-%",
            },
        ).scalar_one()
        or 1
    )


def generar_codigo_producto(db: Session) -> str:
    return _build_producto_codigo(get_siguiente_numero_codigo_producto(db))


# ============================================================
# CATEGORÍAS
# ============================================================

def get_categoria(db: Session, categoria_id: int) -> CategoriaProducto | None:
    return db.get(CategoriaProducto, categoria_id)


def get_categoria_por_nombre(db: Session, nombre: str) -> CategoriaProducto | None:
    nombre_norm = _norm_str(nombre)
    if not nombre_norm:
        return None

    stmt = select(CategoriaProducto).where(
        func.lower(CategoriaProducto.nombre) == nombre_norm.lower()
    )
    return db.scalar(stmt)


def listar_categorias(db: Session) -> list[CategoriaProducto]:
    stmt = select(CategoriaProducto).order_by(CategoriaProducto.nombre.asc())
    return list(db.scalars(stmt))


def crear_categoria(db: Session, data: CategoriaProductoCreate) -> CategoriaProducto:
    nombre = _norm_str(data.nombre)
    descripcion = _norm_str(data.descripcion) or None

    if not nombre:
        raise ValueError("El nombre de la categoría es obligatorio.")

    existente = get_categoria_por_nombre(db, nombre)
    if existente:
        raise ValueError(f"Ya existe una categoría con el nombre '{nombre}'.")

    categoria = CategoriaProducto(
        nombre=nombre,
        descripcion=descripcion,
        activo=True,
    )
    db.add(categoria)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Ya existe una categoría con el nombre '{nombre}'.")

    db.refresh(categoria)
    return categoria


# ============================================================
# UNIDADES DE MEDIDA
# ============================================================

def get_unidad_medida(db: Session, unidad_id: int) -> UnidadMedida | None:
    return db.get(UnidadMedida, unidad_id)


def get_unidad_medida_por_codigo(db: Session, codigo: str) -> UnidadMedida | None:
    codigo_norm = _norm_upper(codigo)
    if not codigo_norm:
        return None

    stmt = select(UnidadMedida).where(UnidadMedida.codigo == codigo_norm)
    return db.scalar(stmt)


def listar_unidades_medida(db: Session) -> list[UnidadMedida]:
    stmt = select(UnidadMedida).order_by(UnidadMedida.codigo.asc())
    return list(db.scalars(stmt))


def crear_unidad_medida(db: Session, data: UnidadMedidaCreate) -> UnidadMedida:
    codigo = _norm_upper(data.codigo)
    nombre = _norm_str(data.nombre)
    simbolo = _norm_upper(data.simbolo) if data.simbolo is not None else None

    if not codigo:
        raise ValueError("El código de la unidad de medida es obligatorio.")

    if not nombre:
        raise ValueError("El nombre de la unidad de medida es obligatorio.")

    existente = get_unidad_medida_por_codigo(db, codigo)
    if existente:
        raise ValueError(f"Ya existe una unidad de medida con el código '{codigo}'.")

    unidad = UnidadMedida(
        codigo=codigo,
        nombre=nombre,
        simbolo=simbolo or None,
        activo=True,
    )
    db.add(unidad)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Ya existe una unidad de medida con el código '{codigo}'.")

    db.refresh(unidad)
    return unidad


# ============================================================
# PRODUCTOS
# ============================================================

def get_producto(db: Session, producto_id: int) -> Producto | None:
    stmt = (
        select(Producto)
        .where(Producto.id == producto_id)
        .options(
            selectinload(Producto.categoria),
            selectinload(Producto.unidad_medida),
        )
    )
    return db.scalar(stmt)


def get_producto_por_codigo(db: Session, codigo: str) -> Producto | None:
    codigo_norm = _norm_upper(codigo)
    if not codigo_norm:
        return None

    stmt = select(Producto).where(Producto.codigo == codigo_norm)
    return db.scalar(stmt)


def get_producto_por_codigo_barra(db: Session, codigo_barra: str) -> Producto | None:
    codigo_barra_norm = _norm_str(codigo_barra)
    if not codigo_barra_norm:
        return None

    stmt = select(Producto).where(Producto.codigo_barra == codigo_barra_norm)
    return db.scalar(stmt)


def buscar_producto(db: Session, termino: str) -> list[Producto]:
    termino = _norm_str(termino)
    if not termino:
        return []

    pattern = f"%{termino}%"
    stmt = (
        select(Producto)
        .where(
            or_(
                Producto.nombre.ilike(pattern),
                Producto.codigo.ilike(pattern),
                Producto.codigo_barra.ilike(pattern),
            )
        )
        .order_by(Producto.nombre.asc())
    )
    return list(db.scalars(stmt))


def buscar_producto_por_lector(db: Session, codigo: str) -> Producto | None:
    termino = _norm_str(codigo)
    if not termino:
        return None

    producto = get_producto_por_codigo_barra(db, termino)
    if producto:
        return producto

    producto = get_producto_por_codigo(db, termino)
    if producto:
        return producto

    return None


def listar_productos(
    db: Session,
    *,
    activos_solo: bool = False,
    q: str | None = None,
    skip: int = 0,
    limit: int = 200,
) -> tuple[list[Producto], bool]:
    """
    Lista productos con paginación.

    Devuelve (filas, hay_mas) usando fetch de ``limit + 1`` para detectar página siguiente.
    """
    lim = max(1, min(int(limit), 500))
    sk = max(0, int(skip))
    stmt = (
        select(Producto)
        .options(
            selectinload(Producto.categoria),
            selectinload(Producto.unidad_medida),
        )
    )

    if activos_solo:
        stmt = stmt.where(Producto.activo.is_(True))

    if q and _norm_str(q):
        pattern = f"%{_norm_str(q)}%"
        stmt = stmt.where(
            or_(
                Producto.nombre.ilike(pattern),
                Producto.codigo.ilike(pattern),
                Producto.codigo_barra.ilike(pattern),
            )
        )

    stmt = stmt.order_by(Producto.nombre.asc()).offset(sk).limit(lim + 1)
    rows = list(db.scalars(stmt))
    hay_mas = len(rows) > lim
    return rows[:lim], hay_mas


def crear_producto(db: Session, data: ProductoCreate) -> Producto:
    nombre = _norm_str(data.nombre)
    descripcion = _norm_str(data.descripcion) or None
    codigo_barra = _norm_str(data.codigo_barra) or None

    if not nombre:
        raise ValueError("El nombre del producto es obligatorio.")

    if codigo_barra:
        existente_barra = get_producto_por_codigo_barra(db, codigo_barra)
        if existente_barra:
            raise ValueError(f"Ya existe un producto con el código de barra '{codigo_barra}'.")

    codigo_manual = _norm_upper(data.codigo) if data.codigo else ""
    stock_inicial = _d(data.stock_actual)
    precio_compra = _d(data.precio_compra)

    if stock_inicial < 0:
        raise ValueError("El stock inicial no puede ser negativo.")
    if stock_inicial > 0 and precio_compra <= 0:
        raise ValueError(
            "Para registrar inventario inicial con asiento contable, el precio de compra debe ser mayor a 0."
        )

    def _build_producto(codigo_final: str) -> Producto:
        return Producto(
            codigo=codigo_final,
            codigo_barra=codigo_barra,
            nombre=nombre,
            descripcion=descripcion,
            categoria_id=data.categoria_id,
            unidad_medida_id=data.unidad_medida_id,
            precio_compra=_d(data.precio_compra),
            precio_venta=_d(data.precio_venta),
            stock_minimo=_d(data.stock_minimo),
            # El stock inicial se registra como movimiento para trazabilidad y asiento contable.
            stock_actual=Decimal("0"),
            controla_stock=bool(data.controla_stock),
            permite_venta_fraccionada=bool(data.permite_venta_fraccionada),
            es_servicio=bool(data.es_servicio),
            activo=bool(data.activo),
        )

    if codigo_manual:
        existente = get_producto_por_codigo(db, codigo_manual)
        if existente:
            raise ValueError(f"Ya existe un producto con el código '{codigo_manual}'.")

        producto = _build_producto(codigo_manual)
        db.add(producto)

        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            mensaje = str(getattr(e, "orig", e)).lower()
            if "codigo_barra" in mensaje:
                raise ValueError(f"Ya existe un producto con el código de barra '{codigo_barra}'.")
            raise ValueError(f"Ya existe un producto con el código '{codigo_manual}'.")

        db.refresh(producto)
        if stock_inicial > 0:
            movimiento = registrar_movimiento_inventario(
                db,
                producto=producto,
                tipo_movimiento="INVENTARIO_INICIAL",
                cantidad=stock_inicial,
                costo_unitario=precio_compra,
                referencia_tipo="INVENTARIO_INICIAL",
                referencia_id=producto.id,
                observacion="Inventario inicial al crear producto",
            )
            contabilizar_ingreso_compra_sin_factura(
                db,
                movimiento_id=movimiento.id,
                usuario=None,
            )
        return producto

    for _ in range(PRODUCTO_CODIGO_INTENTOS):
        codigo_auto = generar_codigo_producto(db)

        producto = _build_producto(codigo_auto)
        db.add(producto)

        try:
            db.commit()
            db.refresh(producto)
            if stock_inicial > 0:
                movimiento = registrar_movimiento_inventario(
                    db,
                    producto=producto,
                    tipo_movimiento="INVENTARIO_INICIAL",
                    cantidad=stock_inicial,
                    costo_unitario=precio_compra,
                    referencia_tipo="INVENTARIO_INICIAL",
                    referencia_id=producto.id,
                    observacion="Inventario inicial al crear producto",
                )
                contabilizar_ingreso_compra_sin_factura(
                    db,
                    movimiento_id=movimiento.id,
                    usuario=None,
                )
            return producto
        except IntegrityError as e:
            db.rollback()
            mensaje = str(getattr(e, "orig", e)).lower()
            if "codigo_barra" in mensaje:
                raise ValueError(f"Ya existe un producto con el código de barra '{codigo_barra}'.")
            if "codigo" in mensaje or "ix_productos_codigo" in mensaje:
                continue
            raise ValueError("No fue posible crear el producto por una restricción de base de datos.")

    raise ValueError("No fue posible generar un código único para el producto. Intenta nuevamente.")


def actualizar_producto(db: Session, producto: Producto, data: ProductoUpdate) -> Producto:
    if data.nombre is not None:
        nombre = _norm_str(data.nombre)
        if not nombre:
            raise ValueError("El nombre del producto es obligatorio.")
        producto.nombre = nombre

    if data.descripcion is not None:
        producto.descripcion = _norm_str(data.descripcion) or None

    if data.categoria_id is not None:
        producto.categoria_id = data.categoria_id

    if data.unidad_medida_id is not None:
        producto.unidad_medida_id = data.unidad_medida_id

    if data.codigo_barra is not None:
        codigo_barra = _norm_str(data.codigo_barra) or None
        if codigo_barra:
            existente = get_producto_por_codigo_barra(db, codigo_barra)
            if existente and existente.id != producto.id:
                raise ValueError(f"Ya existe otro producto con el código de barra '{codigo_barra}'.")
        producto.codigo_barra = codigo_barra

    if data.precio_compra is not None:
        producto.precio_compra = _d(data.precio_compra)

    if data.precio_venta is not None:
        producto.precio_venta = _d(data.precio_venta)

    if data.stock_minimo is not None:
        producto.stock_minimo = _d(data.stock_minimo)

    if data.controla_stock is not None:
        producto.controla_stock = data.controla_stock

    if data.permite_venta_fraccionada is not None:
        producto.permite_venta_fraccionada = data.permite_venta_fraccionada

    if data.es_servicio is not None:
        producto.es_servicio = data.es_servicio

    if data.activo is not None:
        producto.activo = data.activo

    producto.fecha_actualizacion = datetime.utcnow()

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        mensaje = str(getattr(e, "orig", e)).lower()
        if "codigo_barra" in mensaje:
            raise ValueError("Ya existe otro producto con ese código de barra.")
        raise ValueError("No fue posible actualizar el producto por una restricción de base de datos.")

    db.refresh(producto)
    return producto


def producto_tiene_movimientos(db: Session, producto_id: int) -> bool:
    total = db.scalar(
        select(func.count())
        .select_from(InventarioMovimiento)
        .where(InventarioMovimiento.producto_id == producto_id)
    )
    return bool(total and total > 0)


def desactivar_producto(db: Session, producto: Producto) -> Producto:
    producto.activo = False
    producto.fecha_actualizacion = datetime.utcnow()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("No fue posible desactivar el producto.")

    db.refresh(producto)
    return producto


def activar_producto(db: Session, producto: Producto) -> Producto:
    producto.activo = True
    producto.fecha_actualizacion = datetime.utcnow()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("No fue posible activar el producto.")

    db.refresh(producto)
    return producto


def eliminar_producto(db: Session, producto: Producto) -> None:
    if producto_tiene_movimientos(db, producto.id):
        raise ValueError("No se puede eliminar: el producto tiene movimientos. Usa 'Desactivar'.")

    db.delete(producto)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("No se puede eliminar: el producto tiene relaciones asociadas. Usa 'Desactivar'.")


# ============================================================
# MOVIMIENTOS / AJUSTES / ENTRADAS
# ============================================================

def registrar_movimiento_inventario(
    db: Session,
    *,
    producto: Producto,
    tipo_movimiento: str,
    cantidad: Decimal,
    costo_unitario: Decimal = Decimal("0.0000"),
    referencia_tipo: str | None = None,
    referencia_id: int | None = None,
    observacion: str | None = None,
) -> InventarioMovimiento:
    tipo_movimiento = _norm_upper(tipo_movimiento)

    if tipo_movimiento not in TIPOS_AJUSTE_VALIDOS and tipo_movimiento not in {"ENTRADA", "SALIDA"}:
        raise ValueError(f"Tipo de movimiento inválido: {tipo_movimiento}")

    cantidad = _d(cantidad)
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a 0.")

    if bool(getattr(producto, "controla_stock", True)):
        stock_actual = _d(producto.stock_actual)

        if tipo_movimiento in {"SALIDA", "AJUSTE_NEGATIVO", "MERMA", "DEVOLUCION_PROVEEDOR"}:
            if stock_actual < cantidad:
                raise ValueError(
                    f"Stock insuficiente para '{producto.nombre}'. "
                    f"Disponible: {stock_actual}, requerido: {cantidad}."
                )
            producto.stock_actual = (stock_actual - cantidad).quantize(Decimal("0.01"))
        else:
            producto.stock_actual = (stock_actual + cantidad).quantize(Decimal("0.01"))

    movimiento = InventarioMovimiento(
        producto_id=producto.id,
        fecha=datetime.utcnow(),
        tipo_movimiento=tipo_movimiento,
        cantidad=cantidad.quantize(Decimal("0.01")),
        costo_unitario=_d(costo_unitario).quantize(Decimal("0.0001")),
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        observacion=_norm_str(observacion) or None,
    )
    db.add(movimiento)

    producto.fecha_actualizacion = datetime.utcnow()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("No fue posible registrar el movimiento de inventario.")

    db.refresh(movimiento)
    return movimiento


def registrar_ajuste_inventario(
    db: Session,
    *,
    data: InventarioAjusteCreate,
    usuario: str | None = None,
) -> InventarioMovimiento:
    producto = get_producto(db, data.producto_id)
    if not producto:
        raise ValueError("Producto no encontrado.")

    tipo_ajuste = _norm_upper(data.tipo_ajuste)
    if tipo_ajuste not in TIPOS_AJUSTE_VALIDOS:
        raise ValueError("Tipo de ajuste no válido.")

    costo_base = _d(data.costo_unitario)
    if tipo_ajuste in TIPOS_AJUSTE_CONTABILIZABLE_INGRESO and costo_base <= 0:
        costo_base = _d(getattr(producto, "precio_compra", 0))

    movimiento = registrar_movimiento_inventario(
        db,
        producto=producto,
        tipo_movimiento=tipo_ajuste,
        cantidad=_d(data.cantidad),
        costo_unitario=costo_base,
        referencia_tipo="AJUSTE_MANUAL",
        referencia_id=producto.id,
        observacion=data.observacion,
    )

    # Ajustes que incrementan inventario: si traen costo unitario, generar asiento.
    if tipo_ajuste in TIPOS_AJUSTE_CONTABILIZABLE_INGRESO:
        if costo_base <= 0:
            raise ValueError(
                "No se generó asiento contable: ingrese costo unitario o configure precio de compra del producto."
            )
        contabilizar_ingreso_compra_sin_factura(
            db,
            movimiento_id=movimiento.id,
            usuario=usuario,
        )

    return movimiento


def ingresar_stock_producto(
    db: Session,
    *,
    data: InventarioIngresoStockCreate,
    usuario: str | None = None,
) -> InventarioMovimiento:
    producto = get_producto(db, data.producto_id)
    if not producto:
        raise ValueError("Producto no encontrado.")

    if not bool(getattr(producto, "activo", True)):
        raise ValueError("No se puede ingresar stock a un producto inactivo.")

    costo_base = _d(data.costo_unitario)
    if costo_base <= 0:
        costo_base = _d(getattr(producto, "precio_compra", 0))

    movimiento = registrar_movimiento_inventario(
        db,
        producto=producto,
        tipo_movimiento="ENTRADA",
        cantidad=_d(data.cantidad),
        costo_unitario=costo_base,
        referencia_tipo="INGRESO_STOCK",
        referencia_id=producto.id,
        observacion=data.observacion or "Ingreso de stock por nueva partida de compra",
    )

    # Camino dorado premium:
    # si hay costo_unitario > 0, se contabiliza como recepción física sin factura
    if costo_base <= 0:
        raise ValueError(
            "No se generó asiento contable: ingrese costo unitario o configure precio de compra del producto."
        )

    contabilizar_ingreso_compra_sin_factura(
        db,
        movimiento_id=movimiento.id,
        usuario=usuario,
    )

    return movimiento


def listar_movimientos_producto(
    db: Session,
    *,
    producto_id: int,
    limit: int = 100,
) -> list[InventarioMovimiento]:
    stmt = (
        select(InventarioMovimiento)
        .where(InventarioMovimiento.producto_id == producto_id)
        .order_by(InventarioMovimiento.fecha.desc(), InventarioMovimiento.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))