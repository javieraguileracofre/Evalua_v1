# models/comercial/leasing_financiero_cotizacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.comercial.leasing_financiero_credito import LeasingFinancieroAnalisisCredito
    from models.comercial.leasing_financiero_operacion import (
        LeasingFinancieroActivo,
        LeasingFinancieroAmortizacionLinea,
        LeasingFinancieroChecklistItem,
        LeasingFinancieroFacturaCompra,
        LeasingFinancieroOrdenCompra,
        LeasingFinancieroSolicitudPago,
    )
    from models.maestros.cliente import Cliente
    from models.maestros.proveedor import Proveedor


class LeasingFinancieroCotizacion(Base):
    """Cotización leasing financiero (tabla comercial_lf_cotizaciones)."""

    __tablename__ = "comercial_lf_cotizaciones"
    __table_args__ = (
        Index("ix_comercial_lf_cot_cliente_fecha", "cliente_id", "fecha_cotizacion"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cliente: Mapped["Cliente"] = relationship(
        "Cliente",
        back_populates="leasing_fin_cotizaciones",
        lazy="selectin",
    )

    monto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    moneda: Mapped[str] = mapped_column(String(10), default="CLP", server_default="CLP")
    dolar_valor: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    tasa: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    plazo: Mapped[int | None] = mapped_column(Integer)
    opcion_compra: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    periodos_gracia: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    periodicidad: Mapped[str] = mapped_column(
        String(20), default="MENSUAL", server_default="MENSUAL", nullable=False
    )

    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_primera_cuota: Mapped[date | None] = mapped_column(Date)
    valor_neto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    bien_descripcion: Mapped[str | None] = mapped_column(String(500))
    bien_tipo: Mapped[str | None] = mapped_column(String(80))

    pago_inicial_tipo: Mapped[str | None] = mapped_column(String(20))
    pago_inicial_valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    financia_seguro: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    seguro_monto_uf: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    otros_montos_pesos: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    comision_apertura: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    comision_apertura_tipo: Mapped[str | None] = mapped_column(String(20))
    financia_comision: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    gastos_operacionales: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    gps_monto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    financia_gps: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    gastos_administrativos: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    financia_gastos_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    iva_aplica: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    iva_tasa: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    iva_recuperable: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    observaciones: Mapped[str | None] = mapped_column(String(4000))
    tir_anual_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    cae_anual_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    metadata_tributaria: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'::jsonb"))

    proveedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("proveedor.id", ondelete="SET NULL"), index=True
    )
    tasa_fondeo: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    spread_margen: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    condiciones_congeladas: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    escenario_oficial_version: Mapped[int | None] = mapped_column(Integer)

    concesionario: Mapped[str | None] = mapped_column(String(255))
    ejecutivo: Mapped[str | None] = mapped_column(String(255))

    proveedor: Mapped["Proveedor | None"] = relationship("Proveedor", lazy="selectin")

    fecha_cotizacion: Mapped[date] = mapped_column(
        Date,
        default=date.today,
        server_default=text("CURRENT_DATE"),
        nullable=False,
    )

    uf_valor: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    monto_financiado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    numero_operacion: Mapped[str | None] = mapped_column(String(50))
    numero_contrato: Mapped[str | None] = mapped_column(String(50))
    asiento_id: Mapped[int | None] = mapped_column(BigInteger)
    fecha_aprobacion: Mapped[date | None] = mapped_column(Date)
    fecha_formalizacion: Mapped[date | None] = mapped_column(Date)
    fecha_activacion: Mapped[date | None] = mapped_column(Date)
    fecha_vigencia_desde: Mapped[date | None] = mapped_column(Date)
    fecha_vigencia_hasta: Mapped[date | None] = mapped_column(Date)

    aceptada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aceptada_por: Mapped[str | None] = mapped_column(String(200))
    condiciones_aceptadas: Mapped[str] = mapped_column(String(4000), default="", server_default=text("''"))
    snapshot_aceptacion_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'::jsonb"))
    pdf_aceptacion_path: Mapped[str | None] = mapped_column(String(500))
    email_aceptacion_enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_aceptacion_destino: Mapped[str | None] = mapped_column(String(255))

    estado_db: Mapped[str] = mapped_column(
        "estado",
        String(40),
        nullable=False,
        default="BORRADOR",
        server_default=text("'BORRADOR'"),
    )

    contrato_activo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    workflow_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'::jsonb"))

    @staticmethod
    def _normalizar_tasa_tipo(value: str | None) -> str:
        val = str(value or "ANUAL").strip().upper()
        return val if val in {"ANUAL", "MENSUAL"} else "ANUAL"

    @hybrid_property
    def tasa_tipo(self) -> str:
        """Tipo de tasa (ANUAL/MENSUAL).

        El rol de la app no es dueño de comercial_lf_cotizaciones, así que el
        parche 135 (columna tasa_tipo) no puede aplicarse en caliente. Se
        persiste en workflow_json hasta que un dueño ejecute el SQL.
        """
        raw = self.workflow_json if isinstance(self.workflow_json, dict) else {}
        return self._normalizar_tasa_tipo(raw.get("tasa_tipo"))

    @tasa_tipo.inplace.setter
    def _tasa_tipo_setter(self, value: str | None) -> None:
        raw = dict(self.workflow_json) if isinstance(self.workflow_json, dict) else {}
        raw["tasa_tipo"] = self._normalizar_tasa_tipo(value)
        self.workflow_json = raw

    @hybrid_property
    def estado(self) -> str:
        """Estado de flujo Fase 1.

        chk_comercial_lf_estado no admite EN_EVALUACION / ACUERDO_FIRMADO /
        ACTIVO_PENDIENTE_COMPRA / ACTIVO_ADQUIRIDO. La columna guarda el alias
        permitido y el canónico vive en workflow_json.estado_canonico.
        """
        from services.leasing_financiero_estados import estado_canonico

        raw = self.workflow_json if isinstance(self.workflow_json, dict) else {}
        stored = str(raw.get("estado_canonico") or "").strip().upper()
        if stored:
            return estado_canonico(stored)
        return estado_canonico(self.estado_db)

    @estado.inplace.setter
    def _estado_setter(self, value: str | None) -> None:
        from services.leasing_financiero_estados import estado_canonico, estado_para_db

        canon = estado_canonico(value)
        self.estado_db = estado_para_db(canon)
        raw = dict(self.workflow_json) if isinstance(self.workflow_json, dict) else {}
        raw["estado_canonico"] = canon
        self.workflow_json = raw

    @estado.inplace.expression
    def _estado_expression(cls):
        return cls.estado_db

    proyeccion_lineas: Mapped[list["LeasingFinancieroProyeccionLinea"]] = relationship(
        "LeasingFinancieroProyeccionLinea",
        back_populates="cotizacion",
        cascade="all, delete-orphan",
        order_by="LeasingFinancieroProyeccionLinea.secuencia",
    )
    analisis_credito: Mapped["LeasingFinancieroAnalisisCredito | None"] = relationship(
        "LeasingFinancieroAnalisisCredito",
        back_populates="cotizacion",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    historial: Mapped[list["LeasingFinancieroHistorial"]] = relationship(
        "LeasingFinancieroHistorial",
        cascade="all, delete-orphan",
        order_by="LeasingFinancieroHistorial.created_at",
        lazy="selectin",
    )
    activo: Mapped["LeasingFinancieroActivo | None"] = relationship(
        "LeasingFinancieroActivo",
        back_populates="cotizacion",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    amortizacion_lineas: Mapped[list["LeasingFinancieroAmortizacionLinea"]] = relationship(
        "LeasingFinancieroAmortizacionLinea",
        back_populates="cotizacion",
        cascade="all, delete-orphan",
        order_by="LeasingFinancieroAmortizacionLinea.numero_cuota",
        lazy="selectin",
    )
    ordenes_compra: Mapped[list["LeasingFinancieroOrdenCompra"]] = relationship(
        "LeasingFinancieroOrdenCompra",
        back_populates="cotizacion",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    facturas_compra: Mapped[list["LeasingFinancieroFacturaCompra"]] = relationship(
        "LeasingFinancieroFacturaCompra",
        back_populates="cotizacion",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    solicitudes_pago: Mapped[list["LeasingFinancieroSolicitudPago"]] = relationship(
        "LeasingFinancieroSolicitudPago",
        back_populates="cotizacion",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    checklist_items: Mapped[list["LeasingFinancieroChecklistItem"]] = relationship(
        "LeasingFinancieroChecklistItem",
        back_populates="cotizacion",
        cascade="all, delete-orphan",
        order_by="LeasingFinancieroChecklistItem.orden",
        lazy="selectin",
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class LeasingFinancieroProyeccionLinea(Base):
    """Líneas de proyección contable automática por cotización."""

    __tablename__ = "comercial_lf_proyeccion_linea"
    __table_args__ = (UniqueConstraint("cotizacion_id", "secuencia", name="uq_comercial_lf_proy_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion",
        back_populates="proyeccion_lineas",
    )

    secuencia: Mapped[int] = mapped_column(Integer, nullable=False)
    etapa: Mapped[str] = mapped_column(String(40), nullable=False)
    ref_cuota: Mapped[int | None] = mapped_column(Integer)
    glosa: Mapped[str] = mapped_column(String(500), nullable=False)
    cuenta_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    debe: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), server_default="0")
    haber: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class LeasingFinancieroDocumentoProceso(Base):
    __tablename__ = "comercial_lf_documento_proceso"
    __table_args__ = (UniqueConstraint("cotizacion_id", "modulo", "version_n", name="uq_lf_doc_proceso_version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modulo: Mapped[str] = mapped_column(String(40), nullable=False)
    version_n: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="RECIBIDO", server_default="RECIBIDO")
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    usuario: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class LeasingFinancieroHistorial(Base):
    __tablename__ = "comercial_lf_historial"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo_evento: Mapped[str] = mapped_column(String(40), nullable=False)
    estado_desde: Mapped[str | None] = mapped_column(String(40))
    estado_hasta: Mapped[str | None] = mapped_column(String(40))
    comentario: Mapped[str | None] = mapped_column(String(1000))
    usuario: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
