# services/leasing_financiero_ui_forms.py
# -*- coding: utf-8 -*-
"""Parsers y normalizadores de formularios UI del leasing financiero."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Optional

from schemas.comercial.leasing_cotizacion import LeasingSimulacionInput
from services.leasing_financiero_estados import ESTADOS_LF as ESTADOS_LF_ALL


def parse_decimal(value: str, *, money: bool = False) -> Optional[Decimal]:
    if value is None or not isinstance(value, (str, int, float, Decimal)):
        return None
    value = (value or "").strip()
    if not value:
        return None
    value = value.replace(" ", "")

    if money:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", value):
            value = value.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", value):
            value = value.replace(",", "")

    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(value)
    except Exception:
        return None


def parse_int(value: str) -> Optional[int]:
    if value is None or not isinstance(value, (str, int)):
        return None
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except Exception:
        return None


def parse_date(value: str) -> Optional[date]:
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "si", "sí", "on")


def normalizar_estado(value: str | None) -> str:
    if not value:
        return "BORRADOR"
    v = str(value).strip().upper()
    return v if v in ESTADOS_LF_ALL else "BORRADOR"


def normalizar_tasa_tipo(value: str | None) -> str:
    v = str(value or "ANUAL").strip().upper()
    return v if v in {"ANUAL", "MENSUAL"} else "ANUAL"


def normalizar_moneda(value: str | None) -> str:
    v = str(value or "CLP").strip().upper()
    return v if v in {"CLP", "USD", "UF"} else "CLP"


def normalizar_periodicidad(value: str | None) -> str:
    v = str(value or "MENSUAL").strip().upper()
    if v not in {"MENSUAL", "TRIMESTRAL", "SEMESTRAL", "ANUAL"}:
        return "MENSUAL"
    return v


def cotizacion_a_simulacion(cotizacion) -> LeasingSimulacionInput:
    return LeasingSimulacionInput(
        moneda=str(cotizacion.moneda or "CLP"),
        tasa=cotizacion.tasa,
        tasa_tipo=getattr(cotizacion, "tasa_tipo", "ANUAL") or "ANUAL",
        plazo=cotizacion.plazo,
        opcion_compra=cotizacion.opcion_compra,
        periodos_gracia=cotizacion.periodos_gracia or 0,
        periodicidad=normalizar_periodicidad(getattr(cotizacion, "periodicidad", "MENSUAL")),
        fecha_inicio=cotizacion.fecha_inicio,
        fecha_primera_cuota=getattr(cotizacion, "fecha_primera_cuota", None),
        valor_neto=cotizacion.valor_neto,
        pago_inicial_tipo=cotizacion.pago_inicial_tipo,
        pago_inicial_valor=cotizacion.pago_inicial_valor,
        financia_seguro=bool(cotizacion.financia_seguro),
        seguro_monto_uf=cotizacion.seguro_monto_uf,
        otros_montos_pesos=cotizacion.otros_montos_pesos,
        comision_apertura=getattr(cotizacion, "comision_apertura", None),
        comision_apertura_tipo=getattr(cotizacion, "comision_apertura_tipo", None),
        financia_comision=bool(getattr(cotizacion, "financia_comision", False)),
        gastos_operacionales=getattr(cotizacion, "gastos_operacionales", None),
        gps_monto=getattr(cotizacion, "gps_monto", None),
        financia_gps=bool(getattr(cotizacion, "financia_gps", False)),
        gastos_administrativos=getattr(cotizacion, "gastos_administrativos", None),
        financia_gastos_admin=bool(getattr(cotizacion, "financia_gastos_admin", False)),
        iva_aplica=bool(getattr(cotizacion, "iva_aplica", False)),
        iva_tasa=getattr(cotizacion, "iva_tasa", None),
        iva_recuperable=bool(getattr(cotizacion, "iva_recuperable", True)),
        uf_valor=cotizacion.uf_valor,
        monto_financiado=cotizacion.monto_financiado,
        dolar_valor=cotizacion.dolar_valor,
    )


def validar_fx_moneda(moneda: str, uf_valor: Optional[Decimal], dolar_valor: Optional[Decimal]) -> None:
    if moneda == "USD" and (dolar_valor is None or dolar_valor <= 0):
        raise ValueError("Para cotizar en USD debe informar Valor dólar mayor a 0.")
    if moneda == "UF" and (uf_valor is None or uf_valor <= 0):
        raise ValueError("Para cotizar en UF debe informar Valor UF mayor a 0.")
