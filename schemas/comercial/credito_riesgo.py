# schemas/comercial/credito_riesgo.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

SEGMENTOS_VALIDOS = ("PYME", "MEDIANA", "GRAN_EMPRESA")
ESTADOS_SOLICITUD = (
    "BORRADOR",
    "EN_EVALUACION",
    "APROBADA",
    "RECHAZADA",
    "COMITE",
    "CONDICIONES",
    "ARCHIVADA",
    "SOLICITAR_ANTECEDENTES",
)
RECOMENDACIONES = ("APROBAR", "CONDICIONES", "COMITE", "RECHAZAR", "SOLICITAR_ANTECEDENTES")
NIVELES_RIESGO = ("BAJO", "MEDIO", "ALTO", "CRITICO", "RECHAZADO")


class CreditoSolicitudBase(BaseModel):
    cliente_id: int
    tipo_persona: str = "JURIDICA"
    producto: str = "LEASING_FIN"
    sector_actividad: str | None = None
    moneda: str = "CLP"
    monto_solicitado: Decimal = Field(default=Decimal("0"), ge=0)
    plazo_solicitado: int = Field(default=12, ge=1, le=360)
    segmento_cliente: str = "PYME"
    segmento_manual: bool = False
    numero_trabajadores: int = Field(default=0, ge=0)
    ventas_anual: Decimal = Field(default=Decimal("0"), ge=0)
    deuda_total: Decimal = Field(default=Decimal("0"), ge=0)
    deuda_financiera: Decimal = Field(default=Decimal("0"), ge=0)
    patrimonio: Decimal = Field(default=Decimal("0"), ge=0)
    ebitda_anual: Decimal = Field(default=Decimal("0"))
    utilidad_neta_anual: Decimal = Field(default=Decimal("0"))
    gastos_financieros_anual: Decimal = Field(default=Decimal("0"), ge=0)
    flujo_caja_mensual: Decimal = Field(default=Decimal("0"))
    capital_trabajo: Decimal = Field(default=Decimal("0"))
    liquidez_corriente: Decimal | None = None
    concentracion_ingresos_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    concentracion_proveedores_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    historial_tributario: str = "SIN_INFO"
    score_buro_estado: str = "SIN_INFO"
    evaluacion_cualitativa_input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("segmento_cliente")
    @classmethod
    def validar_segmento(cls, v: str) -> str:
        u = v.strip().upper()
        if u not in SEGMENTOS_VALIDOS:
            raise ValueError(f"Segmento inválido: {v}")
        return u


class CreditoEvaluacionOut(BaseModel):
    id: int
    score_total: Decimal
    categoria: str
    clasificacion_riesgo: str
    nivel_riesgo: str | None = None
    segmento_cliente: str | None = None
    recomendacion: str
    decision_motor: str
    monto_maximo_sugerido: Decimal
    plazo_maximo_sugerido: int
    tasa_sugerida_anual: Decimal
    alertas_json: list[str] = Field(default_factory=list)
    condiciones_sugeridas_json: list[str] = Field(default_factory=list)
    motivos_json: list[str] = Field(default_factory=list)
    comite_atribucion: str | None = None

    model_config = {"from_attributes": True}


class CreditoDocumentoUpdate(BaseModel):
    estado: str
    referencia: str | None = None
    observaciones: str | None = None

    @field_validator("estado")
    @classmethod
    def validar_estado_doc(cls, v: str) -> str:
        u = v.strip().upper()
        if u not in ("PENDIENTE", "RECIBIDO", "VALIDADO", "RECHAZADO", "NO_APLICA"):
            raise ValueError(f"Estado documento inválido: {v}")
        return u
