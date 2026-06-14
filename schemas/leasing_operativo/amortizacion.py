# schemas/leasing_operativo/amortizacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AmortizacionOperacionalCuota(BaseModel):
    numero_cuota: int
    fecha_cuota: date | None = None
    saldo_inversion_inicial: Decimal = Field(..., description="Inversión neta pendiente al inicio del periodo.")
    renta_neta: Decimal = Field(..., description="Renta operacional neta del periodo.")
    costo_fondo: Decimal = Field(..., description="Costo financiero del periodo.")
    recupero_inversion: Decimal = Field(..., description="Recupero vía depreciación económica (no principal financiero).")
    costos_operativos: Decimal = Field(default=Decimal("0"))
    prima_riesgo: Decimal = Field(default=Decimal("0"))
    costo_comercial: Decimal = Field(default=Decimal("0"))
    margen_operacional: Decimal = Field(default=Decimal("0"))
    flujo_neto_inversionista: Decimal = Field(default=Decimal("0"))
    saldo_inversion_final: Decimal = Field(..., description="Inversión neta remanente.")

    model_config = ConfigDict(from_attributes=True)
