# services/leasing_credito_scoring.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from schemas.comercial.leasing_credito import LeasingCreditoInput, LeasingCreditoResultado, LeasingRatios


def _q(v: Decimal | float | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(v: Decimal | float | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _clamp(v: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _rating(score: Decimal) -> str:
    if score >= Decimal("85"):
        return "A"
    if score >= Decimal("72"):
        return "B"
    if score >= Decimal("58"):
        return "C"
    if score >= Decimal("45"):
        return "D"
    return "E"


def _bucket_comportamiento(valor: str) -> Decimal:
    v = (valor or "SIN_HISTORIAL").strip().upper()
    if v == "BUENO":
        return Decimal("1.0")
    if v == "REGULAR":
        return Decimal("0.6")
    if v == "MALO":
        return Decimal("0.1")
    return Decimal("0.45")


def calcular_ratios(inp: LeasingCreditoInput) -> LeasingRatios:
    """Ratios estándar de evaluación crediticia a partir de datos del cliente."""
    ventas = _q(inp.ventas_anuales)
    if ventas <= 0 and _q(inp.ventas_12m_iva) > 0:
        ventas = _q(inp.ventas_12m_iva)
    ebitda = _q(inp.ebitda_anual)
    deuda = _q(inp.deuda_financiera_total)
    patrimonio = _q(inp.patrimonio)
    ac = _q(inp.activo_corriente)
    pc = _q(inp.pasivo_corriente)
    utilidad = _q(inp.utilidad_neta_anual)
    gf = _q(inp.gastos_financieros_anual)
    pasivo_total = _q(inp.pasivo_total)
    if pasivo_total <= 0 and deuda > 0:
        pasivo_total = deuda

    servicio_deuda = _q(deuda * Decimal("0.35")) if deuda > 0 else Decimal("0")
    dscr = _q4(ebitda / servicio_deuda) if servicio_deuda > 0 else None
    leverage = _q4(deuda / patrimonio) if patrimonio > 0 else None
    margen = _q4((ebitda / ventas) * Decimal("100")) if ventas > 0 else None
    liquidez = _q4(ac / pc) if pc > 0 else None
    capital_trabajo = _q(ac - pc) if (ac > 0 or pc > 0) else None
    endeudamiento = None
    if patrimonio > 0 and pasivo_total > 0:
        endeudamiento = _q4((pasivo_total / patrimonio) * Decimal("100"))
    elif patrimonio > 0 and deuda > 0:
        endeudamiento = _q4((deuda / patrimonio) * Decimal("100"))
    cobertura = _q4(ebitda / gf) if gf > 0 else None
    rent_neta = _q4((utilidad / ventas) * Decimal("100")) if ventas > 0 else None

    alertas: list[str] = []
    if dscr is not None and dscr < Decimal("1.15"):
        alertas.append(f"DSCR {dscr} bajo umbral típico de 1,15.")
    if leverage is not None and leverage > Decimal("3.5"):
        alertas.append("Leverage (deuda/patrimonio) crítico (>3,5).")
    if liquidez is not None and liquidez < Decimal("1"):
        alertas.append("Liquidez corriente < 1,0: presión de caja de corto plazo.")
    if margen is not None and margen < Decimal("5"):
        alertas.append("Margen EBITDA débil (<5%).")
    if capital_trabajo is not None and capital_trabajo < 0:
        alertas.append("Capital de trabajo negativo.")
    if endeudamiento is not None and endeudamiento > Decimal("300"):
        alertas.append("Endeudamiento total/patrimonio > 300%.")
    if cobertura is not None and cobertura < Decimal("2"):
        alertas.append("Cobertura de gastos financieros < 2x.")
    ventas_iva = _q(inp.ventas_12m_iva)
    if ventas_iva > 0 and _q(inp.ventas_anuales) > 0:
        desvio = abs(ventas_iva - _q(inp.ventas_anuales)) / max(ventas_iva, Decimal("1"))
        if desvio > Decimal("0.25"):
            alertas.append("Desvío >25% entre ventas declaradas y ventas 12m desde IVA.")

    return LeasingRatios(
        dscr=dscr,
        leverage_ratio=leverage,
        margen_ebitda_pct=margen,
        liquidez_corriente=liquidez,
        endeudamiento_pct=endeudamiento,
        capital_trabajo=capital_trabajo,
        cobertura_gastos_fin=cobertura,
        rentabilidad_neta_pct=rent_neta,
        servicio_deuda_proxy=servicio_deuda if servicio_deuda > 0 else None,
        ventas_base=ventas if ventas > 0 else None,
        alertas=alertas,
    )


def _resultado(
    score: Decimal,
    motivos: list[str],
    ratios: LeasingRatios,
) -> LeasingCreditoResultado:
    s = _clamp(_q(score), Decimal("0"), Decimal("100"))
    rating = _rating(s)

    if s >= Decimal("75"):
        recomendacion = "APROBADO"
        riesgo = "BAJO"
    elif s >= Decimal("58"):
        recomendacion = "APROBADA_CONDICIONES"
        riesgo = "MEDIO"
    else:
        recomendacion = "RECHAZADO"
        riesgo = "ALTO"

    motivos_final = list(motivos)
    for a in ratios.alertas[:3]:
        if a not in motivos_final:
            motivos_final.append(a)

    return LeasingCreditoResultado(
        score_total=s,
        rating=rating,  # type: ignore[arg-type]
        recomendacion=recomendacion,  # type: ignore[arg-type]
        nivel_riesgo=riesgo,  # type: ignore[arg-type]
        motivo_resumen=" | ".join(motivos_final[:6]),
        dscr_calculado=ratios.dscr,
        leverage_calculado=ratios.leverage_ratio,
        liquidez_corriente=ratios.liquidez_corriente,
        margen_ebitda_pct=ratios.margen_ebitda_pct,
        endeudamiento_pct=ratios.endeudamiento_pct,
        capital_trabajo=ratios.capital_trabajo,
        cobertura_gastos_fin=ratios.cobertura_gastos_fin,
        rentabilidad_neta_pct=ratios.rentabilidad_neta_pct,
        ratios_json=ratios.to_dict(),
    )


def evaluar_credito(inp: LeasingCreditoInput) -> LeasingCreditoResultado:
    """
    Modelo de mercado bancario simplificado para leasing:
    - Persona natural: capacidad de pago (DTI), score buró, estabilidad, LTV.
    - Persona jurídica: DSCR, leverage, escala/estabilidad, comportamiento, LTV + ratios de balance/IVA.
    """
    if inp.tipo_persona == "NATURAL":
        return _evaluar_natural(inp)
    return _evaluar_juridica(inp)


def _evaluar_natural(inp: LeasingCreditoInput) -> LeasingCreditoResultado:
    motivos: list[str] = []
    ingresos = _q(inp.ingreso_neto_mensual)
    carga = _q(inp.carga_financiera_mensual)
    dti = _q((carga / ingresos) * Decimal("100")) if ingresos > 0 else Decimal("100")
    buro = Decimal(str(inp.score_buro or 0))
    ltv = _q(inp.ltv_pct)
    anti = max(0, int(inp.antiguedad_laboral_meses or 0))
    comp = _bucket_comportamiento(inp.comportamiento_pago)
    ratios = calcular_ratios(inp)

    score = Decimal("0")

    if dti <= 20:
        score += Decimal("40")
        motivos.append("DTI <= 20% (capacidad sólida)")
    elif dti <= 30:
        score += Decimal("34")
        motivos.append("DTI entre 21-30%")
    elif dti <= 40:
        score += Decimal("26")
        motivos.append("DTI entre 31-40%")
    elif dti <= 50:
        score += Decimal("16")
        motivos.append("DTI entre 41-50%")
    else:
        score += Decimal("6")
        motivos.append("DTI > 50% (estrés de capacidad)")

    if buro >= 820:
        score += Decimal("25")
        motivos.append("Buró excelente")
    elif buro >= 740:
        score += Decimal("21")
    elif buro >= 680:
        score += Decimal("16")
    elif buro >= 620:
        score += Decimal("10")
    elif buro > 0:
        score += Decimal("5")
    else:
        score += Decimal("9")
        motivos.append("Sin score buró, ponderación neutral")

    if anti >= 60:
        score += Decimal("15")
    elif anti >= 36:
        score += Decimal("12")
    elif anti >= 18:
        score += Decimal("9")
    elif anti >= 6:
        score += Decimal("6")
    else:
        score += Decimal("3")

    score += _q(Decimal("10") * comp)

    if ltv <= 70:
        score += Decimal("10")
    elif ltv <= 80:
        score += Decimal("8")
    elif ltv <= 90:
        score += Decimal("5")
    elif ltv <= 100:
        score += Decimal("3")
    else:
        score += Decimal("1")
        motivos.append("LTV > 100%")

    return _resultado(score, motivos, ratios)


def _evaluar_juridica(inp: LeasingCreditoInput) -> LeasingCreditoResultado:
    motivos: list[str] = []
    ratios = calcular_ratios(inp)
    dscr = ratios.dscr or Decimal("0")
    leverage = ratios.leverage_ratio or Decimal("99")
    margen = ratios.margen_ebitda_pct or Decimal("0")
    anti = max(0, int(inp.anios_operacion or 0))
    ltv = _q(inp.ltv_pct)
    comp = _bucket_comportamiento(inp.comportamiento_pago)
    liquidez = ratios.liquidez_corriente

    score = Decimal("0")

    # 30% DSCR
    if dscr >= Decimal("2.0"):
        score += Decimal("30")
        motivos.append("DSCR >= 2.0")
    elif dscr >= Decimal("1.5"):
        score += Decimal("25")
    elif dscr >= Decimal("1.2"):
        score += Decimal("19")
    elif dscr >= Decimal("1.0"):
        score += Decimal("12")
        motivos.append("DSCR ajustado (1.0-1.2)")
    else:
        score += Decimal("5")
        motivos.append("DSCR < 1.0")

    # 20% Leverage
    if leverage <= Decimal("1.0"):
        score += Decimal("20")
    elif leverage <= Decimal("1.8"):
        score += Decimal("16")
    elif leverage <= Decimal("2.5"):
        score += Decimal("11")
    elif leverage <= Decimal("3.5"):
        score += Decimal("6")
        motivos.append("Leverage elevado")
    else:
        score += Decimal("2")
        motivos.append("Leverage crítico")

    # 12% Rentabilidad operativa
    if margen >= Decimal("20"):
        score += Decimal("12")
    elif margen >= Decimal("12"):
        score += Decimal("10")
    elif margen >= Decimal("7"):
        score += Decimal("7")
    elif margen > 0:
        score += Decimal("4")
    else:
        score += Decimal("1")
        motivos.append("Margen EBITDA bajo")

    # 10% Liquidez (desde balance)
    if liquidez is None:
        score += Decimal("5")
        motivos.append("Sin dato de liquidez corriente en balance")
    elif liquidez >= Decimal("1.5"):
        score += Decimal("10")
        motivos.append("Liquidez corriente sólida")
    elif liquidez >= Decimal("1.2"):
        score += Decimal("8")
    elif liquidez >= Decimal("1.0"):
        score += Decimal("6")
    elif liquidez >= Decimal("0.8"):
        score += Decimal("3")
    else:
        score += Decimal("1")
        motivos.append("Liquidez corriente crítica")

    # 8% Antigüedad empresa
    if anti >= 10:
        score += Decimal("8")
    elif anti >= 5:
        score += Decimal("6")
    elif anti >= 3:
        score += Decimal("5")
    elif anti >= 1:
        score += Decimal("3")
    else:
        score += Decimal("1")

    # 8% Consistencia IVA vs ventas
    ventas_iva = _q(inp.ventas_12m_iva)
    ventas = _q(inp.ventas_anuales)
    if ventas_iva > 0 and ventas > 0:
        desvio = abs(ventas_iva - ventas) / max(ventas_iva, Decimal("1"))
        if desvio <= Decimal("0.10"):
            score += Decimal("8")
            motivos.append("Ventas coherentes con IVA 12m")
        elif desvio <= Decimal("0.25"):
            score += Decimal("5")
        else:
            score += Decimal("2")
            motivos.append("Inconsistencia ventas vs IVA")
    elif ventas_iva > 0 or _q(inp.iva_debito_12m) > 0:
        score += Decimal("5")
        motivos.append("IVA cargado; ventas cruzadas parciales")
    else:
        score += Decimal("3")
        motivos.append("Sin certificado IVA / carpeta tributaria parseada")

    # 7% Comportamiento pago
    score += _q(Decimal("7") * comp)

    # 5% LTV
    if ltv <= 70:
        score += Decimal("5")
    elif ltv <= 80:
        score += Decimal("4")
    elif ltv <= 90:
        score += Decimal("3")
    elif ltv <= 100:
        score += Decimal("2")
    else:
        score += Decimal("1")

    return _resultado(score, motivos, ratios)


def ratios_dict_from_resultado(resultado: LeasingCreditoResultado) -> dict[str, Any]:
    return dict(resultado.ratios_json or {})
