# services/leasing_operativo/tax_rules_cl.py
# -*- coding: utf-8 -*-
"""
Reglas tributarias parametrizables (Chile) — NO hardcodear sin fuente.

Fuentes primarias consultadas (SII / LIR):
  - Ley sobre Impuesto a la Renta, art. 31 (gasto necesario) y art. 31 N°5 (depreciación).
  - Circular SII N°53 de 2020 (gastos automóviles / station wagons y similares).
  - Art. 37 bis LIR + Circular SII N°5 de 2024 (leasing financiero con opción de compra
    celebrado desde 01-01-2023): tratamiento distinto al arrendamiento operativo.

Advertencia: el tratamiento de LEASING_FINANCIERO / ARRENDAMIENTO_CON_OPCION_COMPRA
NO se reutiliza automáticamente para ARRENDAMIENTO_OPERATIVO.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

# Catálogo normativo parametrizable (vigencia documentada; admin puede ajustar).
DEFAULT_TAX_RULES: dict[str, Any] = {
    "tipo_contrato_default": "ARRENDAMIENTO_OPERATIVO",
    "tipos_contrato": [
        "ARRENDAMIENTO_OPERATIVO",
        "LEASING_FINANCIERO",
        "ARRENDAMIENTO_CON_OPCION_COMPRA",
    ],
    "book_policy": {
        "metodo": "LINEAL",
        "vida_util_meses_default": 60,
        "valor_residual_contable_pct": 10,
        "fuente_normativa": "Política contable interna EvaluaERP (IFRS / NIC 16 alineada a política empresa)",
        "articulo": "N/A — contable, no tributaria",
        "circular": "",
        "fecha_vigencia": "2026-01-01",
        "fecha_actualizacion": "2026-10-08",
    },
    "tax_policy": {
        "metodo": "LINEAL_SII",
        "vida_util_meses_default": 36,
        "valor_residual_tributario_pct": 0,
        "aplica_depreciacion_arrendador_operativo": True,
        "aplica_art_37_bis": False,
        "fuente_normativa": "Ley sobre Impuesto a la Renta (LIR)",
        "articulo": "Art. 31 N°5 LIR",
        "circular": "Circular SII N°53/2020 (gastos vehículos); Circular SII N°5/2024 (art. 37 bis leasing financiero)",
        "fecha_vigencia": "2020-04-01",
        "fecha_actualizacion": "2026-10-08",
        "notas": [
            "Art. 31 N°5: cuota anual de depreciación de bienes del activo inmovilizado en uso en el giro.",
            "Circular 53/2020: limitaciones de gasto en automóviles/station wagons cuando no es giro habitual.",
            "Art. 37 bis + Circ. 5/2024: aplica a leasing financiero con opción de compra (no operativo puro).",
        ],
    },
    "por_tipo_contrato": {
        "ARRENDAMIENTO_OPERATIVO": {
            "deprecia_arrendador": True,
            "deprecia_arrendatario": False,
            "aplica_art_37_bis": False,
            "fuente_normativa": "LIR art. 31; régimen de arrendamiento operativo (bien en patrimonio del arrendador)",
            "articulo": "Art. 31 N°5 LIR",
            "circular": "Circular SII N°53/2020",
            "fecha_vigencia": "2020-04-01",
            "fecha_actualizacion": "2026-10-08",
        },
        "LEASING_FINANCIERO": {
            "deprecia_arrendador": False,
            "deprecia_arrendatario": True,
            "aplica_art_37_bis": True,
            "fuente_normativa": "LIR art. 37 bis; Ley 21.420",
            "articulo": "Art. 37 bis LIR",
            "circular": "Circular SII N°5/2024",
            "fecha_vigencia": "2023-01-01",
            "fecha_actualizacion": "2026-10-08",
        },
        "ARRENDAMIENTO_CON_OPCION_COMPRA": {
            "deprecia_arrendador": False,
            "deprecia_arrendatario": True,
            "aplica_art_37_bis": True,
            "fuente_normativa": "LIR art. 37 bis (contratos con opción de compra)",
            "articulo": "Art. 37 bis LIR",
            "circular": "Circular SII N°5/2024",
            "fecha_vigencia": "2023-01-01",
            "fecha_actualizacion": "2026-10-08",
        },
    },
}


def merge_tax_rules(policy: dict[str, Any] | None) -> dict[str, Any]:
    out = deepcopy(DEFAULT_TAX_RULES)
    if not isinstance(policy, dict):
        return out
    for k, v in policy.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def resolve_contract_tax(tipo_contrato: str, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = merge_tax_rules(rules)
    key = str(tipo_contrato or cfg.get("tipo_contrato_default") or "ARRENDAMIENTO_OPERATIVO").upper()
    row = dict((cfg.get("por_tipo_contrato") or {}).get(key) or {})
    row["tipo_contrato"] = key
    row["tax_policy"] = cfg.get("tax_policy") or {}
    row["book_policy"] = cfg.get("book_policy") or {}
    row["consulta_fecha"] = date.today().isoformat()
    return row
