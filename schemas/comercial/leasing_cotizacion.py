# schemas/comercial/leasing_cotizacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

ESTADOS_LF = {
    "BORRADOR",
    "COTIZADA",
    "EN_ANALISIS_COMERCIAL",
    "EN_ANALISIS_CREDITO",
    "APROBADA_CONDICIONES",
    "APROBADA",
    "RECHAZADA",
    "EN_FORMALIZACION",
    "DOCUMENTACION_COMPLETA",
    "ACTIVADA",
    "VIGENTE",
    "ANULADA",
    "PERDIDA_CLIENTE",
}


PERIODICIDADES_LF = frozenset({"MENSUAL", "TRIMESTRAL", "SEMESTRAL", "ANUAL"})


class LeasingCotizacionBase(BaseModel):
    cliente_id: int
    monto: Optional[Decimal] = None
    moneda: str = "CLP"
    tasa: Optional[Decimal] = None
    plazo: Optional[int] = None
    opcion_compra: Optional[Decimal] = None
    periodos_gracia: Optional[int] = 0
    periodicidad: str = Field(default="MENSUAL", max_length=20)
    fecha_inicio: Optional[date] = None
    fecha_primera_cuota: Optional[date] = None

    bien_descripcion: Optional[str] = Field(default=None, max_length=500)
    bien_tipo: Optional[str] = Field(default=None, max_length=80)

    valor_neto: Optional[Decimal] = None
    pago_inicial_tipo: Optional[str] = None
    pago_inicial_valor: Optional[Decimal] = None

    financia_seguro: bool = False
    seguro_monto_uf: Optional[Decimal] = None
    otros_montos_pesos: Optional[Decimal] = None
    comision_apertura: Optional[Decimal] = None
    comision_apertura_tipo: Optional[str] = None
    financia_comision: bool = False
    gastos_operacionales: Optional[Decimal] = None
    gps_monto: Optional[Decimal] = None
    financia_gps: bool = False
    gastos_administrativos: Optional[Decimal] = None
    financia_gastos_admin: bool = False

    iva_aplica: bool = False
    iva_tasa: Optional[Decimal] = None
    iva_recuperable: bool = True
    observaciones: Optional[str] = Field(default=None, max_length=4000)

    concesionario: Optional[str] = None
    ejecutivo: Optional[str] = None
    proveedor_id: Optional[int] = None
    tasa_fondeo: Optional[Decimal] = None
    spread_margen: Optional[Decimal] = None
    activo_marca: Optional[str] = Field(default=None, max_length=120)
    activo_modelo: Optional[str] = Field(default=None, max_length=120)
    activo_serie: Optional[str] = Field(default=None, max_length=80)
    activo_chasis: Optional[str] = Field(default=None, max_length=80)
    condiciones_congeladas: bool = False
    escenario_oficial_version: Optional[int] = None
    fecha_cotizacion: Optional[date] = None
    uf_valor: Optional[Decimal] = None
    monto_financiado: Optional[Decimal] = None
    dolar_valor: Optional[Decimal] = None

    estado: str = Field(default="BORRADOR", max_length=40)
    contrato_activo: bool = False
    numero_operacion: Optional[str] = None
    numero_contrato: Optional[str] = None
    asiento_id: Optional[int] = None
    fecha_aprobacion: Optional[date] = None
    fecha_formalizacion: Optional[date] = None
    fecha_activacion: Optional[date] = None
    fecha_vigencia_desde: Optional[date] = None
    fecha_vigencia_hasta: Optional[date] = None
    tir_anual_pct: Optional[Decimal] = None
    cae_anual_pct: Optional[Decimal] = None
    metadata_tributaria: Optional[dict[str, Any]] = None
    aceptada_en: Optional[datetime] = None
    aceptada_por: Optional[str] = None
    condiciones_aceptadas: str = ""
    snapshot_aceptacion_json: Optional[dict[str, Any]] = None
    pdf_aceptacion_path: Optional[str] = None
    email_aceptacion_enviado_en: Optional[datetime] = None
    email_aceptacion_destino: Optional[str] = None


class LeasingCotizacionCreate(LeasingCotizacionBase):
    pass


