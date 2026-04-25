# schemas/comercial/leasing_amortizacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AmortizacionCuota(BaseModel):
    numero_cuota: int = Field(..., description="Número de cuota (1..N).")
    fecha_cuota: Optional[date] = Field(default=None, description="Fecha estimada de vencimiento.")
    saldo_inicial: Decimal = Field(..., description="Saldo al inicio del periodo.")
    cuota: Decimal = Field(..., description="Pago total del periodo.")
    interes: Decimal = Field(..., description="Interés del periodo.")
    amortizacion: Decimal = Field(..., description="Abono a capital del periodo.")
    saldo_final: Decimal = Field(..., description="Saldo al final del periodo.")
    es_gracia: bool = Field(default=False, description="Periodo de gracia (sin pago de cuota).")
    es_opcion_compra: bool = Field(default=False, description="Línea de opción de compra final.")

    model_config = ConfigDict(from_attributes=True)
