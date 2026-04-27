# services/leasing_credito_scoring.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from schemas.comercial.leasing_credito import LeasingCreditoInput, LeasingCreditoResultado


def _q(v: Decimal | float | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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


def _resultado(score: Decimal, motivos: list[str], dscr: Decimal | None, leverage: Decimal | None) -> LeasingCreditoResultado:
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

    return LeasingCreditoResultado(
        score_total=s,
        rating=rating,  # type: ignore[arg-type]
        recomendacion=recomendacion,  # type: ignore[arg-type]
        nivel_riesgo=riesgo,  # type: ignore[arg-type]
        motivo_resumen=" | ".join(motivos[:5]),
        dscr_calculado=dscr,
        leverage_calculado=leverage,
    )


def evaluar_credito(inp: LeasingCreditoInput) -> LeasingCreditoResultado:
    """
    Modelo de mercado bancario simplificado para leasing:
    - Persona natural: capacidad de pago (DTI), score buró, estabilidad, LTV.
    - Persona jurídica: DSCR, leverage, escala/estabilidad, comportamiento, LTV.
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

    score = Decimal("0")

    # 40% Capacidad de pago / DTI
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

    # 25% Score de buró
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

    # 15% Estabilidad laboral
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

    # 10% Comportamiento de pago
    score += _q(Decimal("10") * comp)

    # 10% LTV
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

    return _resultado(score, motivos, dscr=None, leverage=None)


def _evaluar_juridica(inp: LeasingCreditoInput) -> LeasingCreditoResultado:
    motivos: list[str] = []
    ventas = _q(inp.ventas_anuales)
    ebitda = _q(inp.ebitda_anual)
    deuda = _q(inp.deuda_financiera_total)
    patrimonio = _q(inp.patrimonio)
    anti = max(0, int(inp.anios_operacion or 0))
    ltv = _q(inp.ltv_pct)
    comp = _bucket_comportamiento(inp.comportamiento_pago)

    # Proxy anual para servicio de deuda: 35% de deuda financiera.
    servicio_deuda = _q(deuda * Decimal("0.35")) if deuda > 0 else Decimal("0.01")
    dscr = _q(ebitda / servicio_deuda) if servicio_deuda > 0 else Decimal("0")
    leverage = _q(deuda / patrimonio) if patrimonio > 0 else Decimal("99")
    margen = _q((ebitda / ventas) * Decimal("100")) if ventas > 0 else Decimal("0")

    score = Decimal("0")

    # 35% DSCR
    if dscr >= Decimal("2.0"):
        score += Decimal("35")
        motivos.append("DSCR >= 2.0")
    elif dscr >= Decimal("1.5"):
        score += Decimal("29")
    elif dscr >= Decimal("1.2"):
        score += Decimal("22")
    elif dscr >= Decimal("1.0"):
        score += Decimal("14")
        motivos.append("DSCR ajustado (1.0-1.2)")
    else:
        score += Decimal("6")
        motivos.append("DSCR < 1.0")

    # 25% Leverage
    if leverage <= Decimal("1.0"):
        score += Decimal("25")
    elif leverage <= Decimal("1.8"):
        score += Decimal("20")
    elif leverage <= Decimal("2.5"):
        score += Decimal("14")
    elif leverage <= Decimal("3.5"):
        score += Decimal("8")
        motivos.append("Leverage elevado")
    else:
        score += Decimal("3")
        motivos.append("Leverage crítico")

    # 15% Rentabilidad operativa
    if margen >= Decimal("20"):
        score += Decimal("15")
    elif margen >= Decimal("12"):
        score += Decimal("12")
    elif margen >= Decimal("7"):
        score += Decimal("9")
    elif margen > 0:
        score += Decimal("5")
    else:
        score += Decimal("2")
        motivos.append("Margen EBITDA bajo")

    # 10% Antigüedad empresa
    if anti >= 10:
        score += Decimal("10")
    elif anti >= 5:
        score += Decimal("8")
    elif anti >= 3:
        score += Decimal("6")
    elif anti >= 1:
        score += Decimal("4")
    else:
        score += Decimal("2")

    # 7% Comportamiento pago
    score += _q(Decimal("7") * comp)

    # 8% LTV
    if ltv <= 70:
        score += Decimal("8")
    elif ltv <= 80:
        score += Decimal("6")
    elif ltv <= 90:
        score += Decimal("4")
    elif ltv <= 100:
        score += Decimal("2")
    else:
        score += Decimal("1")

    return _resultado(score, motivos, dscr=dscr, leverage=leverage)
