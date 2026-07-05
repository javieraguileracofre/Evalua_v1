# services/leasing_financiero_tributario.py
# -*- coding: utf-8 -*-
"""Desglose tributario configurable para leasing financiero (Chile)."""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, Field

# Tasa IVA por defecto Chile (configurable vía env LF_IVA_TASA_DEFAULT).
IVA_TASA_DEFAULT = Decimal(os.getenv("LF_IVA_TASA_DEFAULT", "0.19"))


def _q2(v: Decimal | float | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(v: Decimal | float | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class DesgloseTributarioLF(BaseModel):
    valor_neto: Decimal = Decimal("0")
    base_afecta: Decimal = Decimal("0")
    base_exenta: Decimal = Decimal("0")
    iva_monto: Decimal = Decimal("0")
    iva_tasa_pct: Decimal = Decimal("0")
    total_con_iva: Decimal = Decimal("0")
    iva_recuperable: bool = True
    iva_credito_estimado: Decimal = Decimal("0")
    componente_interes_afecto: Decimal = Decimal("0")
    componente_interes_exento: Decimal = Decimal("0")
    notas: list[str] = Field(default_factory=list)
    trazabilidad: dict[str, Any] = Field(default_factory=dict)


def normalizar_tasa_iva(tasa: Decimal | float | int | None) -> Decimal:
    if tasa is None:
        return _q4(IVA_TASA_DEFAULT)
    t = Decimal(str(tasa))
    if t > Decimal("1"):
        t = t / Decimal("100")
    if t < Decimal("0") or t > Decimal("1"):
        raise ValueError("La tasa de IVA debe estar entre 0% y 100%.")
    return _q4(t)


def calcular_desglose_tributario(
    *,
    valor_neto: Decimal | None,
    iva_aplica: bool = False,
    iva_tasa: Decimal | float | int | None = None,
    iva_recuperable: bool = True,
    total_intereses: Decimal | None = None,
    interes_gravado_pct: Decimal | None = None,
) -> DesgloseTributarioLF:
    """
    Separa componentes afectos/no afectos de IVA sobre el bien.
    Los intereses se tratan como exentos por defecto (configurable vía interes_gravado_pct).
    """
    notas: list[str] = []
    neto = _q2(valor_neto or Decimal("0"))
    if neto <= 0:
        return DesgloseTributarioLF(notas=["Sin valor neto informado."])

    tasa = normalizar_tasa_iva(iva_tasa) if iva_aplica else Decimal("0")
    intereses = _q2(total_intereses or Decimal("0"))
    pct_int_grav = Decimal(str(interes_gravado_pct)) if interes_gravado_pct is not None else Decimal("0")
    if pct_int_grav > Decimal("1"):
        pct_int_grav = pct_int_grav / Decimal("100")

    if not iva_aplica:
        notas.append("Operación marcada sin IVA sobre el bien.")
        comp_int_afecto = _q2(intereses * pct_int_grav)
        comp_int_exento = _q2(intereses - comp_int_afecto)
        return DesgloseTributarioLF(
            valor_neto=neto,
            base_afecta=Decimal("0"),
            base_exenta=neto,
            iva_monto=Decimal("0"),
            iva_tasa_pct=Decimal("0"),
            total_con_iva=neto,
            iva_recuperable=iva_recuperable,
            componente_interes_afecto=comp_int_afecto,
            componente_interes_exento=comp_int_exento,
            notas=notas,
            trazabilidad={
                "regla_bien": "EXENTO",
                "regla_interes_gravado_pct": str(pct_int_grav),
            },
        )

    iva_monto = _q2(neto * tasa)
    total = _q2(neto + iva_monto)
    credito = _q2(iva_monto) if iva_recuperable else Decimal("0")
    comp_int_afecto = _q2(intereses * pct_int_grav)
    comp_int_exento = _q2(intereses - comp_int_afecto)

    notas.append("IVA calculado sobre valor neto del bien (base afecta).")
    if iva_recuperable:
        notas.append("IVA registrado como recuperable (crédito fiscal estimado).")
    else:
        notas.append("IVA no recuperable: costo para el cliente.")
    if intereses > 0:
        notas.append(
            f"Intereses: {_q2(pct_int_grav * 100)}% gravado / resto exento (configurable)."
        )

    return DesgloseTributarioLF(
        valor_neto=neto,
        base_afecta=neto,
        base_exenta=Decimal("0"),
        iva_monto=iva_monto,
        iva_tasa_pct=_q4(tasa * 100),
        total_con_iva=total,
        iva_recuperable=iva_recuperable,
        iva_credito_estimado=credito,
        componente_interes_afecto=comp_int_afecto,
        componente_interes_exento=comp_int_exento,
        notas=notas,
        trazabilidad={
            "regla_bien": "AFECTO",
            "iva_tasa_decimal": str(tasa),
            "regla_interes_gravado_pct": str(pct_int_grav),
        },
    )
