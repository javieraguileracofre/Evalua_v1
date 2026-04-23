# models/inventario/inventario.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class CategoriaProducto(Base):
    __tablename__ = "categorias_producto"

    __table_args__ = (
        Index("ix_categorias_producto_nombre", "nombre"),
        Index("ix_categorias_producto_activo", "activo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    productos: Mapped[list["Producto"]] = relationship(
        "Producto",
        back_populates="categoria",
    )


class UnidadMedida(Base):
    __tablename__ = "unidades_medida"

    __table_args__ = (
        Index("ix_unidades_medida_codigo", "codigo"),
        Index("ix_unidades_medida_activo", "activo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    simbolo: Mapped[str | None] = mapped_column(String(20), nullable=True)

    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    productos: Mapped[list["Producto"]] = relationship(
        "Producto",
        back_populates="unidad_medida",
    )


class Producto(Base):
    __tablename__ = "productos"

    __table_args__ = (
        Index("ix_productos_codigo", "codigo"),
        Index("ix_productos_codigo_barra", "codigo_barra"),
        Index("ix_productos_nombre", "nombre"),
        Index("ix_productos_categoria", "categoria_id"),
        Index("ix_productos_activo", "activo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    codigo_barra: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        unique=True,
    )

    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    categoria_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categorias_producto.id", ondelete="SET NULL"),
        nullable=True,
    )

    unidad_medida_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("unidades_medida.id", ondelete="SET NULL"),
        nullable=True,
    )

    precio_compra: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    precio_venta: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    stock_minimo: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    stock_actual: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    controla_stock: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    permite_venta_fraccionada: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    es_servicio: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    categoria: Mapped["CategoriaProducto | None"] = relationship(
        "CategoriaProducto",
        back_populates="productos",
    )

    unidad_medida: Mapped["UnidadMedida | None"] = relationship(
        "UnidadMedida",
        back_populates="productos",
    )

    movimientos: Mapped[list["InventarioMovimiento"]] = relationship(
        "InventarioMovimiento",
        back_populates="producto",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="desc(InventarioMovimiento.fecha)",
    )


class InventarioMovimiento(Base):
    __tablename__ = "inventario_movimientos"

    __table_args__ = (
        Index("ix_inventario_movimientos_producto", "producto_id"),
        Index("ix_inventario_movimientos_fecha", "fecha"),
        Index("ix_inventario_movimientos_tipo", "tipo_movimiento"),
        Index(
            "ix_inventario_movimientos_referencia",
            "referencia_tipo",
            "referencia_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    producto_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("productos.id", ondelete="CASCADE"),
        nullable=False,
    )

    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    tipo_movimiento: Mapped[str] = mapped_column(String(30), nullable=False)

    cantidad: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    costo_unitario: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        default=Decimal("0.0000"),
        server_default="0",
    )

    referencia_tipo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    referencia_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    producto: Mapped["Producto"] = relationship(
        "Producto",
        back_populates="movimientos",
    )