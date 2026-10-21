# services/leasing_operativo/depreciation_service.py
# -*- coding: utf-8 -*-
"""Tres capas separadas: BOOK_VALUE / TAX_VALUE / MARKET_VALUE."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.leasing_operativo.tax_rules_cl import merge_tax_rules, resolve_contract_tax


def _d(v: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(v).replace(",", ".")) if v is not None else Decimal(default)
    except Exception:
        return Decimal(default)


def project_linear_value(
    *,
    costo_inicial: Decimal,
    vida_util_meses: int,
    residual_pct: Decimal,
    meses_transcurridos: int,
) -> dict[str, Any]:
    n = max(int(vida_util_meses), 1)
    m = max(min(int(meses_transcurridos), n), 0)
    residual = max(costo_inicial * (_d(residual_pct) / Decimal("100")), Decimal("0"))
    depreciable = max(costo_inicial - residual, Decimal("0"))
    dep_m = (depreciable / Decimal(n)).quantize(Decimal("1"))
    acum = (dep_m * Decimal(m)).quantize(Decimal("1"))
    if acum > depreciable:
        acum = depreciable
    valor = (costo_inicial - acum).quantize(Decimal("1"))
    return {
        "costo_inicial": float(costo_inicial),
        "vida_util_meses": n,
        "meses_transcurridos": m,
        "depreciacion_mensual": float(dep_m),
        "depreciacion_acumulada": float(acum),
        "valor": float(max(valor, residual if m >= n else valor)),
        "valor_residual_politica": float(residual),
    }


def calculate_value_layers(
    *,
    costo_activo: Any,
    plazo_meses: int,
    tipo_contrato: str = "ARRENDAMIENTO_OPERATIVO",
    tax_rules: dict[str, Any] | None = None,
    market_value_future: Any = None,
) -> dict[str, Any]:
    """
    MARKET_VALUE: proviene del motor de mercado (no se mezcla con libro/tributario).
    BOOK_VALUE / TAX_VALUE: política parametrizable con trazabilidad normativa.
    """
    costo = max(_d(costo_activo), Decimal("0"))
    rules = merge_tax_rules(tax_rules)
    contract = resolve_contract_tax(tipo_contrato, rules)
    book_p = rules.get("book_policy") or {}
    tax_p = rules.get("tax_policy") or {}

    book = project_linear_value(
        costo_inicial=costo,
        vida_util_meses=int(book_p.get("vida_util_meses_default") or 60),
        residual_pct=_d(book_p.get("valor_residual_contable_pct"), "10"),
        meses_transcurridos=plazo_meses,
    )
    tax = project_linear_value(
        costo_inicial=costo,
        vida_util_meses=int(tax_p.get("vida_util_meses_default") or 36),
        residual_pct=_d(tax_p.get("valor_residual_tributario_pct"), "0"),
        meses_transcurridos=plazo_meses,
    )
    # Si el contrato no permite depreciar al arrendador, TAX_VALUE permanece = costo (sin dep. en este rol)
    if not contract.get("deprecia_arrendador", True):
        tax = {
            "costo_inicial": float(costo),
            "vida_util_meses": int(tax_p.get("vida_util_meses_default") or 36),
            "meses_transcurridos": int(plazo_meses),
            "depreciacion_mensual": 0.0,
            "depreciacion_acumulada": 0.0,
            "valor": float(costo),
            "valor_residual_politica": 0.0,
            "nota": "Depreciación tributaria del bien no aplica al arrendador bajo este tipo_contrato.",
        }

    market_v = _d(market_value_future) if market_value_future is not None else None
    return {
        "BOOK_VALUE": {
            **book,
            "layer": "BOOK_VALUE",
            "fuente_normativa": book_p.get("fuente_normativa"),
            "articulo": book_p.get("articulo"),
            "circular": book_p.get("circular"),
            "fecha_vigencia": book_p.get("fecha_vigencia"),
            "fecha_actualizacion": book_p.get("fecha_actualizacion"),
        },
        "TAX_VALUE": {
            **tax,
            "layer": "TAX_VALUE",
            "fuente_normativa": (contract.get("fuente_normativa") or tax_p.get("fuente_normativa")),
            "articulo": contract.get("articulo") or tax_p.get("articulo"),
            "circular": contract.get("circular") or tax_p.get("circular"),
            "fecha_vigencia": contract.get("fecha_vigencia") or tax_p.get("fecha_vigencia"),
            "fecha_actualizacion": contract.get("fecha_actualizacion") or tax_p.get("fecha_actualizacion"),
            "tipo_contrato": contract.get("tipo_contrato"),
            "aplica_art_37_bis": bool(contract.get("aplica_art_37_bis")),
        },
        "MARKET_VALUE": {
            "layer": "MARKET_VALUE",
            "valor": float(market_v) if market_v is not None else None,
            "nota": "Estimación económica de mercado; independiente de libro y tributaria.",
        },
        "tipo_contrato": contract.get("tipo_contrato"),
        "VALOR_LIBROS_FINAL": book["valor"],
        "VALOR_TRIBUTARIO_FINAL": tax["valor"],
    }
