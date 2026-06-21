# services/credito_riesgo/evaluacion_cualitativa.py
# -*- coding: utf-8 -*-
"""Factores cualitativos de riesgo crediticio (escala 0-100 por dimensión)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

DIMENSIONES = (
    "calidad_administracion",
    "experiencia_negocio",
    "riesgo_sectorial",
    "dependencia_clientes",
    "dependencia_proveedores",
    "calidad_informacion",
    "riesgo_reputacional",
    "riesgo_legal_compliance",
)

PESOS_CUALITATIVOS: dict[str, Decimal] = {
    "calidad_administracion": Decimal("0.15"),
    "experiencia_negocio": Decimal("0.10"),
    "riesgo_sectorial": Decimal("0.15"),
    "dependencia_clientes": Decimal("0.15"),
    "dependencia_proveedores": Decimal("0.10"),
    "calidad_informacion": Decimal("0.15"),
    "riesgo_reputacional": Decimal("0.10"),
    "riesgo_legal_compliance": Decimal("0.10"),
}


def _d(v: Any, default: str = "50") -> Decimal:
    if v is None:
        return Decimal(default)
    try:
        val = Decimal(str(v))
        return max(Decimal("0"), min(val, Decimal("100")))
    except Exception:
        return Decimal(default)


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


@dataclass
class EvaluacionCualitativa:
    score_total: Decimal
    dimensiones: dict[str, float]
    alertas: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_total": float(self.score_total),
            "dimensiones": self.dimensiones,
            "alertas": self.alertas,
            "motivos": self.motivos,
        }


def _inferir_desde_solicitud(
    *,
    segmento: str,
    sector_actividad: str | None,
    concentracion_ingresos_pct: Any,
    concentracion_proveedores_pct: Any,
    historial_tributario: str | None,
    anios_operacion: int,
    protestos: int,
    castigos: int,
    score_buro_estado: str | None,
) -> dict[str, Decimal]:
    """Completa dimensiones no informadas con heurísticas conservadoras."""
    conc_cli = _d(concentracion_ingresos_pct, "0")
    conc_prov = _d(concentracion_proveedores_pct, "0")
    hist = (historial_tributario or "SIN_INFO").upper()
    buro = (score_buro_estado or "SIN_INFO").upper()

    dep_clientes = Decimal("85") - min(conc_cli * Decimal("0.8"), Decimal("60"))
    dep_proveedores = Decimal("85") - min(conc_prov * Decimal("0.7"), Decimal("50"))

    calidad_info = Decimal("70")
    if hist == "AL_DIA":
        calidad_info = Decimal("85")
    elif hist == "OBSERVADO":
        calidad_info = Decimal("45")
    elif hist == "IRREGULAR":
        calidad_info = Decimal("20")
    elif hist == "SIN_INFO":
        calidad_info = Decimal("50")

    riesgo_legal = Decimal("75")
    if protestos > 0 or castigos > 0:
        riesgo_legal -= Decimal("30")
    if hist == "IRREGULAR":
        riesgo_legal -= Decimal("25")

    riesgo_reput = Decimal("70")
    if buro == "DESFAVORABLE":
        riesgo_reput = Decimal("30")
    elif buro == "CRITICO":
        riesgo_reput = Decimal("10")
    elif buro == "FAVORABLE":
        riesgo_reput = Decimal("90")

    exp_neg = Decimal("50")
    if anios_operacion >= 10:
        exp_neg = Decimal("90")
    elif anios_operacion >= 5:
        exp_neg = Decimal("75")
    elif anios_operacion >= 2:
        exp_neg = Decimal("60")

    sector = (sector_actividad or "").lower()
    riesgo_sector = Decimal("65")
    if any(k in sector for k in ("construccion", "retail", "transporte")):
        riesgo_sector = Decimal("40")
    elif any(k in sector for k in ("salud", "utilities", "telecom")):
        riesgo_sector = Decimal("75")

    admin = Decimal("65") if segmento == "PYME" else Decimal("70")

    return {
        "calidad_administracion": admin,
        "experiencia_negocio": exp_neg,
        "riesgo_sectorial": riesgo_sector,
        "dependencia_clientes": max(dep_clientes, Decimal("0")),
        "dependencia_proveedores": max(dep_proveedores, Decimal("0")),
        "calidad_informacion": calidad_info,
        "riesgo_reputacional": max(riesgo_reput, Decimal("0")),
        "riesgo_legal_compliance": max(riesgo_legal, Decimal("0")),
    }


def evaluar_cualitativo(
    *,
    segmento: str,
    input_json: dict[str, Any] | None,
    sector_actividad: str | None = None,
    concentracion_ingresos_pct: Any = 0,
    concentracion_proveedores_pct: Any = 0,
    historial_tributario: str | None = None,
    anios_operacion_empresa: Any = 0,
    antiguedad_meses_natural: Any = 0,
    tipo_persona: str = "JURIDICA",
    protestos: Any = 0,
    castigos: Any = 0,
    score_buro_estado: str | None = None,
) -> EvaluacionCualitativa:
    tipo_p = (tipo_persona or "JURIDICA").upper()
    anios = _i(anios_operacion_empresa, 0)
    if tipo_p == "NATURAL":
        anios = max(anios, _i(antiguedad_meses_natural, 0) // 12)

    base = _inferir_desde_solicitud(
        segmento=segmento,
        sector_actividad=sector_actividad,
        concentracion_ingresos_pct=concentracion_ingresos_pct,
        concentracion_proveedores_pct=concentracion_proveedores_pct,
        historial_tributario=historial_tributario,
        anios_operacion=anios,
        protestos=_i(protestos, 0),
        castigos=_i(castigos, 0),
        score_buro_estado=score_buro_estado,
    )

    inp = input_json or {}
    dimensiones: dict[str, float] = {}
    for dim in DIMENSIONES:
        if dim in inp and inp[dim] is not None:
            dimensiones[dim] = float(_d(inp[dim]))
        else:
            dimensiones[dim] = float(base[dim])

    score = Decimal("0")
    for dim, peso in PESOS_CUALITATIVOS.items():
        score += Decimal(str(dimensiones[dim])) * peso

    alertas: list[str] = []
    motivos: list[str] = []

    if dimensiones["dependencia_clientes"] < 50:
        alertas.append("Alta dependencia de pocos clientes.")
        motivos.append("Concentración de ingresos eleva riesgo comercial.")
    if dimensiones["calidad_informacion"] < 50:
        alertas.append("Calidad de información entregada insuficiente.")
        motivos.append("Antecedentes incompletos o tributarios observados.")
    if dimensiones["riesgo_legal_compliance"] < 45:
        alertas.append("Riesgo legal/compliance elevado.")
    if segmento == "GRAN_EMPRESA" and dimensiones["riesgo_sectorial"] < 50:
        alertas.append("Sector de alto riesgo sistémico para exposición corporativa.")

    return EvaluacionCualitativa(
        score_total=score.quantize(Decimal("0.01")),
        dimensiones=dimensiones,
        alertas=alertas,
        motivos=motivos,
    )