class LeasingCotizacionUpdate(BaseModel):
    monto: Optional[Decimal] = None
    moneda: Optional[str] = None
    tasa: Optional[Decimal] = None
    plazo: Optional[int] = None
    opcion_compra: Optional[Decimal] = None
    periodos_gracia: Optional[int] = None
    periodicidad: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_primera_cuota: Optional[date] = None
    bien_descripcion: Optional[str] = None
    bien_tipo: Optional[str] = None
    valor_neto: Optional[Decimal] = None
    pago_inicial_tipo: Optional[str] = None
    pago_inicial_valor: Optional[Decimal] = None
    financia_seguro: Optional[bool] = None
    seguro_monto_uf: Optional[Decimal] = None
    otros_montos_pesos: Optional[Decimal] = None
    comision_apertura: Optional[Decimal] = None
    comision_apertura_tipo: Optional[str] = None
    financia_comision: Optional[bool] = None
    gastos_operacionales: Optional[Decimal] = None
    gps_monto: Optional[Decimal] = None
    financia_gps: Optional[bool] = None
    gastos_administrativos: Optional[Decimal] = None
    financia_gastos_admin: Optional[bool] = None
    iva_aplica: Optional[bool] = None
    iva_tasa: Optional[Decimal] = None
    iva_recuperable: Optional[bool] = None
    observaciones: Optional[str] = None
    concesionario: Optional[str] = None
    ejecutivo: Optional[str] = None
    proveedor_id: Optional[int] = None
    tasa_fondeo: Optional[Decimal] = None
    spread_margen: Optional[Decimal] = None
    activo_marca: Optional[str] = None
    activo_modelo: Optional[str] = None
    activo_serie: Optional[str] = None
    activo_chasis: Optional[str] = None
    condiciones_congeladas: Optional[bool] = None
    escenario_oficial_version: Optional[int] = None
    fecha_cotizacion: Optional[date] = None
    uf_valor: Optional[Decimal] = None
    monto_financiado: Optional[Decimal] = None
    dolar_valor: Optional[Decimal] = None
    estado: Optional[str] = None
    contrato_activo: Optional[bool] = None
    numero_operacion: Optional[str] = None
    numero_contrato: Optional[str] = None
    asiento_id: Optional[int] = None
    fecha_aprobacion: Optional[date] = None
    fecha_formalizacion: Optional[date] = None
    fecha_activacion: Optional[date] = None
    fecha_vigencia_desde: Optional[date] = None
    fecha_vigencia_hasta: Optional[date] = None
    tir_anual_pct: Optional[Decimal] = None
    cae_anual_pct: Optional[Decimal] = None
    metadata_tributaria: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")


class LeasingCotizacionRead(LeasingCotizacionBase):
    id: int
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LeasingSimulacionInput(BaseModel):
    """Parámetros para simular una cotización sin persistir."""

    moneda: str = "CLP"
    tasa: Optional[Decimal] = None
    plazo: Optional[int] = None
    opcion_compra: Optional[Decimal] = None
    periodos_gracia: Optional[int] = 0
    periodicidad: str = "MENSUAL"
    fecha_inicio: Optional[date] = None
    fecha_primera_cuota: Optional[date] = None
    valor_neto: Optional[Decimal] = None
    pago_inicial_tipo: Optional[str] = None
    pago_inicial_valor: Optional[Decimal] = None
    financia_seguro: bool = False
    seguro_monto_uf: Optional[Decimal] = None
    otros_montos_pesos: Optional[Decimal] = None
    comision_apertura: Optional[Decimal] = None
    comision_apertura_tipo: Optional[str] = None
    financia_comision: bool = False
    gastos_operacionales: Optional[Decimal] = None
    gps_monto: Optional[Decimal] = None
    financia_gps: bool = False
    gastos_administrativos: Optional[Decimal] = None
    financia_gastos_admin: bool = False
    iva_aplica: bool = False
    iva_tasa: Optional[Decimal] = None
    iva_recuperable: bool = True
    uf_valor: Optional[Decimal] = None
    monto_financiado: Optional[Decimal] = None
    dolar_valor: Optional[Decimal] = None
    tasa_fondeo: Optional[Decimal] = None
    spread_margen: Optional[Decimal] = None

    model_config = ConfigDict(extra="forbid")


class LeasingSimulacionResumen(BaseModel):
    moneda: str
    valor_neto: Optional[Decimal] = None
    pago_inicial: Decimal = Decimal("0")
    seguro_financiado: Decimal = Decimal("0")
    otros_montos: Decimal = Decimal("0")
    gps_financiado: Decimal = Decimal("0")
    gastos_admin_financiados: Decimal = Decimal("0")
    monto_financiado: Decimal
    renta_mensual: Optional[Decimal] = None
    total_intereses: Decimal = Decimal("0")
    total_rentas: Decimal = Decimal("0")
    total_opcion_compra: Decimal = Decimal("0")
    total_desembolso: Decimal = Decimal("0")
    tasa_nominal_anual_pct: Optional[Decimal] = None
    tea_anual_pct: Optional[Decimal] = None
    tir_anual_pct: Optional[Decimal] = None
    cae_anual_pct: Optional[Decimal] = None
    periodicidad: str = "MENSUAL"
    desglose_tributario: dict[str, Any] = Field(default_factory=dict)
    cuotas_operativas: int = 0
    periodos_gracia: int = 0
    monto_financiado_calculado: bool = False
    advertencias: list[str] = Field(default_factory=list)
