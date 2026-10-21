# services/leasing_operativo/residual_model.py
# -*- coding: utf-8 -*-
"""Valor residual: base paramétrica + estimación comercial por km/edad/tipo de uso."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any


TIPOS_USO: dict[str, dict[str, Any]] = {
    # Legacy (simulador)
    "URBANO": {"label": "Urbano", "desgaste_mult": Decimal("1.00"), "liquidez_mult": Decimal("1.02")},
    "INTERURBANO": {"label": "Interurbano / ruta", "desgaste_mult": Decimal("1.08"), "liquidez_mult": Decimal("1.00")},
    "MIXTO": {"label": "Mixto", "desgaste_mult": Decimal("1.12"), "liquidez_mult": Decimal("0.98")},
    "FAENA": {"label": "Faena / construcción", "desgaste_mult": Decimal("1.22"), "liquidez_mult": Decimal("0.92")},
    "MINERO": {"label": "Minero / industrial", "desgaste_mult": Decimal("1.35"), "liquidez_mult": Decimal("0.88")},
    # Taxonomía profesional (factores económicos en residual_value_v1.uso_factores)
    "USO_PARTICULAR": {"label": "Uso particular", "desgaste_mult": Decimal("1.00"), "liquidez_mult": Decimal("1.02")},
    "USO_EJECUTIVO": {"label": "Uso ejecutivo", "desgaste_mult": Decimal("1.02"), "liquidez_mult": Decimal("1.01")},
    "USO_COMERCIAL": {"label": "Uso comercial", "desgaste_mult": Decimal("1.12"), "liquidez_mult": Decimal("0.96")},
    "USO_REPARTO": {"label": "Uso reparto", "desgaste_mult": Decimal("1.18"), "liquidez_mult": Decimal("0.94")},
    "USO_LOGISTICO": {"label": "Uso logístico", "desgaste_mult": Decimal("1.20"), "liquidez_mult": Decimal("0.93")},
    "USO_CONSTRUCCION": {"label": "Uso construcción", "desgaste_mult": Decimal("1.28"), "liquidez_mult": Decimal("0.90")},
    "USO_MINERO": {"label": "Uso minero", "desgaste_mult": Decimal("1.35"), "liquidez_mult": Decimal("0.88")},
    "USO_TERRITORIO_EXTREMO": {"label": "Territorio extremo", "desgaste_mult": Decimal("1.40"), "liquidez_mult": Decimal("0.85")},
    "USO_INTENSIVO": {"label": "Uso intensivo", "desgaste_mult": Decimal("1.30"), "liquidez_mult": Decimal("0.90")},
}


def _d(v: Any, default: str = "0") -> Decimal:
    if v is None:
        return Decimal(default)
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v).replace(",", "."))
    except Exception:
        return Decimal(default)


def residual_base_valor(
    capex_total: Decimal,
    residual_base_pct: Decimal,
    plazo_meses: int,
) -> Decimal:
    """% base del tipo ajustado levemente por plazo (plazos largos reducen % residual típico)."""
    n = max(int(plazo_meses), 1)
    adj = Decimal("1") - (min(n, 84) * Decimal("0.0008"))
    adj = max(adj, Decimal("0.88"))
    pct = (residual_base_pct / Decimal("100")) * adj
    return (capex_total * pct).quantize(Decimal("1"))


def residual_ajustado(
    *,
    valor_base: Decimal,
    capex_total: Decimal,
    residual_max_pct: Decimal,
    scenario_mult: Decimal,
    liquidez_factor: Decimal,
    obsolescencia_factor: Decimal,
    desgaste_km_factor: Decimal,
    desgaste_hora_factor: Decimal,
    haircut_pct: Decimal,
    km_anual: Decimal,
    horas_anual: Decimal,
    marca_modelo_factor: Decimal,
    sector_economico_mult: Decimal,
    inflacion_activo_pct_anual: Decimal,
    condicion_factor: Decimal,
) -> dict[str, Any]:
    """
    valor_residual_ajustado = base * Π factores, tope % máximo sobre CAPEX, haircut conservador.
    """
    f_uso = Decimal("1") - (km_anual * desgaste_km_factor) - (horas_anual * desgaste_hora_factor)
    f_uso = max(f_uso, Decimal("0.65"))

    f_marca = max(min(marca_modelo_factor, Decimal("1.15")), Decimal("0.85"))
    f_cond = max(min(condicion_factor, Decimal("1.05")), Decimal("0.80"))
    f_inf = Decimal("1") + (inflacion_activo_pct_anual / Decimal("100")) * Decimal("0.35")

    raw = (
        valor_base
        * scenario_mult
        * liquidez_factor
        * obsolescencia_factor
        * f_uso
        * f_marca
        * sector_economico_mult
        * f_inf
        * f_cond
    )
    cap_max = capex_total * (residual_max_pct / Decimal("100"))
    capped = min(raw, cap_max)
    hc = haircut_pct / Decimal("100")
    final = capped * (Decimal("1") - hc)
    final = max(final, Decimal("0")).quantize(Decimal("1"))

    return {
        "valor_residual_base": float(valor_base),
        "valor_residual_ajustado": float(final),
        "factor_uso": float(f_uso),
        "factor_marca": float(f_marca),
        "tope_capex_pct": float(residual_max_pct),
        "haircut_pct": float(haircut_pct),
    }


def estimar_residual_cotizacion(
    *,
    valor_bien: Decimal,
    plazo_meses: int,
    km_anual: Decimal,
    km_inicial: Decimal = Decimal("0"),
    anio_vehiculo: int | None = None,
    tipo_uso: str = "INTERURBANO",
    residual_base_pct: Decimal = Decimal("35"),
    residual_max_pct: Decimal = Decimal("55"),
    liquidez_factor: Decimal = Decimal("1"),
    obsolescencia_factor: Decimal = Decimal("1"),
    desgaste_km_factor: Decimal = Decimal("0.0000008"),
    haircut_pct: Decimal = Decimal("5"),
    marca_modelo_factor: Decimal = Decimal("1"),
) -> dict[str, Any]:
    """
    Estimación comercial del residual al término del arriendo.

    Proyecta km acumulados y años de uso al fin del contrato, aplica curva de
    retención de valor y factores de tipo de uso. No scrapea portales: lista
    para conectar un proveedor de mercado más adelante (fuente=modelo_interno).
    """
    valor = max(_d(valor_bien), Decimal("0"))
    n = max(int(plazo_meses), 1)
    anios_contrato = (Decimal(n) / Decimal("12")).quantize(Decimal("0.01"))
    km_a = max(_d(km_anual), Decimal("0"))
    km_0 = max(_d(km_inicial), Decimal("0"))
    km_fin = (km_0 + km_a * anios_contrato).quantize(Decimal("1"))

    anio_hoy = date.today().year
    anio_v = int(anio_vehiculo or anio_hoy)
    edad_hoy = max(anio_hoy - anio_v, 0)
    edad_fin = float(Decimal(edad_hoy) + anios_contrato)

    uso_key = str(tipo_uso or "INTERURBANO").upper()
    uso_cfg = TIPOS_USO.get(uso_key) or TIPOS_USO["INTERURBANO"]
    desgaste_uso = _d(uso_cfg["desgaste_mult"], "1")
    liq_uso = _d(uso_cfg["liquidez_mult"], "1")

    # Curva de retención: pierde valor con edad y con km (referencia ~20k km/año)
    f_edad = Decimal("1") - (Decimal(str(min(edad_fin, 12))) * Decimal("0.055"))
    f_edad = max(f_edad, Decimal("0.35"))
    km_exceso = max(km_fin - (Decimal("20000") * Decimal(str(max(edad_fin, 0.5)))), Decimal("0"))
    f_km = Decimal("1") - (km_exceso * max(_d(desgaste_km_factor), Decimal("0.0000004")))
    f_km = max(f_km, Decimal("0.45"))
    f_uso = Decimal("1") / desgaste_uso
    f_marca = max(min(_d(marca_modelo_factor, "1"), Decimal("1.12")), Decimal("0.88"))

    base = residual_base_valor(valor, _d(residual_base_pct, "35"), n)
    raw = (
        base
        * f_edad
        * f_km
        * f_uso
        * f_marca
        * _d(liquidez_factor, "1")
        * liq_uso
        * _d(obsolescencia_factor, "1")
    )
    cap_max = valor * (_d(residual_max_pct, "55") / Decimal("100"))
    capped = min(raw, cap_max)
    sugerido = (capped * (Decimal("1") - _d(haircut_pct, "5") / Decimal("100"))).quantize(Decimal("1"))
    sugerido = max(min(sugerido, valor), Decimal("0"))
    capital = max(valor - sugerido, Decimal("0"))

    return {
        "fuente": "modelo_interno",
        "tipo_uso": uso_key,
        "tipo_uso_label": uso_cfg["label"],
        "plazo_meses": n,
        "anios_contrato": float(anios_contrato),
        "edad_hoy_anios": edad_hoy,
        "edad_fin_anios": round(edad_fin, 2),
        "km_anual": float(km_a),
        "km_inicial": float(km_0),
        "km_fin_estimado": float(km_fin),
        "valor_bien": float(valor),
        "valor_residual_sugerido": float(sugerido),
        "capital_amortizable_sugerido": float(capital),
        "pct_residual_sugerido": float((sugerido / valor * Decimal("100")).quantize(Decimal("0.01"))) if valor > 0 else 0.0,
        "factores": {
            "edad": float(f_edad),
            "km": float(f_km),
            "uso": float(f_uso),
            "marca": float(f_marca),
            "liquidez_uso": float(liq_uso),
        },
        "nota": "Estimación interna. Podrá conectarse a comparables de mercado; el comercial puede ajustar el residual.",
    }
