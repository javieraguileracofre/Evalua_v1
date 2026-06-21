# services/credito_riesgo/decision.py
# -*- coding: utf-8 -*-
"""Decisión crediticia, atribución de comité y condiciones sugeridas."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

ATRIBUCIONES_DEFAULT: dict[str, Any] = {
    "PYME": {"hasta_clp": 50_000_000, "nivel": "ANALISTA_SENIOR"},
    "MEDIANA": {"hasta_clp": 300_000_000, "nivel": "COMITE_LOCAL"},
    "GRAN_EMPRESA": {"hasta_clp": 2_000_000_000, "nivel": "COMITE_CORPORATIVO"},
    "sobre_limite": "COMITE_DIRECTORIO",
}


def _d(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def nivel_riesgo_desde_categoria(categoria: str) -> str:
    cat = categoria.strip().upper()
    if cat in ("A", "B"):
        return "BAJO"
    if cat == "C":
        return "MEDIO"
    if cat == "D":
        return "ALTO"
    return "CRITICO"


def clasificacion_riesgo_compat(categoria: str) -> str:
    """Mantiene compatibilidad con columna clasificacion_riesgo (incluye RECHAZADO)."""
    nivel = nivel_riesgo_desde_categoria(categoria)
    if nivel == "CRITICO":
        return "CRITICO"
    return nivel


def determinar_comite_atribucion(
    *,
    segmento: str,
    monto_solicitado: Any,
    categoria: str,
    politica: dict[str, Any] | None = None,
) -> str:
    pol = {**ATRIBUCIONES_DEFAULT, **(politica or {})}
    monto = _d(monto_solicitado)
    seg = segmento.upper()
    cfg = pol.get(seg, pol.get("MEDIANA", {}))
    limite = Decimal(str(cfg.get("hasta_clp", 300_000_000)))
    nivel_base = str(cfg.get("nivel", "COMITE_LOCAL"))

    if categoria in ("D", "E"):
        return str(pol.get("sobre_limite", "COMITE_DIRECTORIO"))
    if monto > limite:
        return str(pol.get("sobre_limite", "COMITE_DIRECTORIO"))
    return nivel_base


def generar_condiciones_sugeridas(
    *,
    segmento: str,
    categoria: str,
    eval_fin: dict[str, Any],
    eval_cual: dict[str, Any],
    documentos_pendientes: list[str] | None = None,
    garantia_cobertura_pct: float | None = None,
) -> list[str]:
    condiciones: list[str] = []
    seg = segmento.upper()

    if documentos_pendientes:
        condiciones.append(f"Completar documentación: {', '.join(documentos_pendientes[:5])}.")

    if categoria in ("B", "C", "D"):
        if garantia_cobertura_pct is not None and garantia_cobertura_pct < 100:
            condiciones.append("Reforzar garantías hasta cobertura mínima 100% del monto.")

    dscr = eval_fin.get("dscr")
    if dscr is not None and dscr < 1.3:
        condiciones.append("Monitoreo trimestral de flujo y DSCR mínimo 1,20.")

    if eval_cual.get("dimensiones", {}).get("calidad_informacion", 100) < 60:
        condiciones.append("Actualizar carpeta tributaria SII e IVA F29 antes de desembolso.")

    if seg == "PYME":
        condiciones.append("Aval personal del representante legal o socio mayoritario.")
    elif seg == "MEDIANA":
        condiciones.append("Presentar EEFF auditados o firmados por contador externo.")
    elif seg == "GRAN_EMPRESA":
        condiciones.append("Informe de exposición consolidada y cumplimiento de covenants.")

    if eval_fin.get("morosidad_historica_dias", 0) >= 30:
        condiciones.append("Historial de mora: exigir pagaré en blanco o línea reducida inicial.")

    return condiciones[:8]


def recomendacion_final(
    *,
    decision_motor: str,
    categoria: str,
    documentos_criticos_pendientes: int,
    score_cualitativo: float,
) -> str:
    if documentos_criticos_pendientes >= 2:
        return "SOLICITAR_ANTECEDENTES"
    if decision_motor == "APROBAR" and categoria in ("A", "B"):
        return "APROBAR"
    if decision_motor == "CONDICIONES" or categoria == "C":
        return "CONDICIONES"
    if decision_motor == "RECHAZAR" or categoria in ("D", "E"):
        return "RECHAZAR" if score_cualitativo < 35 else "COMITE"
    if categoria in ("D", "E"):
        return "RECHAZAR"
    return "COMITE"


def calcular_pricing(
    *,
    tasa_base_anual: Decimal,
    categoria: str,
    segmento: str,
    nivel_riesgo: str,
) -> dict[str, Any]:
    spread_seg = {"PYME": Decimal("0.5"), "MEDIANA": Decimal("0.3"), "GRAN_EMPRESA": Decimal("0.15")}
    spread_riesgo = {
        "BAJO": Decimal("0"),
        "MEDIO": Decimal("0.75"),
        "ALTO": Decimal("1.5"),
        "CRITICO": Decimal("3.0"),
    }
    seg = segmento.upper()
    spread = spread_seg.get(seg, Decimal("0.4")) + spread_riesgo.get(nivel_riesgo, Decimal("1"))
    tasa = (tasa_base_anual + spread).quantize(Decimal("0.0001"))
    return {
        "tasa_base_anual_pct": float(tasa_base_anual),
        "spread_segmento_pct": float(spread_seg.get(seg, Decimal("0.4"))),
        "spread_riesgo_pct": float(spread_riesgo.get(nivel_riesgo, Decimal("1"))),
        "tasa_sugerida_anual_pct": float(tasa),
        "moneda": "CLP",
        "nota_uf": "Pricing referencial en CLP; operaciones en UF requieren conversión diaria.",
    }
