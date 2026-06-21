# services/credito_riesgo/segmentacion.py
# -*- coding: utf-8 -*-
"""Clasificación PYME / Mediana / Gran Empresa según criterios parametrizables."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

SEGMENTOS = ("PYME", "MEDIANA", "GRAN_EMPRESA")

SEGMENTACION_DEFAULT: dict[str, Any] = {
    "uf_referencia_clp": 38000,
    "pyme_ventas_max_uf": 25000,
    "pyme_trabajadores_max": 49,
    "mediana_ventas_max_uf": 100000,
    "mediana_trabajadores_max": 199,
    "sectores_alto_riesgo": ["construccion", "retail", "transporte"],
}


def _d(v: Any, default: str = "0") -> Decimal:
    if v is None:
        return Decimal(default)
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


@dataclass
class ResultadoSegmentacion:
    segmento: str
    motivos: list[str]
    detalle: dict[str, Any]


def clasificar_segmento(
    *,
    ventas_anual: Any,
    numero_trabajadores: Any,
    sector_actividad: str | None = None,
    segmento_manual: str | None = None,
    politica: dict[str, Any] | None = None,
) -> ResultadoSegmentacion:
    """Determina segmento empresarial. Si segmento_manual es válido, lo respeta."""
    pol = {**SEGMENTACION_DEFAULT, **(politica or {})}
    uf_clp = _d(pol.get("uf_referencia_clp"), "38000")
    ventas = _d(ventas_anual)
    trabajadores = _i(numero_trabajadores, 0)
    motivos: list[str] = []

    manual = (segmento_manual or "").strip().upper()
    if manual in SEGMENTOS:
        motivos.append(f"Segmento fijado manualmente: {manual}.")
        return ResultadoSegmentacion(
            segmento=manual,
            motivos=motivos,
            detalle={"modo": "manual", "ventas_anual_clp": float(ventas), "trabajadores": trabajadores},
        )

    ventas_uf = (ventas / uf_clp) if uf_clp > 0 else Decimal("0")
    pyme_ventas = _d(pol.get("pyme_ventas_max_uf"))
    pyme_trab = _i(pol.get("pyme_trabajadores_max"), 49)
    mediana_ventas = _d(pol.get("mediana_ventas_max_uf"))
    mediana_trab = _i(pol.get("mediana_trabajadores_max"), 199)

    es_pyme = ventas_uf <= pyme_ventas or trabajadores <= pyme_trab
    es_mediana = (not es_pyme) and (ventas_uf <= mediana_ventas or trabajadores <= mediana_trab)

    if es_pyme:
        segmento = "PYME"
        motivos.append(
            f"Ventas ~{float(ventas_uf):,.0f} UF o {trabajadores} trabajadores dentro de umbral PYME."
        )
    elif es_mediana:
        segmento = "MEDIANA"
        motivos.append(
            f"Ventas ~{float(ventas_uf):,.0f} UF / {trabajadores} trabajadores: perfil Mediana Empresa."
        )
    else:
        segmento = "GRAN_EMPRESA"
        motivos.append(
            f"Ventas ~{float(ventas_uf):,.0f} UF y {trabajadores} trabajadores: perfil Gran Empresa."
        )

    sector = (sector_actividad or "").strip().lower()
    sectores_riesgo = [str(s).lower() for s in pol.get("sectores_alto_riesgo", [])]
    sector_alto_riesgo = any(s in sector for s in sectores_riesgo) if sector else False

    return ResultadoSegmentacion(
        segmento=segmento,
        motivos=motivos,
        detalle={
            "modo": "automatico",
            "ventas_anual_clp": float(ventas),
            "ventas_anual_uf": float(ventas_uf.quantize(Decimal("0.01"))),
            "trabajadores": trabajadores,
            "sector_alto_riesgo": sector_alto_riesgo,
            "umbrales": {
                "pyme_ventas_max_uf": float(pyme_ventas),
                "mediana_ventas_max_uf": float(mediana_ventas),
            },
        },
    )


def clave_ponderaciones_segmento(segmento: str) -> str:
    return {
        "PYME": "ponderaciones_pyme_v1",
        "MEDIANA": "ponderaciones_mediana_v1",
        "GRAN_EMPRESA": "ponderaciones_gran_v1",
    }.get(segmento.upper(), "ponderaciones_v1")
