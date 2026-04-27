# services/credito_riesgo_motor.py
# -*- coding: utf-8 -*-
"""
Motor Crédito y Riesgo EvaluaERP — score 0-1000, macro (Chile referencia) + micro.
Salidas: categoría A-E, clasificación Bajo/Medio/Alto/Rechazado, monto/plazo/tasa sugeridos,
recomendación APROBAR | CONDICIONES | COMITE | RECHAZAR y texto explicativo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

# --- Referencia macro interna (editable vía credito_politica.macro_referencia_chile_202602) ---
MACRO_DEFAULT: dict[str, Decimal] = {
    "inflacion_anual_pct": Decimal("2.4"),
    "pib_crecimiento_pct": Decimal("2.5"),
    "morosidad_90_mas_pct": Decimal("2.35"),
    "cartera_deteriorada_pct": Decimal("8.45"),
    "tpm_referencia_anual_pct": Decimal("5.25"),
}

# Sector → penalización 0-1 sobre bucket macro-sectorial (1 = más riesgo)
SECTOR_PENALIZACION: dict[str, Decimal] = {
    "salud": Decimal("0.15"),
    "alimentos": Decimal("0.25"),
    "transporte": Decimal("0.45"),
    "construccion": Decimal("0.55"),
    "retail": Decimal("0.50"),
    "retail pequeño": Decimal("0.55"),
    "empresa nueva": Decimal("0.85"),
    "tecnologia": Decimal("0.35"),
    "servicios": Decimal("0.40"),
    "default": Decimal("0.40"),
}

PONDERACIONES_DEFAULT: dict[str, Decimal] = {
    "capacidad_pago": Decimal("0.25"),
    "historial_pago": Decimal("0.25"),
    "endeudamiento": Decimal("0.15"),
    "liquidez_flujo": Decimal("0.15"),
    "antiguedad": Decimal("0.10"),
    "garantias": Decimal("0.05"),
    "macro_sectorial": Decimal("0.05"),
}

REGLAS_FLUJOS_DEFAULT: dict[str, Decimal] = {
    # Flujo rapido
    "rapido_score_aprobacion": Decimal("300"),
    "rapido_endeudamiento_max_pct": Decimal("45"),
    "rapido_antiguedad_min_anios": Decimal("1"),
    # Flujo profundo
    "profundo_dscr_aprobacion_min": Decimal("1.15"),
    "profundo_dscr_rechazo_max": Decimal("1.00"),
    "profundo_dscr_alerta_min": Decimal("1.10"),
    "profundo_dscr_fuerte_min": Decimal("1.30"),
    "profundo_garantia_aprobacion_min_pct": Decimal("80"),
    "profundo_garantia_rechazo_max_pct": Decimal("70"),
    "profundo_garantia_fuerte_min_pct": Decimal("120"),
    "profundo_concentracion_alta_pct": Decimal("60"),
    "profundo_concentracion_baja_pct": Decimal("35"),
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


def _norm_sector(raw: str | None) -> str:
    if not raw:
        return ""
    s = str(raw).strip().lower()
    for ch in ("á", "é", "í", "ó", "ú"):
        s = s.replace(ch, ch[0])
    return s


def _sector_penalty_key(norm: str) -> str:
    if not norm:
        return "default"
    for key in SECTOR_PENALIZACION:
        if key != "default" and key in norm:
            return key
    return "default"


def principal_desde_cuota_maxima(cuota: Decimal, tasa_anual: Decimal, plazo_meses: int) -> Decimal:
    """Principal máximo compatible con una cuota tope (PMT inverso)."""
    m = max(int(plazo_meses), 1)
    c = max(cuota, Decimal("0"))
    if c <= 0:
        return Decimal("0")
    r = (tasa_anual / Decimal("100")) / Decimal("12")
    if r <= 0:
        return (c * Decimal(m)).quantize(Decimal("1"))
    one_plus = Decimal("1") + r
    factor = (one_plus**m - Decimal("1")) / (r * (one_plus**m))
    if factor <= 0:
        return Decimal("0")
    return (c * factor).quantize(Decimal("1"))


def pmt_cuota_mensual(monto: Decimal, tasa_anual: Decimal, plazo_meses: int) -> Decimal:
    """Cuota nivelada (interés compuesto mensual)."""
    m = max(int(plazo_meses), 1)
    principal = max(monto, Decimal("0"))
    if principal <= 0:
        return Decimal("0")
    r = (tasa_anual / Decimal("100")) / Decimal("12")
    if r <= 0:
        return (principal / Decimal(m)).quantize(Decimal("0.01"))
    one_plus = Decimal("1") + r
    num = r * (one_plus ** m)
    den = (one_plus ** m) - Decimal("1")
    if den == 0:
        return (principal / Decimal(m)).quantize(Decimal("0.01"))
    cuota = principal * (num / den)
    return cuota.quantize(Decimal("0.01"))


@dataclass
class MotorCreditoRiesgoResultado:
    score_total: Decimal
    categoria: str
    clasificacion_riesgo: str
    monto_maximo_sugerido: Decimal
    plazo_maximo_sugerido: int
    tasa_sugerida_anual: Decimal
    recomendacion: str
    decision_motor: str
    flujo_evaluacion: str
    explicacion: str
    desglose_json: dict[str, Any]
    macro_json: dict[str, Any]
    stress_cuotas_json: dict[str, Any]
    log_reglas_json: dict[str, Any]
    motivos: list[str] = field(default_factory=list)


def _clasificacion_riesgo(categoria: str) -> str:
    if categoria == "E":
        return "RECHAZADO"
    if categoria == "D":
        return "ALTO"
    if categoria == "C":
        return "MEDIO"
    return "BAJO"


def _categoria_desde_score(score: Decimal) -> str:
    s = float(score)
    if s >= 800:
        return "A"
    if s >= 650:
        return "B"
    if s >= 500:
        return "C"
    if s >= 350:
        return "D"
    return "E"


def _recomendacion(cat: str) -> str:
    if cat == "A":
        return "APROBAR"
    if cat == "B":
        return "CONDICIONES"
    if cat == "C":
        return "COMITE"
    if cat == "D":
        return "COMITE"
    return "RECHAZAR"


def _plazo_max_por_categoria(cat: str) -> int:
    return {"A": 60, "B": 48, "C": 36, "D": 24, "E": 0}[cat]


def _tasa_spread(cat: str) -> Decimal:
    return {"A": Decimal("2.0"), "B": Decimal("3.5"), "C": Decimal("5.5"), "D": Decimal("9.0"), "E": Decimal("15.0")}[cat]


def _macro_ajustes(macro: dict[str, Decimal], motivos: list[str]) -> tuple[Decimal, dict[str, Any]]:
    """
    Devuelve factor 0-1 que escala el subscore macro-sectorial (1 = favorable).
    """
    infl = macro.get("inflacion_anual_pct", MACRO_DEFAULT["inflacion_anual_pct"])
    pib = macro.get("pib_crecimiento_pct", MACRO_DEFAULT["pib_crecimiento_pct"])
    mora_sys = macro.get("morosidad_90_mas_pct", MACRO_DEFAULT["morosidad_90_mas_pct"])
    cartera = macro.get("cartera_deteriorada_pct", MACRO_DEFAULT["cartera_deteriorada_pct"])

    factor = Decimal("1")
    detalle: dict[str, Any] = {}

    if infl > Decimal("4"):
        factor -= Decimal("0.25")
        motivos.append("Inflación elevada (>4%): endurecimiento macro.")
        detalle["inflacion"] = "castigo"
    elif infl < Decimal("2"):
        factor -= Decimal("0.08")
        motivos.append("Inflación baja (<2%): posible bajo dinamismo; prudencia.")
        detalle["inflacion"] = "prudencia_baja_inflacion"
    else:
        detalle["inflacion"] = "normal"

    if pib < Decimal("0"):
        factor -= Decimal("0.35")
        motivos.append("PIB negativo: exigir mayor prudencia / garantías.")
        detalle["pib"] = "negativo"
    elif pib < Decimal("1.5"):
        factor -= Decimal("0.15")
        motivos.append("PIB débil: restricción de apetito.")
        detalle["pib"] = "debil"
    else:
        detalle["pib"] = "favorable"

    if mora_sys > Decimal("2.0"):
        factor -= Decimal("0.12") * min((mora_sys - Decimal("2")) / Decimal("0.5"), Decimal("1"))
        motivos.append("Mora sistémica 90+ días presionada (CMF): entorno más riesgoso.")
    if cartera > Decimal("8"):
        factor -= Decimal("0.08")
        motivos.append("Cartera deteriorada elevada: presión crediticia del sistema.")

    factor = max(factor, Decimal("0.35"))
    return factor, detalle


def evaluar_credito_riesgo(
    *,
    ingreso_mensual: Any,
    gastos_mensual: Any,
    deuda_cuotas_mensual: Any,
    cuota_propuesta: Any,
    monto_solicitado: Any,
    plazo_solicitado: Any,
    tipo_persona: str,
    sector_actividad: str | None,
    mora_max_dias_12m: Any,
    protestos: Any,
    castigos: Any,
    reprogramaciones: Any,
    tipo_contrato: str | None,
    ventas_anual: Any,
    deuda_total: Any,
    patrimonio: Any,
    liquidez_corriente: Any | None,
    flujo_caja_mensual: Any,
    antiguedad_meses_natural: Any,
    anios_operacion_empresa: Any,
    garantia_valor_liquidacion: Any,
    exposicion_usd_pct: Any,
    concentracion_ingresos_pct: Any,
    historial_tributario: str | None,
    flujo_evaluacion: str = "PROFUNDO",
    macro: dict[str, Decimal] | None = None,
    ponderaciones: dict[str, Decimal] | None = None,
    reglas_flujos: dict[str, Decimal] | None = None,
) -> MotorCreditoRiesgoResultado:
    motivos: list[str] = []
    macro_use = {k: macro.get(k, v) if macro else v for k, v in MACRO_DEFAULT.items()}
    pond = ponderaciones or PONDERACIONES_DEFAULT
    reglas = dict(REGLAS_FLUJOS_DEFAULT)
    if reglas_flujos:
        for k, v in reglas_flujos.items():
            try:
                reglas[k] = _d(v, str(REGLAS_FLUJOS_DEFAULT.get(k, Decimal("0"))))
            except Exception:
                continue

    ing = _d(ingreso_mensual)
    gas = _d(gastos_mensual)
    cuotas_ex = _d(deuda_cuotas_mensual)
    cuota_prop = _d(cuota_propuesta)
    monto_sol = _d(monto_solicitado)
    plazo = max(_i(plazo_solicitado, 12), 1)
    ventas = _d(ventas_anual)
    deuda = _d(deuda_total)
    pat = _d(patrimonio)
    liq = liquidez_corriente
    liq_d = _d(liq, "1") if liq is not None else None
    fcf_m = _d(flujo_caja_mensual)
    mora = _i(mora_max_dias_12m, 0)
    prot = _i(protestos, 0)
    cast = _i(castigos, 0)
    reprog = _i(reprogramaciones, 0)
    gar_liq = _d(garantia_valor_liquidacion)
    usd_exp = _d(exposicion_usd_pct)
    conc_ing = _d(concentracion_ingresos_pct)
    hist_trib = (historial_tributario or "SIN_INFO").strip().upper()
    flujo = (flujo_evaluacion or "PROFUNDO").strip().upper()
    if flujo not in {"RAPIDO", "PROFUNDO"}:
        flujo = "PROFUNDO"
    log_reglas: list[dict[str, Any]] = []

    tipo_p = (tipo_persona or "NATURAL").strip().upper()
    ant_meses = _i(antiguedad_meses_natural, 0)
    anios_emp = _i(anios_operacion_empresa, 0)

    # --- Capacidad de pago (0-250) ---
    carga_fin = Decimal("0")
    if ing > 0:
        carga_fin = ((cuotas_ex + cuota_prop) / ing) * Decimal("100")
    excedente = ing - gas - cuotas_ex - cuota_prop

    if carga_fin <= Decimal("25"):
        scap = Decimal("250")
    elif carga_fin <= Decimal("40"):
        scap = Decimal("200")
        motivos.append("Carga financiera en rango medio (25-40%).")
    elif carga_fin <= Decimal("55"):
        scap = Decimal("120")
        motivos.append("Carga financiera alta (40-55%).")
    else:
        scap = Decimal("40")
        motivos.append("Carga financiera crítica (>55%): riesgo de servicio de deuda.")

    if excedente < 0:
        scap = min(scap, Decimal("80"))
        motivos.append("Excedente mensual negativo tras cuota propuesta.")
    log_reglas.append(
        {
            "regla": "capacidad_pago_base",
            "carga_financiera_pct": float(carga_fin),
            "excedente_mensual": float(excedente),
            "subscore": float(scap),
        }
    )

    tpm = macro_use.get("tpm_referencia_anual_pct", Decimal("5.25"))
    cuota_base = pmt_cuota_mensual(monto_sol, tpm, plazo)
    cuota_p2 = pmt_cuota_mensual(monto_sol, tpm + Decimal("2"), plazo)
    cuota_p4 = pmt_cuota_mensual(monto_sol, tpm + Decimal("4"), plazo)
    stress_json = {
        "tpm_referencia_anual_pct": float(tpm),
        "cuota_tpm_pct": float(cuota_base),
        "cuota_tpm_mas_2pct": float(cuota_p2),
        "cuota_tpm_mas_4pct": float(cuota_p4),
    }
    if ing > 0:
        dti_stress4 = ((cuotas_ex + cuota_p4) / ing) * Decimal("100")
        stress_json["carga_financiera_con_tpm_mas_4pct"] = float(dti_stress4)
        if dti_stress4 > Decimal("55"):
            scap -= Decimal("40")
            motivos.append("Estrés de tasa (+4% anual): la carga supera umbral crítico.")

    # --- Historial (0-250) ---
    shist = Decimal("220")
    if mora == 0 and prot == 0 and cast == 0:
        shist = Decimal("250")
        motivos.append("Sin mora declarada ni protestos/castigos: comportamiento favorable.")
    elif mora < 30:
        shist = Decimal("210")
        motivos.append("Mora máxima menor a 30 días: castigo leve.")
    elif mora < 90:
        shist = Decimal("140")
        motivos.append("Mora entre 30 y 90 días: castigo medio en historial.")
    else:
        shist = Decimal("60")
        motivos.append("Mora 90+ días: castigo fuerte en historial.")

    if prot > 0 or cast > 0:
        shist -= Decimal("80") * min(Decimal(str(prot + cast)), Decimal("3"))
        motivos.append("Protestos o castigos registrados: deterioro de confianza.")

    if reprog > 0:
        shist -= Decimal("15") * min(Decimal(str(reprog)), Decimal("4"))
        motivos.append("Reprogramaciones: señal de tensión de pago.")

    shist = max(shist, Decimal("0"))

    # Contrato laboral (personas)
    tc = (tipo_contrato or "").upper()
    if tipo_p == "NATURAL":
        if tc in ("HONORARIOS", "INFORMAL", "BOLETA"):
            shist -= Decimal("25")
            motivos.append("Tipo de ingreso menos estable (honorarios/informal): mayor riesgo.")
        elif tc == "INDEFINIDO":
            motivos.append("Contrato indefinido: menor riesgo laboral percibido.")
    log_reglas.append(
        {
            "regla": "historial_pago_base",
            "mora_max_dias_12m": mora,
            "protestos": prot,
            "castigos": cast,
            "reprogramaciones": reprog,
            "subscore": float(shist),
        }
    )

    # --- Endeudamiento (0-150) ---
    slev = Decimal("120")
    if pat > 0:
        ratio_dp = deuda / pat
        stress_json["deuda_patrimonio"] = float(ratio_dp)
        if ratio_dp <= Decimal("1"):
            slev = Decimal("150")
        elif ratio_dp <= Decimal("2.5"):
            slev = Decimal("110")
            motivos.append("Apalancamiento moderado (deuda/patrimonio).")
        elif ratio_dp <= Decimal("4"):
            slev = Decimal("70")
            motivos.append("Apalancamiento alto.")
        else:
            slev = Decimal("30")
            motivos.append("Apalancamiento crítico (deuda/patrimonio).")
    if ventas > 0:
        dv = deuda / ventas
        stress_json["deuda_ventas_anual"] = float(dv)
        if dv > Decimal("1"):
            slev -= Decimal("30")

    slev = max(min(slev, Decimal("150")), Decimal("0"))
    log_reglas.append(
        {
            "regla": "endeudamiento_base",
            "subscore": float(slev),
        }
    )

    # --- Liquidez / flujo (0-150) ---
    sliq = Decimal("100")
    if liq_d is not None:
        if liq_d > Decimal("1.5"):
            sliq = Decimal("150")
            motivos.append("Liquidez corriente sana (>1,5).")
        elif liq_d >= Decimal("1"):
            sliq = Decimal("115")
            motivos.append("Liquidez corriente aceptable (1,0-1,5).")
        else:
            sliq = Decimal("55")
            motivos.append("Liquidez corriente baja riesgo de caja (<1,0).")
    else:
        if tipo_p == "JURIDICA":
            motivos.append("Liquidez corriente no informada: neutro con prudencia.")
            sliq = Decimal("85")

    cob_deuda = Decimal("0")
    if cuota_prop > 0 and fcf_m > 0:
        cob_deuda = fcf_m / cuota_prop
        stress_json["cobertura_deuda_flujo_mensual"] = float(cob_deuda)
        if cob_deuda < Decimal("1"):
            sliq -= Decimal("40")
            motivos.append("Cobertura de cuota con flujo mensual débil.")
        elif cob_deuda >= Decimal("1.5"):
            sliq += Decimal("10")
            sliq = min(sliq, Decimal("150"))

    sliq = max(min(sliq, Decimal("150")), Decimal("0"))
    log_reglas.append(
        {
            "regla": "liquidez_flujo_base",
            "subscore": float(sliq),
        }
    )

    # --- Antigüedad / estabilidad (0-100) ---
    if tipo_p == "JURIDICA":
        yrs = anios_emp
    else:
        yrs = ant_meses // 12

    if yrs >= 5:
        sant = Decimal("100")
        motivos.append("Antigüedad sólida (5+ años).")
    elif yrs >= 2:
        sant = Decimal("70")
        motivos.append("Antigüedad media (2 a 5 años).")
    elif yrs >= 1:
        sant = Decimal("45")
        motivos.append("Antigüedad corta (1 a 2 años).")
    else:
        sant = Decimal("20")
        motivos.append("Antigüedad muy corta (<1 año): riesgo operativo elevado.")
    log_reglas.append(
        {
            "regla": "antiguedad_base",
            "anios_referencia": int(yrs),
            "subscore": float(sant),
        }
    )

    # --- Garantías (0-50) ---
    sgar = Decimal("25")
    if monto_sol > 0 and gar_liq > 0:
        cov = (gar_liq / monto_sol) * Decimal("100")
        stress_json["cobertura_garantia_liquidacion_pct"] = float(cov)
        if cov >= Decimal("150"):
            sgar = Decimal("50")
            motivos.append("Cobertura de garantía robusta (>150%).")
        elif cov >= Decimal("100"):
            sgar = Decimal("40")
        elif cov >= Decimal("70"):
            sgar = Decimal("25")
            motivos.append("Cobertura de garantía débil (70-100%).")
        else:
            sgar = Decimal("10")
            motivos.append("Cobertura de garantía insuficiente (<70%).")
    log_reglas.append(
        {
            "regla": "garantias_base",
            "subscore": float(sgar),
        }
    )

    # --- Macro + sector (0-50) ---
    macro_factor, macro_det = _macro_ajustes(macro_use, motivos)
    sec_key = _sector_penalty_key(_norm_sector(sector_actividad))
    sec_pen = SECTOR_PENALIZACION.get(sec_key, SECTOR_PENALIZACION["default"])
    stress_json["sector_clave"] = sec_key
    stress_json["sector_penalizacion"] = float(sec_pen)

    base_macro = Decimal("50") * macro_factor * (Decimal("1") - sec_pen * Decimal("0.5"))
    smacro = max(min(base_macro, Decimal("50")), Decimal("0"))
    motivos.append(f"Riesgo sectorial ({sec_key}) ponderado en entorno macro.")

    if usd_exp > Decimal("40"):
        smacro -= Decimal("10")
        motivos.append("Alta exposición USD vs ingresos en CLP: riesgo cambiario.")

    smacro = max(min(smacro, Decimal("50")), Decimal("0"))
    log_reglas.append(
        {
            "regla": "macro_sectorial_base",
            "subscore": float(smacro),
            "sector": sec_key,
        }
    )

    # --- Flujo rápido: reglas simples de aprobación/rechazo ---
    if flujo == "RAPIDO":
        score_comercial = (shist + (slev * Decimal("1.3"))).quantize(Decimal("0.01"))
        regla_endeudamiento_ok = carga_fin <= reglas["rapido_endeudamiento_max_pct"]
        regla_antiguedad_ok = yrs >= int(reglas["rapido_antiguedad_min_anios"])
        decision_rapida = "RECHAZAR"

        if score_comercial >= reglas["rapido_score_aprobacion"] and regla_endeudamiento_ok and regla_antiguedad_ok:
            decision_rapida = "APROBAR"

        log_reglas.append(
            {
                "regla": "flujo_rapido_decision",
                "score_comercial": float(score_comercial),
                "endeudamiento_pct": float(carga_fin),
                "antiguedad_anios": int(yrs),
                "umbral_score_aprobacion": float(reglas["rapido_score_aprobacion"]),
                "umbral_endeudamiento_pct": float(reglas["rapido_endeudamiento_max_pct"]),
                "umbral_antiguedad_min_anios": int(reglas["rapido_antiguedad_min_anios"]),
                "resultado": decision_rapida,
            }
        )

        score = max(Decimal("0"), min((score_comercial / Decimal("400")) * Decimal("1000"), Decimal("1000"))).quantize(Decimal("0.01"))
        cat = _categoria_desde_score(score)
        clasif = _clasificacion_riesgo(cat)
        reco = "APROBAR" if decision_rapida == "APROBAR" else "RECHAZAR"
        decision_motor = decision_rapida

        plazo_max = min(plazo, _plazo_max_por_categoria(cat))
        spread = _tasa_spread(cat)
        tasa_sugerida = (macro_use.get("tpm_referencia_anual_pct", Decimal("5.25")) + spread).quantize(Decimal("0.0001"))
        monto_max = monto_sol if decision_motor == "APROBAR" else Decimal("0")
        if decision_motor != "APROBAR":
            plazo_max = 0

        desglose = {
            "flujo": "RAPIDO",
            "subscores": {
                "score_comercial": float(score_comercial),
                "historial_pago": float(shist),
                "endeudamiento": float(slev),
                "antiguedad": float(sant),
            },
            "carga_financiera_pct": float(carga_fin),
            "categoria": cat,
        }
        macro_json = {k: float(v) for k, v in macro_use.items()}
        macro_json["detalle_reglas"] = macro_det

        expl = (
            f"Flujo RAPIDO ejecutado. Decisión automática: {decision_motor}. "
            f"Score rápido {float(score):.0f}/1000 (categoría {cat})."
        )
        return MotorCreditoRiesgoResultado(
            score_total=score,
            categoria=cat,
            clasificacion_riesgo=clasif,
            monto_maximo_sugerido=monto_max.quantize(Decimal("1")),
            plazo_maximo_sugerido=int(plazo_max),
            tasa_sugerida_anual=tasa_sugerida,
            recomendacion=reco,
            decision_motor=decision_motor,
            flujo_evaluacion="RAPIDO",
            explicacion=expl,
            desglose_json=desglose,
            macro_json=macro_json,
            stress_cuotas_json=stress_json,
            log_reglas_json={"reglas_aplicadas": log_reglas},
            motivos=motivos,
        )

    # Ponderación: cada subscore ya está en su escala máxima (250,250,150,150,100,50,50 = 1000).
    # Los pesos en BD reescalan contribuciones si difieren del estándar.
    w = {k: pond.get(k, PONDERACIONES_DEFAULT[k]) for k in PONDERACIONES_DEFAULT}
    ref = PONDERACIONES_DEFAULT
    score = (
        scap * (w["capacidad_pago"] / ref["capacidad_pago"])
        + shist * (w["historial_pago"] / ref["historial_pago"])
        + slev * (w["endeudamiento"] / ref["endeudamiento"])
        + sliq * (w["liquidez_flujo"] / ref["liquidez_flujo"])
        + sant * (w["antiguedad"] / ref["antiguedad"])
        + sgar * (w["garantias"] / ref["garantias"])
        + smacro * (w["macro_sectorial"] / ref["macro_sectorial"])
    )

    score = max(Decimal("0"), min(score, Decimal("1000"))).quantize(Decimal("0.01"))

    cat = _categoria_desde_score(score)
    clasif = _clasificacion_riesgo(cat)
    reco = _recomendacion(cat)
    if cat == "E":
        reco = "RECHAZAR"

    plazo_max = min(plazo, _plazo_max_por_categoria(cat))
    spread = _tasa_spread(cat)
    tasa_sugerida = tpm + spread + (macro_use["morosidad_90_mas_pct"] - Decimal("2")) * Decimal("0.15")
    tasa_sugerida = max(tasa_sugerida, tpm).quantize(Decimal("0.0001"))

    # Monto máximo sugerido: cupo mensual disponible según DTI objetivo → principal vía PMT inverso.
    dti_obj = {"A": Decimal("0.35"), "B": Decimal("0.30"), "C": Decimal("0.25"), "D": Decimal("0.20"), "E": Decimal("0")}[cat]
    monto_max = Decimal("0")
    if ing > 0 and dti_obj > 0 and cat != "E":
        cup_disp = ing * dti_obj - cuotas_ex
        if cup_disp > 0:
            monto_cap = principal_desde_cuota_maxima(cup_disp * Decimal("0.95"), tasa_sugerida, plazo)
            haircuts = {"A": Decimal("1"), "B": Decimal("1"), "C": Decimal("0.85"), "D": Decimal("0.55")}
            monto_max = min(monto_sol, monto_cap * haircuts.get(cat, Decimal("1")))
        else:
            monto_max = Decimal("0")
    if cat == "E":
        monto_max = Decimal("0")
        plazo_max = 0

    monto_max = max(monto_max, Decimal("0")).quantize(Decimal("1"))

    # Flujo profundo: capacidad de pago + garantías + análisis adicional.
    dscr = Decimal("0")
    if cuota_prop > 0:
        dscr = (fcf_m / cuota_prop).quantize(Decimal("0.0001"))
    stress_json["dscr"] = float(dscr)

    ajuste_profundo = Decimal("0")
    if dscr < reglas["profundo_dscr_alerta_min"]:
        ajuste_profundo -= Decimal("90")
        motivos.append("DSCR insuficiente en flujo profundo.")
    elif dscr >= reglas["profundo_dscr_fuerte_min"]:
        ajuste_profundo += Decimal("30")
        motivos.append("DSCR sólido (>=1.30) en flujo profundo.")

    if conc_ing > reglas["profundo_concentracion_alta_pct"]:
        ajuste_profundo -= Decimal("60")
        motivos.append("Alta concentración de ingresos (>60%).")
    elif conc_ing <= reglas["profundo_concentracion_baja_pct"]:
        ajuste_profundo += Decimal("20")
        motivos.append("Concentración de ingresos diversificada (<=35%).")

    if hist_trib == "OBSERVADO":
        ajuste_profundo -= Decimal("80")
        motivos.append("Historial tributario observado.")
    elif hist_trib == "IRREGULAR":
        ajuste_profundo -= Decimal("140")
        motivos.append("Historial tributario irregular.")
    elif hist_trib == "AL_DIA":
        ajuste_profundo += Decimal("20")
        motivos.append("Historial tributario al día.")

    cobertura_garantia_pct = Decimal("0")
    if monto_sol > 0 and gar_liq > 0:
        cobertura_garantia_pct = (gar_liq / monto_sol) * Decimal("100")
    stress_json["cobertura_garantia_pct"] = float(cobertura_garantia_pct)

    if cobertura_garantia_pct < reglas["profundo_garantia_rechazo_max_pct"]:
        ajuste_profundo -= Decimal("120")
        motivos.append("Garantías insuficientes para flujo profundo.")
    elif cobertura_garantia_pct >= reglas["profundo_garantia_fuerte_min_pct"]:
        ajuste_profundo += Decimal("40")
        motivos.append("Garantías fuertes para flujo profundo.")

    score = max(Decimal("0"), min(score + ajuste_profundo, Decimal("1000"))).quantize(Decimal("0.01"))
    cat = _categoria_desde_score(score)
    clasif = _clasificacion_riesgo(cat)

    decision_motor = "RECHAZAR"
    if dscr >= reglas["profundo_dscr_aprobacion_min"] and cobertura_garantia_pct >= reglas["profundo_garantia_aprobacion_min_pct"] and cat in {"A", "B", "C"}:
        decision_motor = "APROBAR"
    elif cat in {"D", "E"} or dscr < reglas["profundo_dscr_rechazo_max"] or cobertura_garantia_pct < reglas["profundo_garantia_rechazo_max_pct"]:
        decision_motor = "RECHAZAR"
    else:
        decision_motor = "CONDICIONES"

    reco = decision_motor
    log_reglas.append(
        {
            "regla": "flujo_profundo_decision",
            "dscr": float(dscr),
            "concentracion_ingresos_pct": float(conc_ing),
            "historial_tributario": hist_trib,
            "cobertura_garantia_pct": float(cobertura_garantia_pct),
            "umbrales": {k: float(v) for k, v in reglas.items()},
            "decision": decision_motor,
        }
    )

    desglose = {
        "subscores": {
            "capacidad_pago": float(scap),
            "historial_pago": float(shist),
            "endeudamiento": float(slev),
            "liquidez_flujo": float(sliq),
            "antiguedad": float(sant),
            "garantias": float(sgar),
            "macro_sectorial": float(smacro),
        },
        "flujo": "PROFUNDO",
        "analisis_profundo": {
            "dscr": float(dscr),
            "concentracion_ingresos_pct": float(conc_ing),
            "historial_tributario": hist_trib,
            "cobertura_garantia_pct": float(cobertura_garantia_pct),
            "ajuste_profundo_score": float(ajuste_profundo),
        },
        "ponderaciones": {k: float(v) for k, v in w.items()},
        "carga_financiera_pct": float(carga_fin),
        "excedente_mensual": float(excedente),
        "categoria": cat,
    }

    macro_json = {k: float(v) for k, v in macro_use.items()}
    macro_json["detalle_reglas"] = macro_det
    macro_json["fuente_nota"] = "Valores referencia Chile Feb-2026 (BCCh inflación/PIB; CMF mora/cartera). Ajustar en credito_politica."

    expl = (
        f"Flujo PROFUNDO: categoría {cat} (score {float(score):.0f}/1000), riesgo {clasif}. "
        f"Decisión automática: {decision_motor}.\n\nMotivos principales:\n"
        + "\n".join(f"- {m}" for m in motivos[:12])
    )

    return MotorCreditoRiesgoResultado(
        score_total=score,
        categoria=cat,
        clasificacion_riesgo=clasif,
        monto_maximo_sugerido=monto_max,
        plazo_maximo_sugerido=int(plazo_max),
        tasa_sugerida_anual=tasa_sugerida,
        recomendacion=reco,
        decision_motor=decision_motor,
        flujo_evaluacion="PROFUNDO",
        explicacion=expl,
        desglose_json=desglose,
        macro_json=macro_json,
        stress_cuotas_json=stress_json,
        log_reglas_json={"reglas_aplicadas": log_reglas},
        motivos=motivos,
    )


def resultado_a_columnas(r: MotorCreditoRiesgoResultado) -> dict[str, Any]:
    return {
        "score_total": r.score_total,
        "categoria": r.categoria,
        "clasificacion_riesgo": r.clasificacion_riesgo,
        "monto_maximo_sugerido": r.monto_maximo_sugerido,
        "plazo_maximo_sugerido": r.plazo_maximo_sugerido,
        "tasa_sugerida_anual": r.tasa_sugerida_anual,
        "recomendacion": r.recomendacion,
        "decision_motor": r.decision_motor,
        "flujo_evaluacion": r.flujo_evaluacion,
        "explicacion": r.explicacion,
        "desglose_json": r.desglose_json,
        "macro_json": r.macro_json,
        "stress_cuotas_json": r.stress_cuotas_json,
        "log_reglas_json": r.log_reglas_json,
        "motor_version": "v1",
    }
