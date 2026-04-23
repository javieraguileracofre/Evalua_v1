# models_autogen.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, BigInteger, SmallInteger, Numeric, String, Text, Time
from sqlalchemy.dialects.postgresql import UUID, JSON, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from db.base_class import Base


class FinAdjunto(Base):
    __tablename__ = "adjunto"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.adjunto_id_seq'::regclass)
    entidad: Mapped[String(40)] = mapped_column(String(40), nullable=False)
    entidad_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    nombre: Mapped[String(220)] = mapped_column(String(220), nullable=False)
    mime: Mapped[String(120)] = mapped_column(String(120), nullable=True)
    storage_path: Mapped[String(500)] = mapped_column(String(500), nullable=False)
    hash_sha256: Mapped[String(80)] = mapped_column(String(80), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinApDocumento(Base):
    __tablename__ = "ap_documento"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.ap_documento_id_seq'::regclass)
    uuid: Mapped[UUID(as_uuid=True)] = mapped_column(UUID(as_uuid=True), nullable=False)  # default=gen_random_uuid()
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[String  # USER-DEFINED::ap_doc_tipo] = mapped_column(String  # USER-DEFINED::ap_doc_tipo, nullable=False)
    estado: Mapped[String  # USER-DEFINED::ap_doc_estado] = mapped_column(String  # USER-DEFINED::ap_doc_estado, nullable=False)  # default='BORRADOR'::fin.ap_doc_estado
    folio: Mapped[String(40)] = mapped_column(String(40), nullable=False)
    fecha_emision: Mapped[Date] = mapped_column(Date, nullable=False)
    fecha_recepcion: Mapped[Date] = mapped_column(Date, nullable=True)
    fecha_vencimiento: Mapped[Date] = mapped_column(Date, nullable=False)
    moneda: Mapped[String  # USER-DEFINED::moneda_iso] = mapped_column(String  # USER-DEFINED::moneda_iso, nullable=False)  # default='CLP'::fin.moneda_iso
    tipo_cambio: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=1
    neto: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    exento: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    iva: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    otros_impuestos: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    total: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    saldo_pendiente: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    referencia: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    observaciones: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinApDocumentoDetalle(Base):
    __tablename__ = "ap_documento_detalle"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.ap_documento_detalle_id_seq'::regclass)
    documento_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    linea: Mapped[Integer] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[String(260)] = mapped_column(String(260), nullable=False)
    cantidad: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=1
    precio_unitario: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=0
    descuento: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    neto_linea: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    iva_linea: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    otros_impuestos: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    total_linea: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    categoria_gasto_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    centro_costo_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinApDocumentoImpuesto(Base):
    __tablename__ = "ap_documento_impuesto"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.ap_documento_impuesto_id_seq'::regclass)
    documento_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[String  # USER-DEFINED::impuesto_tipo] = mapped_column(String  # USER-DEFINED::impuesto_tipo, nullable=False)  # default='OTRO'::fin.impuesto_tipo
    codigo: Mapped[String(40)] = mapped_column(String(40), nullable=True)
    nombre: Mapped[String(120)] = mapped_column(String(120), nullable=True)
    monto: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinApPago(Base):
    __tablename__ = "ap_pago"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.ap_pago_id_seq'::regclass)
    uuid: Mapped[UUID(as_uuid=True)] = mapped_column(UUID(as_uuid=True), nullable=False)  # default=gen_random_uuid()
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    estado: Mapped[String  # USER-DEFINED::ap_pago_estado] = mapped_column(String  # USER-DEFINED::ap_pago_estado, nullable=False)  # default='BORRADOR'::fin.ap_pago_estado
    fecha_pago: Mapped[Date] = mapped_column(Date, nullable=False)
    medio_pago: Mapped[String  # USER-DEFINED::medio_pago] = mapped_column(String  # USER-DEFINED::medio_pago, nullable=False)  # default='TRANSFERENCIA'::fin.medio_pago
    referencia: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    banco_proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    moneda: Mapped[String  # USER-DEFINED::moneda_iso] = mapped_column(String  # USER-DEFINED::moneda_iso, nullable=False)  # default='CLP'::fin.moneda_iso
    tipo_cambio: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=1
    monto_total: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    observaciones: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinApPagoAplicacion(Base):
    __tablename__ = "ap_pago_aplicacion"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.ap_pago_aplicacion_id_seq'::regclass)
    pago_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    documento_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    monto_aplicado: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinCategoriaGasto(Base):
    __tablename__ = "categoria_gasto"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.categoria_gasto_id_seq'::regclass)
    codigo: Mapped[String(30)] = mapped_column(String(30), nullable=False)
    nombre: Mapped[String(160)] = mapped_column(String(160), nullable=False)
    tipo: Mapped[String  # USER-DEFINED::tipo_gasto] = mapped_column(String  # USER-DEFINED::tipo_gasto, nullable=False)  # default='OPERACIONAL'::fin.tipo_gasto
    estado: Mapped[String  # USER-DEFINED::estado_activo] = mapped_column(String  # USER-DEFINED::estado_activo, nullable=False)  # default='ACTIVO'::fin.estado_activo
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinCentroCosto(Base):
    __tablename__ = "centro_costo"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.centro_costo_id_seq'::regclass)
    codigo: Mapped[String(30)] = mapped_column(String(30), nullable=False)
    nombre: Mapped[String(120)] = mapped_column(String(120), nullable=False)
    estado: Mapped[String  # USER-DEFINED::estado_activo] = mapped_column(String  # USER-DEFINED::estado_activo, nullable=False)  # default='ACTIVO'::fin.estado_activo
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinConfigContable(Base):
    __tablename__ = "config_contable"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.config_contable_id_seq'::regclass)
    codigo_evento: Mapped[String(50)] = mapped_column(String(50), nullable=False)
    nombre_evento: Mapped[String(150)] = mapped_column(String(150), nullable=False)
    lado: Mapped[String(10)] = mapped_column(String(10), nullable=False)
    codigo_cuenta: Mapped[String(30)] = mapped_column(String(30), ForeignKey("fin.plan_cuenta.codigo"), nullable=False)
    orden: Mapped[Integer] = mapped_column(Integer, nullable=False)  # default=1
    requiere_centro_costo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    requiere_documento: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    estado: Mapped[String(20)] = mapped_column(String(20), nullable=False)  # default='ACTIVO'::character varying
    descripcion: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinConfigContableDetalleModulo(Base):
    __tablename__ = "config_contable_detalle_modulo"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.config_contable_detalle_modulo_id_seq'::regclass)
    modulo: Mapped[String(50)] = mapped_column(String(50), nullable=False)
    submodulo: Mapped[String(50)] = mapped_column(String(50), nullable=True)
    tipo_documento: Mapped[String(50)] = mapped_column(String(50), nullable=True)
    codigo_evento: Mapped[String(50)] = mapped_column(String(50), nullable=False)
    nombre_evento: Mapped[String(150)] = mapped_column(String(150), nullable=False)
    lado: Mapped[String(10)] = mapped_column(String(10), nullable=False)
    codigo_cuenta: Mapped[String(30)] = mapped_column(String(30), ForeignKey("fin.plan_cuenta.codigo"), nullable=False)
    orden: Mapped[Integer] = mapped_column(Integer, nullable=False)  # default=1
    requiere_centro_costo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    requiere_documento: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    requiere_cliente: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    requiere_proveedor: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    estado: Mapped[String(20)] = mapped_column(String(20), nullable=False)  # default='ACTIVO'::character varying
    descripcion: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinEvento(Base):
    __tablename__ = "evento"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.evento_id_seq'::regclass)
    entidad: Mapped[String(40)] = mapped_column(String(40), nullable=False)
    entidad_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    evento: Mapped[String(80)] = mapped_column(String(80), nullable=False)
    detalle: Mapped[Text] = mapped_column(Text, nullable=True)
    user_email: Mapped[String  # USER-DEFINED::citext] = mapped_column(String  # USER-DEFINED::citext, nullable=True)
    ip_origen: Mapped[String(80)] = mapped_column(String(80), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinPeriodo(Base):
    __tablename__ = "periodo"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.periodo_id_seq'::regclass)
    anio: Mapped[Integer] = mapped_column(Integer, nullable=False)
    mes: Mapped[Integer] = mapped_column(Integer, nullable=False)
    estado: Mapped[String  # USER-DEFINED::periodo_estado] = mapped_column(String  # USER-DEFINED::periodo_estado, nullable=False)  # default='ABIERTO'::fin.periodo_estado
    cerrado_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    cerrado_por: Mapped[String  # USER-DEFINED::citext] = mapped_column(String  # USER-DEFINED::citext, nullable=True)
    notas: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinPlanCuenta(Base):
    __tablename__ = "plan_cuenta"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.plan_cuenta_id_seq'::regclass)
    codigo: Mapped[String(30)] = mapped_column(String(30), nullable=False)
    nombre: Mapped[String(180)] = mapped_column(String(180), nullable=False)
    nivel: Mapped[Integer] = mapped_column(Integer, nullable=False)  # default=1
    cuenta_padre_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("fin.plan_cuenta.id"), nullable=True)
    tipo: Mapped[String(30)] = mapped_column(String(30), nullable=False)
    clasificacion: Mapped[String(50)] = mapped_column(String(50), nullable=False)
    naturaleza: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    acepta_movimiento: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    requiere_centro_costo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    estado: Mapped[String(20)] = mapped_column(String(20), nullable=False)  # default='ACTIVO'::character varying
    descripcion: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinProveedorFin(Base):
    __tablename__ = "proveedor_fin"
    __table_args__ = {"schema": "fin"}

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin.proveedor_fin_id_seq'::regclass)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    condicion_pago_dias: Mapped[Integer] = mapped_column(Integer, nullable=False)  # default=30
    limite_credito: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    estado: Mapped[String  # USER-DEFINED::estado_simple] = mapped_column(String  # USER-DEFINED::estado_simple, nullable=False)  # default='ACTIVO'::fin.estado_simple
    notas: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class ApDocumentoCompra(Base):
    __tablename__ = "ap_documento_compra"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('ap_documento_compra_id_seq'::regclass)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[String  # USER-DEFINED::ap_documento_tipo] = mapped_column(String  # USER-DEFINED::ap_documento_tipo, nullable=False)
    estado: Mapped[String  # USER-DEFINED::ap_estado_documento] = mapped_column(String  # USER-DEFINED::ap_estado_documento, nullable=False)  # default='BORRADOR'::ap_estado_documento
    folio: Mapped[String(40)] = mapped_column(String(40), nullable=False)
    fecha_emision: Mapped[Date] = mapped_column(Date, nullable=False)
    fecha_recepcion: Mapped[Date] = mapped_column(Date, nullable=True)
    fecha_vencimiento: Mapped[Date] = mapped_column(Date, nullable=False)
    moneda: Mapped[String(10)] = mapped_column(String(10), nullable=False)  # default='CLP'::character varying
    tipo_cambio: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=1
    neto: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    exento: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    iva: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    otros_impuestos: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    total: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    saldo_pendiente: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    referencia: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    observaciones: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class ApDocumentoCompraDetalle(Base):
    __tablename__ = "ap_documento_compra_detalle"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('ap_documento_compra_detalle_id_seq'::regclass)
    documento_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    linea: Mapped[Integer] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[String(260)] = mapped_column(String(260), nullable=False)
    cantidad: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=1
    precio_unitario: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=0
    descuento: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    neto_linea: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    iva_linea: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    otros_impuestos: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    total_linea: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    categoria_gasto_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    centro_costo_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class ApPago(Base):
    __tablename__ = "ap_pago"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('ap_pago_id_seq'::regclass)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    estado: Mapped[String  # USER-DEFINED::ap_estado_pago] = mapped_column(String  # USER-DEFINED::ap_estado_pago, nullable=False)  # default='BORRADOR'::ap_estado_pago
    fecha_pago: Mapped[Date] = mapped_column(Date, nullable=False)
    medio_pago: Mapped[String  # USER-DEFINED::fin_medio_pago] = mapped_column(String  # USER-DEFINED::fin_medio_pago, nullable=False)  # default='TRANSFERENCIA'::fin_medio_pago
    referencia: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    moneda: Mapped[String(10)] = mapped_column(String(10), nullable=False)  # default='CLP'::character varying
    tipo_cambio: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=1
    monto_total: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    observaciones: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class ApPagoAplicacion(Base):
    __tablename__ = "ap_pago_aplicacion"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('ap_pago_aplicacion_id_seq'::regclass)
    pago_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    documento_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    monto_aplicado: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class AsientosContables(Base):
    __tablename__ = "asientos_contables"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('asientos_contables_id_seq'::regclass)
    fecha: Mapped[Date] = mapped_column(Date, nullable=False)
    descripcion: Mapped[Text] = mapped_column(Text, nullable=True)
    origen_tipo: Mapped[String(30)] = mapped_column(String(30), nullable=True)
    origen_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    glosa: Mapped[String(255)] = mapped_column(String(255), nullable=True)


class AsientosDetalle(Base):
    __tablename__ = "asientos_detalle"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('asientos_detalle_id_seq'::regclass)
    asiento_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("asientos_contables.id"), nullable=False)
    cuenta_contable: Mapped[String(50)] = mapped_column(String(50), nullable=True)
    descripcion: Mapped[String(255)] = mapped_column(String(255), nullable=True)
    debe: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    haber: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    codigo_cuenta: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    nombre_cuenta: Mapped[String(255)] = mapped_column(String(255), nullable=False)


class Cajas(Base):
    __tablename__ = "cajas"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('cajas_id_seq'::regclass)
    nombre: Mapped[String(100)] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[String(255)] = mapped_column(String(255), nullable=True)
    saldo_inicial: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_actual: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_apertura: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    fecha_cierre: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    estado: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    activa: Mapped[Boolean] = mapped_column(Boolean, nullable=False)


class CategoriasProducto(Base):
    __tablename__ = "categorias_producto"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('categorias_producto_id_seq'::regclass)
    nombre: Mapped[String(150)] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[Text] = mapped_column(Text, nullable=True)
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class Clientes(Base):
    __tablename__ = "clientes"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('clientes_id_seq'::regclass)
    rut: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    razon_social: Mapped[String(200)] = mapped_column(String(200), nullable=False)
    nombre_fantasia: Mapped[String(200)] = mapped_column(String(200), nullable=True)
    giro: Mapped[String(200)] = mapped_column(String(200), nullable=True)
    direccion: Mapped[String(250)] = mapped_column(String(250), nullable=True)
    comuna: Mapped[String(100)] = mapped_column(String(100), nullable=True)
    ciudad: Mapped[String(100)] = mapped_column(String(100), nullable=True)
    telefono: Mapped[String(50)] = mapped_column(String(50), nullable=True)
    email: Mapped[String(150)] = mapped_column(String(150), nullable=True)
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    fecha_actualizacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class CuentasPorCobrar(Base):
    __tablename__ = "cuentas_por_cobrar"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('cuentas_por_cobrar_id_seq'::regclass)
    cliente_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("clientes.id"), nullable=False)
    nota_venta_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("notas_venta.id"), nullable=True)
    fecha_emision: Mapped[Date] = mapped_column(Date, nullable=False)
    fecha_vencimiento: Mapped[Date] = mapped_column(Date, nullable=False)
    monto_original: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_pendiente: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    observacion: Mapped[Text] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    fecha_actualizacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    razon_social: Mapped[String(255)] = mapped_column(String(255), nullable=True)


class CuentasPorPagar(Base):
    __tablename__ = "cuentas_por_pagar"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('cuentas_por_pagar_id_seq'::regclass)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("proveedores.id"), nullable=False)
    factura_compra_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("facturas_compra.id"), nullable=True)
    fecha_emision: Mapped[Date] = mapped_column(Date, nullable=False)
    fecha_vencimiento: Mapped[Date] = mapped_column(Date, nullable=False)
    monto_original: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_pendiente: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    observacion: Mapped[Text] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    fecha_actualizacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class EmailLog(Base):
    __tablename__ = "email_log"

    id: Mapped[Integer] = mapped_column(Integer, primary_key=True, nullable=False)  # default=nextval('email_log_id_seq'::regclass)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=CURRENT_TIMESTAMP
    modulo: Mapped[String(50)] = mapped_column(String(50), nullable=False)  # default='COBRANZA'::character varying
    evento: Mapped[String(50)] = mapped_column(String(50), nullable=False)  # default='RECORDATORIO'::character varying
    cliente_id: Mapped[Integer] = mapped_column(Integer, nullable=True)
    cxc_id: Mapped[Integer] = mapped_column(Integer, nullable=True)
    to_email: Mapped[String(255)] = mapped_column(String(255), nullable=False)
    subject: Mapped[String(255)] = mapped_column(String(255), nullable=False)
    include_detalle: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    status: Mapped[String(20)] = mapped_column(String(20), nullable=False)  # default='PENDIENTE'::character varying
    sent_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Text] = mapped_column(Text, nullable=True)
    meta_json: Mapped[Text] = mapped_column(Text, nullable=True)


class FacturasCompra(Base):
    __tablename__ = "facturas_compra"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('facturas_compra_id_seq'::regclass)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("proveedores.id"), nullable=False)
    numero_documento: Mapped[String(50)] = mapped_column(String(50), nullable=False)
    fecha_emision: Mapped[Date] = mapped_column(Date, nullable=False)
    fecha_vencimiento: Mapped[Date] = mapped_column(Date, nullable=True)
    neto: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    iva: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    observacion: Mapped[Text] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    fecha_actualizacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class FacturasCompraDetalle(Base):
    __tablename__ = "facturas_compra_detalle"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('facturas_compra_detalle_id_seq'::regclass)
    factura_compra_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("facturas_compra.id"), nullable=False)
    producto_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("productos.id"), nullable=True)
    descripcion: Mapped[String(250)] = mapped_column(String(250), nullable=True)
    cantidad: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    costo_unitario: Mapped[Numeric(14, 4)] = mapped_column(Numeric(14, 4), nullable=False)
    subtotal: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)


class FinAdjunto(Base):
    __tablename__ = "fin_adjunto"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin_adjunto_id_seq'::regclass)
    entidad: Mapped[String(40)] = mapped_column(String(40), nullable=False)
    entidad_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    nombre: Mapped[String(220)] = mapped_column(String(220), nullable=False)
    mime: Mapped[String(120)] = mapped_column(String(120), nullable=True)
    storage_path: Mapped[String(500)] = mapped_column(String(500), nullable=False)
    hash_sha256: Mapped[String(80)] = mapped_column(String(80), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinCategoriaGasto(Base):
    __tablename__ = "fin_categoria_gasto"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin_categoria_gasto_id_seq'::regclass)
    codigo: Mapped[String(30)] = mapped_column(String(30), nullable=False)
    nombre: Mapped[String(160)] = mapped_column(String(160), nullable=False)
    tipo: Mapped[String  # USER-DEFINED::fin_tipo_gasto] = mapped_column(String  # USER-DEFINED::fin_tipo_gasto, nullable=False)  # default='OPERACIONAL'::fin_tipo_gasto
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinCentroCosto(Base):
    __tablename__ = "fin_centro_costo"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin_centro_costo_id_seq'::regclass)
    codigo: Mapped[String(30)] = mapped_column(String(30), nullable=False)
    nombre: Mapped[String(120)] = mapped_column(String(120), nullable=False)
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinEvento(Base):
    __tablename__ = "fin_evento"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin_evento_id_seq'::regclass)
    entidad: Mapped[String(40)] = mapped_column(String(40), nullable=False)
    entidad_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    evento: Mapped[String(80)] = mapped_column(String(80), nullable=False)
    detalle: Mapped[Text] = mapped_column(Text, nullable=True)
    user_email: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    ip_origen: Mapped[String(80)] = mapped_column(String(80), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class FinGasto(Base):
    __tablename__ = "fin_gasto"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('fin_gasto_id_seq'::regclass)
    estado: Mapped[String  # USER-DEFINED::fin_estado_gasto] = mapped_column(String  # USER-DEFINED::fin_estado_gasto, nullable=False)  # default='BORRADOR'::fin_estado_gasto
    fecha: Mapped[Date] = mapped_column(Date, nullable=False)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    documento_ref: Mapped[String(80)] = mapped_column(String(80), nullable=True)
    categoria_gasto_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    centro_costo_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    medio_pago: Mapped[String  # USER-DEFINED::fin_medio_pago] = mapped_column(String  # USER-DEFINED::fin_medio_pago, nullable=False)  # default='OTRO'::fin_medio_pago
    moneda: Mapped[String(10)] = mapped_column(String(10), nullable=False)  # default='CLP'::character varying
    tipo_cambio: Mapped[Numeric(18, 6)] = mapped_column(Numeric(18, 6), nullable=False)  # default=1
    neto: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    exento: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    iva: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    otros_impuestos: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    total: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    descripcion: Mapped[String(260)] = mapped_column(String(260), nullable=False)
    observaciones: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class InventarioMovimientos(Base):
    __tablename__ = "inventario_movimientos"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('inventario_movimientos_id_seq'::regclass)
    producto_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("productos.id"), nullable=False)
    fecha: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    tipo_movimiento: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    cantidad: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    costo_unitario: Mapped[Numeric(14, 4)] = mapped_column(Numeric(14, 4), nullable=False)
    referencia_tipo: Mapped[String(30)] = mapped_column(String(30), nullable=True)
    referencia_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    observacion: Mapped[Text] = mapped_column(Text, nullable=True)


class MovimientosCaja(Base):
    __tablename__ = "movimientos_caja"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('movimientos_caja_id_seq'::regclass)
    caja_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("cajas.id"), nullable=False)
    fecha: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    tipo_movimiento: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    medio_pago: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    monto: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    referencia_tipo: Mapped[String(30)] = mapped_column(String(30), nullable=True)
    referencia_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=True)
    observacion: Mapped[Text] = mapped_column(Text, nullable=True)


class NotasVenta(Base):
    __tablename__ = "notas_venta"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('notas_venta_id_seq'::regclass)
    numero: Mapped[String(50)] = mapped_column(String(50), nullable=False)
    fecha: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    cliente_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("clientes.id"), nullable=True)
    caja_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("cajas.id"), nullable=True)
    tipo_pago: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    estado: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    subtotal_neto: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    descuento_total: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    total_neto: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    total_iva: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    total_total: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    observacion: Mapped[Text] = mapped_column(Text, nullable=True)
    usuario_emisor: Mapped[String(100)] = mapped_column(String(100), nullable=True)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    fecha_actualizacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    fecha_vencimiento: Mapped[Date] = mapped_column(Date, nullable=False)


class NotasVentaDetalle(Base):
    __tablename__ = "notas_venta_detalle"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('notas_venta_detalle_id_seq'::regclass)
    nota_venta_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("notas_venta.id"), nullable=False)
    producto_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("productos.id"), nullable=True)
    descripcion: Mapped[String(250)] = mapped_column(String(250), nullable=True)
    cantidad: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    precio_unitario: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    descuento_porcentaje: Mapped[Numeric(5, 2)] = mapped_column(Numeric(5, 2), nullable=False)
    descuento_monto: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    subtotal: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)


class PagosClientes(Base):
    __tablename__ = "pagos_clientes"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('pagos_clientes_id_seq'::regclass)
    cuenta_cobrar_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("cuentas_por_cobrar.id"), nullable=False)
    fecha_pago: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    monto_pago: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    caja_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("cajas.id"), nullable=True)
    referencia: Mapped[String(100)] = mapped_column(String(100), nullable=True)
    observacion: Mapped[Text] = mapped_column(Text, nullable=True)
    forma_pago: Mapped[Text] = mapped_column(Text, nullable=True)


class PagosProveedores(Base):
    __tablename__ = "pagos_proveedores"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('pagos_proveedores_id_seq'::regclass)
    cuenta_pagar_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("cuentas_por_pagar.id"), nullable=False)
    fecha_pago: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    monto_pago: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    medio_pago: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    referencia: Mapped[String(100)] = mapped_column(String(100), nullable=True)
    observacion: Mapped[Text] = mapped_column(Text, nullable=True)


class Productos(Base):
    __tablename__ = "productos"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('productos_id_seq'::regclass)
    codigo: Mapped[String(50)] = mapped_column(String(50), nullable=False)
    nombre: Mapped[String(200)] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[Text] = mapped_column(Text, nullable=True)
    categoria_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("categorias_producto.id"), nullable=True)
    unidad_medida_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("unidades_medida.id"), nullable=True)
    precio_compra: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    precio_venta: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    stock_minimo: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    stock_actual: Mapped[Numeric(14, 2)] = mapped_column(Numeric(14, 2), nullable=False)
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    fecha_actualizacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    codigo_barra: Mapped[String(80)] = mapped_column(String(80), nullable=True)
    controla_stock: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    permite_venta_fraccionada: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    es_servicio: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false


class Proveedor(Base):
    __tablename__ = "proveedor"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('proveedor_id_seq'::regclass)
    rut: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    rut_normalizado: Mapped[String(20)] = mapped_column(String(20), nullable=True)
    razon_social: Mapped[String(180)] = mapped_column(String(180), nullable=False)
    nombre_fantasia: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    giro: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    email: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    telefono: Mapped[String(50)] = mapped_column(String(50), nullable=True)
    sitio_web: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    condicion_pago_dias: Mapped[Integer] = mapped_column(Integer, nullable=False)  # default=30
    limite_credito: Mapped[Numeric(18, 2)] = mapped_column(Numeric(18, 2), nullable=False)  # default=0
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    notas: Mapped[Text] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class ProveedorBanco(Base):
    __tablename__ = "proveedor_banco"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('proveedor_banco_id_seq'::regclass)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    banco: Mapped[String(120)] = mapped_column(String(120), nullable=False)
    tipo_cuenta: Mapped[String(60)] = mapped_column(String(60), nullable=False)
    numero_cuenta: Mapped[String(60)] = mapped_column(String(60), nullable=False)
    titular: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    rut_titular: Mapped[String(20)] = mapped_column(String(20), nullable=True)
    email_pago: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    es_principal: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class ProveedorContacto(Base):
    __tablename__ = "proveedor_contacto"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('proveedor_contacto_id_seq'::regclass)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    nombre: Mapped[String(120)] = mapped_column(String(120), nullable=False)
    cargo: Mapped[String(120)] = mapped_column(String(120), nullable=True)
    email: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    telefono: Mapped[String(50)] = mapped_column(String(50), nullable=True)
    es_principal: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class ProveedorDireccion(Base):
    __tablename__ = "proveedor_direccion"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('proveedor_direccion_id_seq'::regclass)
    proveedor_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    linea1: Mapped[String(180)] = mapped_column(String(180), nullable=False)
    linea2: Mapped[String(180)] = mapped_column(String(180), nullable=True)
    comuna: Mapped[String(120)] = mapped_column(String(120), nullable=True)
    ciudad: Mapped[String(120)] = mapped_column(String(120), nullable=True)
    region: Mapped[String(120)] = mapped_column(String(120), nullable=True)
    pais: Mapped[String(120)] = mapped_column(String(120), nullable=False)  # default='Chile'::character varying
    codigo_postal: Mapped[String(20)] = mapped_column(String(20), nullable=True)
    es_principal: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class Proveedores(Base):
    __tablename__ = "proveedores"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('proveedores_id_seq'::regclass)
    rut: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    razon_social: Mapped[String(200)] = mapped_column(String(200), nullable=False)
    nombre_fantasia: Mapped[String(200)] = mapped_column(String(200), nullable=True)
    giro: Mapped[String(200)] = mapped_column(String(200), nullable=True)
    direccion: Mapped[String(250)] = mapped_column(String(250), nullable=True)
    comuna: Mapped[String(100)] = mapped_column(String(100), nullable=True)
    ciudad: Mapped[String(100)] = mapped_column(String(100), nullable=True)
    telefono: Mapped[String(50)] = mapped_column(String(50), nullable=True)
    email: Mapped[String(150)] = mapped_column(String(150), nullable=True)
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    fecha_actualizacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class TenantDomains(Base):
    __tablename__ = "tenant_domains"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('tenant_domains_id_seq'::regclass)
    tenant_id: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    domain: Mapped[String(255)] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=false
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class Tenants(Base):
    __tablename__ = "tenants"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('tenants_id_seq'::regclass)
    tenant_code: Mapped[String(60)] = mapped_column(String(60), nullable=False)
    tenant_name: Mapped[String(160)] = mapped_column(String(160), nullable=False)
    db_driver: Mapped[String(80)] = mapped_column(String(80), nullable=False)  # default='postgresql+psycopg'::character varying
    db_host: Mapped[String(120)] = mapped_column(String(120), nullable=False)
    db_port: Mapped[Integer] = mapped_column(Integer, nullable=False)  # default=5432
    db_name: Mapped[String(120)] = mapped_column(String(120), nullable=False)
    db_user: Mapped[String(120)] = mapped_column(String(120), nullable=False)
    db_password: Mapped[Text] = mapped_column(Text, nullable=False)
    db_sslmode: Mapped[String(20)] = mapped_column(String(20), nullable=True)
    is_active: Mapped[Boolean] = mapped_column(Boolean, nullable=False)  # default=true
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)  # default=now()


class UnidadesMedida(Base):
    __tablename__ = "unidades_medida"

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, nullable=False)  # default=nextval('unidades_medida_id_seq'::regclass)
    codigo: Mapped[String(20)] = mapped_column(String(20), nullable=False)
    nombre: Mapped[String(100)] = mapped_column(String(100), nullable=False)
    simbolo: Mapped[String(20)] = mapped_column(String(20), nullable=True)
    activo: Mapped[Boolean] = mapped_column(Boolean, nullable=False)
    fecha_creacion: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
