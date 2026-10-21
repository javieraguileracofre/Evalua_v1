# services/leasing_operativo/politicas_ui.py
# -*- coding: utf-8 -*-
"""Catálogo y helpers de UI para políticas globales LOP (lectura / decisión / edición)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


# Orden de presentación en la pantalla de políticas.
POLITICA_ORDER: tuple[str, ...] = (
    "motor_decision_v1",
    "escenarios_v1",
    "residual_value_v1",
    "costo_fondo_v1",
    "riesgo_base_v1",
    "mora_v1",
    "terminacion_v1",
    "remarketing_v1",
)

ESCENARIO_KEYS: tuple[str, ...] = ("CONSERVADOR", "BASE", "OPTIMISTA", "ESTRES")
ESCENARIO_MULT_KEYS: tuple[str, ...] = (
    "residual_mult",
    "costo_mult",
    "riesgo_mult",
    "tasa_fondo_mult",
)

# Defaults de fábrica (alineados a SQL 102 / 109).
DEFAULTS: dict[str, dict[str, Any]] = {
    "escenarios_v1": {
        "CONSERVADOR": {
            "residual_mult": 0.92,
            "costo_mult": 1.08,
            "riesgo_mult": 1.25,
            "tasa_fondo_mult": 1.12,
        },
        "BASE": {
            "residual_mult": 1.0,
            "costo_mult": 1.0,
            "riesgo_mult": 1.0,
            "tasa_fondo_mult": 1.0,
        },
        "OPTIMISTA": {
            "residual_mult": 1.06,
            "costo_mult": 0.95,
            "riesgo_mult": 0.88,
            "tasa_fondo_mult": 0.95,
        },
        "ESTRES": {
            "residual_mult": 0.82,
            "costo_mult": 1.18,
            "riesgo_mult": 1.45,
            "tasa_fondo_mult": 1.28,
        },
    },
    "motor_decision_v1": {
        "van_minimo": 0,
        "tir_minima_anual_pct": 10,
        "margen_op_minimo_pct": 5,
        "ltv_max_pct": 92,
    },
    "costo_fondo_v1": {
        "costo_deuda_anual_pct": 7.5,
        "costo_capital_anual_pct": 12,
        "peso_deuda": 0.65,
        "peso_capital": 0.35,
        "spread_inversionista_anual_pct": 2.5,
    },
    "riesgo_base_v1": {
        "LGD_base": 0.45,
        "EAD_pct_capex": 1.0,
        "PD_BAJO": 0.012,
        "PD_MEDIO": 0.035,
        "PD_ALTO": 0.09,
        "PD_CRITICO": 0.18,
    },
    "mora_v1": {
        "tasa_mora_mensual_pct": 1.5,
        "tasa_mora_diaria_pct": 0.05,
        "dias_gracia": 5,
        "mora_sobre": "NETO",
        "generar_cxc_mora": True,
    },
    "terminacion_v1": {
        "penalidad_pct_rentas_pendientes": 50,
        "penalidad_pct_capex_remanente": 8,
        "incluir_iva_penalidad": True,
        "requiere_repossession": False,
    },
    "remarketing_v1": {
        "descuento_venta_forzada_pct": 12,
        "costo_repossession_default": 800000,
        "costo_reacondicionamiento_pct": 3,
        "meses_objetivo_venta": 3,
    },
    "residual_value_v1": {
        "model_version": "RV-2026.10.01",
        "market_data_weights": {
            "chileautos": 0.50,
            "mercadolibre": 0.30,
            "yapo": 0.20,
            "autocosmos": 0.0,
        },
        "conservative_factor": 0.90,
        "base_factor": 1.00,
        "optimistic_factor": 1.08,
        "sale_cost_percentage": 2.0,
        "tipo_contrato_default": "ARRENDAMIENTO_OPERATIVO",
        "max_contract_months": 84,
        "max_km_month": 5000,
        "max_km_contract": 250000,
        "residual_min": 0.20,
        "residual_target": 0.45,
        "residual_max": 0.85,
        "deal_thresholds": {
            "minimum_irr": 10,
            "minimum_npv": 0,
            "minimum_margin": 5,
            "residual_min_pct": 25,
            "maximum_residual_risk": 70,
            "ltv_max_pct": 92,
        },
    },
}

CATALOG: dict[str, dict[str, Any]] = {
    "motor_decision_v1": {
        "titulo": "Motor de decisión",
        "grupo": "Pricing y aprobación",
        "icono": "bi-traffic-light",
        "impacto": "Aprueba / rechaza",
        "impacto_tone": "danger",
        "resumen": "Umbrales que el simulador usa para semáforo de viabilidad.",
        "decision_hint": (
            "Subir TIR o margen mínimo endurece la aprobación. "
            "Bajar LTV máximo reduce exposición de capital por operación."
        ),
        "layout": "fields",
        "fields": [
            {
                "key": "van_minimo",
                "label": "VAN mínimo",
                "tipo": "number",
                "step": "1",
                "unidad": "CLP",
                "ayuda": "Valor presente neto mínimo para marcar OK.",
            },
            {
                "key": "tir_minima_anual_pct",
                "label": "TIR mínima anual",
                "tipo": "number",
                "step": "0.1",
                "unidad": "%",
                "ayuda": "Rentabilidad mínima exigida al inversionista.",
            },
            {
                "key": "margen_op_minimo_pct",
                "label": "Margen operacional mínimo",
                "tipo": "number",
                "step": "0.1",
                "unidad": "%",
                "ayuda": "Colchón sobre costos operativos y financieros.",
            },
            {
                "key": "ltv_max_pct",
                "label": "LTV máximo",
                "tipo": "number",
                "step": "0.1",
                "unidad": "%",
                "ayuda": "Tope de financiamiento vs valor del activo.",
            },
        ],
    },
    "escenarios_v1": {
        "titulo": "Escenarios de sensibilidad",
        "grupo": "Pricing y aprobación",
        "icono": "bi-sliders",
        "impacto": "Sensibilidad",
        "impacto_tone": "warning",
        "resumen": "Multiplicadores que estresan residual, costos, riesgo y tasa de fondo.",
        "decision_hint": (
            "BASE = 1,0 en todo. Conservador / estrés suben costos y riesgo; "
            "optimista afloja residual y tasa. Use estrés para stress-test de comité."
        ),
        "layout": "escenarios",
        "fields": [],
    },
    "residual_value_v1": {
        "titulo": "Motor de valor residual",
        "grupo": "Pricing y aprobación",
        "icono": "bi-graph-down-arrow",
        "impacto": "Residual / mercado",
        "impacto_tone": "primary",
        "resumen": "Pesos de portales, factores de escenario y umbrales del deal score.",
        "decision_hint": (
            "Los pesos de Chileautos / Mercado Libre / Yapo deben sumar ~1. "
            "No hardcodear en código: edite aquí. Autocosmos es respaldo auditable (peso 0 por defecto)."
        ),
        "layout": "fields",
        "fields": [
            {
                "key": "model_version",
                "label": "Versión del modelo",
                "tipo": "text",
                "ayuda": "Ej. RV-2026.10.01 — se congela en cada cotización.",
            },
            {
                "key": "conservative_factor",
                "label": "Factor escenario conservador",
                "tipo": "number",
                "step": "0.01",
                "ayuda": "Multiplicador del residual conservador.",
            },
            {
                "key": "base_factor",
                "label": "Factor escenario base",
                "tipo": "number",
                "step": "0.01",
            },
            {
                "key": "optimistic_factor",
                "label": "Factor escenario optimista",
                "tipo": "number",
                "step": "0.01",
            },
            {
                "key": "sale_cost_percentage",
                "label": "Comisión venta %",
                "tipo": "number",
                "step": "0.1",
                "unidad": "%",
            },
            {
                "key": "tipo_contrato_default",
                "label": "Tipo contrato default",
                "tipo": "text",
                "ayuda": "ARRENDAMIENTO_OPERATIVO | LEASING_FINANCIERO | ARRENDAMIENTO_CON_OPCION_COMPRA",
            },
            {
                "key": "max_contract_months",
                "label": "Plazo máximo (meses)",
                "tipo": "number",
                "step": "1",
            },
            {
                "key": "max_km_month",
                "label": "KM máximos / mes",
                "tipo": "number",
                "step": "1",
            },
            {
                "key": "residual_target",
                "label": "Residual objetivo (fracción)",
                "tipo": "number",
                "step": "0.01",
                "ayuda": "Ej. 0.45 = 45% del valor.",
            },
        ],
    },
    "costo_fondo_v1": {
        "titulo": "Costo de fondo (WACC)",
        "grupo": "Pricing y aprobación",
        "icono": "bi-bank",
        "impacto": "Renta / margen",
        "impacto_tone": "primary",
        "resumen": "Costo de deuda y capital que alimenta la tasa mensual efectiva.",
        "decision_hint": (
            "Si el funding real sube, aumente costo de deuda o spread. "
            "Pesos deuda/capital deben sumar ~1,0."
        ),
        "layout": "fields",
        "fields": [
            {
                "key": "costo_deuda_anual_pct",
                "label": "Costo de deuda anual",
                "tipo": "number",
                "step": "0.01",
                "unidad": "%",
                "ayuda": "Kd — costo de pasivos / líneas.",
            },
            {
                "key": "costo_capital_anual_pct",
                "label": "Costo de capital anual",
                "tipo": "number",
                "step": "0.01",
                "unidad": "%",
                "ayuda": "Ke — retorno exigido al patrimonio.",
            },
            {
                "key": "peso_deuda",
                "label": "Peso deuda",
                "tipo": "number",
                "step": "0.01",
                "unidad": "0–1",
                "ayuda": "Participación de deuda en la estructura.",
            },
            {
                "key": "peso_capital",
                "label": "Peso capital",
                "tipo": "number",
                "step": "0.01",
                "unidad": "0–1",
                "ayuda": "Participación de capital propio.",
            },
            {
                "key": "spread_inversionista_anual_pct",
                "label": "Spread inversionista",
                "tipo": "number",
                "step": "0.01",
                "unidad": "%",
                "ayuda": "Prima adicional sobre WACC base.",
            },
        ],
    },
    "riesgo_base_v1": {
        "titulo": "Riesgo crediticio base",
        "grupo": "Riesgo",
        "icono": "bi-shield-exclamation",
        "impacto": "Prima de riesgo",
        "impacto_tone": "warning",
        "resumen": "LGD, EAD y probabilidades de default por banda de riesgo.",
        "decision_hint": (
            "PD más altas o LGD mayor encarecen la renta vía prima de riesgo. "
            "Ajuste solo con respaldo de cartera histórica."
        ),
        "layout": "fields",
        "fields": [
            {
                "key": "LGD_base",
                "label": "LGD base",
                "tipo": "number",
                "step": "0.01",
                "unidad": "0–1",
                "ayuda": "Pérdida dado el default (fracción).",
            },
            {
                "key": "EAD_pct_capex",
                "label": "EAD sobre capex",
                "tipo": "number",
                "step": "0.01",
                "unidad": "fracción",
                "ayuda": "Exposición al default como % del capex financiado.",
            },
            {
                "key": "PD_BAJO",
                "label": "PD riesgo bajo",
                "tipo": "number",
                "step": "0.001",
                "unidad": "0–1",
                "ayuda": "Probabilidad de default anual — banda baja.",
            },
            {
                "key": "PD_MEDIO",
                "label": "PD riesgo medio",
                "tipo": "number",
                "step": "0.001",
                "unidad": "0–1",
                "ayuda": "Banda media (perfil típico).",
            },
            {
                "key": "PD_ALTO",
                "label": "PD riesgo alto",
                "tipo": "number",
                "step": "0.001",
                "unidad": "0–1",
                "ayuda": "Banda alta — mayor prima.",
            },
            {
                "key": "PD_CRITICO",
                "label": "PD riesgo crítico",
                "tipo": "number",
                "step": "0.001",
                "unidad": "0–1",
                "ayuda": "Banda crítica — casi prohibitivo.",
            },
        ],
    },
    "mora_v1": {
        "titulo": "Mora y cobranza",
        "grupo": "Cartera",
        "icono": "bi-cash-coin",
        "impacto": "Cobranza",
        "impacto_tone": "primary",
        "resumen": "Tasas, días de gracia y generación de CxC por mora.",
        "decision_hint": (
            "Más días de gracia suaviza cobranza; tasa diaria más alta castiga atraso. "
            "mora_sobre NETO cobra sobre renta neta."
        ),
        "layout": "fields",
        "fields": [
            {
                "key": "tasa_mora_mensual_pct",
                "label": "Tasa mora mensual",
                "tipo": "number",
                "step": "0.01",
                "unidad": "%",
                "ayuda": "Referencia mensual (informativa / reporting).",
            },
            {
                "key": "tasa_mora_diaria_pct",
                "label": "Tasa mora diaria",
                "tipo": "number",
                "step": "0.001",
                "unidad": "%",
                "ayuda": "Se aplica por día de atraso sobre la base.",
            },
            {
                "key": "dias_gracia",
                "label": "Días de gracia",
                "tipo": "number",
                "step": "1",
                "unidad": "días",
                "ayuda": "Ventana sin intereses moratorios.",
            },
            {
                "key": "mora_sobre",
                "label": "Base de cálculo",
                "tipo": "select",
                "opciones": [
                    {"value": "NETO", "label": "NETO (renta sin IVA)"},
                    {"value": "BRUTO", "label": "BRUTO"},
                ],
                "ayuda": "Sobre qué monto se calcula la mora.",
            },
            {
                "key": "generar_cxc_mora",
                "label": "Generar CxC de mora",
                "tipo": "bool",
                "ayuda": "Si está activo, crea cuenta por cobrar de intereses.",
            },
        ],
    },
    "terminacion_v1": {
        "titulo": "Terminación anticipada",
        "grupo": "Cartera",
        "icono": "bi-file-earmark-break",
        "impacto": "Salida de contrato",
        "impacto_tone": "warning",
        "resumen": "Penalidades al cerrar un contrato antes de plazo.",
        "decision_hint": (
            "Penalidad alta sobre rentas pendientes desincentiva salida temprana; "
            "sobre capex remanente protege el residual no recuperado."
        ),
        "layout": "fields",
        "fields": [
            {
                "key": "penalidad_pct_rentas_pendientes",
                "label": "Penalidad sobre rentas pendientes",
                "tipo": "number",
                "step": "0.1",
                "unidad": "%",
                "ayuda": "% de las rentas aún no facturadas.",
            },
            {
                "key": "penalidad_pct_capex_remanente",
                "label": "Penalidad sobre capex remanente",
                "tipo": "number",
                "step": "0.1",
                "unidad": "%",
                "ayuda": "% del capital aún no recuperado.",
            },
            {
                "key": "incluir_iva_penalidad",
                "label": "Incluir IVA en penalidad",
                "tipo": "bool",
                "ayuda": "Si la liquidación lleva IVA.",
            },
            {
                "key": "requiere_repossession",
                "label": "Exige repossession",
                "tipo": "bool",
                "ayuda": "Fuerza recuperación física del activo al terminar.",
            },
        ],
    },
    "remarketing_v1": {
        "titulo": "Remarketing / recuperación",
        "grupo": "Cartera",
        "icono": "bi-arrow-repeat",
        "impacto": "Valor de salida",
        "impacto_tone": "primary",
        "resumen": "Costos y descuentos al recuperar y vender el activo.",
        "decision_hint": (
            "Mayor descuento de venta forzada baja el recovery; "
            "meses objetivo más cortos asumen mercado líquido."
        ),
        "layout": "fields",
        "fields": [
            {
                "key": "descuento_venta_forzada_pct",
                "label": "Descuento venta forzada",
                "tipo": "number",
                "step": "0.1",
                "unidad": "%",
                "ayuda": "Haircut sobre valor de mercado en liquidación.",
            },
            {
                "key": "costo_repossession_default",
                "label": "Costo repossession default",
                "tipo": "number",
                "step": "1",
                "unidad": "CLP",
                "ayuda": "Costo fijo estimado de recuperación del bien.",
            },
            {
                "key": "costo_reacondicionamiento_pct",
                "label": "Costo reacondicionamiento",
                "tipo": "number",
                "step": "0.1",
                "unidad": "%",
                "ayuda": "% del valor para dejar el activo vendible.",
            },
            {
                "key": "meses_objetivo_venta",
                "label": "Meses objetivo de venta",
                "tipo": "number",
                "step": "1",
                "unidad": "meses",
                "ayuda": "Horizonte esperado de remarketing.",
            },
        ],
    },
}


def defaults_for(clave: str) -> dict[str, Any]:
    return deepcopy(DEFAULTS.get(clave) or {})


def meta_for(clave: str) -> dict[str, Any]:
    base = CATALOG.get(clave)
    if base:
        return base
    return {
        "titulo": clave,
        "grupo": "Otras",
        "icono": "bi-gear",
        "impacto": "Personalizada",
        "impacto_tone": "secondary",
        "resumen": "Política sin catálogo tipado — edite con cuidado.",
        "decision_hint": "No hay guía de negocio para esta clave. Prefiera JSON avanzado solo si conoce el motor.",
        "layout": "json_only",
        "fields": [],
    }


def _to_number(raw: Any, default: float = 0.0) -> float:
    if raw is None:
        return default
    s = str(raw).strip()
    if not s:
        return default
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default


def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    s = str(raw or "").strip().lower()
    return s in {"1", "true", "on", "si", "sí", "yes"}


def parse_form_valor(clave: str, form: Any) -> dict[str, Any]:
    """Construye valor_json desde campos tipados del formulario (o JSON crudo)."""
    mode = str(form.get("edit_mode") or "fields").strip().lower()
    if mode == "json" or meta_for(clave).get("layout") == "json_only":
        import json

        raw = str(form.get("valor_json") or "").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("El JSON de política debe ser un objeto.")
        return data

    meta = meta_for(clave)
    if meta.get("layout") == "escenarios":
        out: dict[str, Any] = {}
        for esc in ESCENARIO_KEYS:
            row: dict[str, Any] = {}
            for mk in ESCENARIO_MULT_KEYS:
                row[mk] = _to_number(form.get(f"esc_{esc}_{mk}"), 1.0)
            out[esc] = row
        return out

    out = {}
    for f in meta.get("fields") or []:
        key = f["key"]
        tipo = f.get("tipo") or "number"
        raw = form.get(key)
        if tipo == "bool":
            out[key] = _to_bool(raw)
        elif tipo == "select" or tipo == "text":
            out[key] = str(raw or "").strip() or str((f.get("opciones") or [{}])[0].get("value") or "")
        else:
            # Enteros conocidos
            if key in {
                "dias_gracia",
                "meses_objetivo_venta",
                "van_minimo",
                "costo_repossession_default",
                "max_contract_months",
                "max_km_month",
                "max_km_contract",
            }:
                out[key] = int(round(_to_number(raw, 0)))
            else:
                out[key] = _to_number(raw, 0.0)
    # Preservar estructuras anidadas no editadas en el formulario tipado
    if clave == "residual_value_v1":
        base = defaults_for(clave)
        base.update(out)
        return base
    return out


def _fmt_kpi(value: Any, *, pct: bool = False, money: bool = False) -> str:
    if value is None or value == "":
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if pct:
        return f"{n:g}%"
    if money:
        return f"${n:,.0f}".replace(",", ".")
    return f"{n:g}"


def build_summary(politicas_by_clave: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    motor = politicas_by_clave.get("motor_decision_v1") or {}
    mora = politicas_by_clave.get("mora_v1") or {}
    fondo = politicas_by_clave.get("costo_fondo_v1") or {}
    term = politicas_by_clave.get("terminacion_v1") or {}
    return [
        {
            "label": "TIR mínima",
            "value": _fmt_kpi(motor.get("tir_minima_anual_pct"), pct=True),
            "hint": "Motor de decisión",
            "clave": "motor_decision_v1",
        },
        {
            "label": "Margen mín.",
            "value": _fmt_kpi(motor.get("margen_op_minimo_pct"), pct=True),
            "hint": "Motor de decisión",
            "clave": "motor_decision_v1",
        },
        {
            "label": "LTV máx.",
            "value": _fmt_kpi(motor.get("ltv_max_pct"), pct=True),
            "hint": "Motor de decisión",
            "clave": "motor_decision_v1",
        },
        {
            "label": "Mora diaria",
            "value": _fmt_kpi(mora.get("tasa_mora_diaria_pct"), pct=True),
            "hint": "Cobranza",
            "clave": "mora_v1",
        },
        {
            "label": "Días gracia",
            "value": _fmt_kpi(mora.get("dias_gracia")),
            "hint": "Cobranza",
            "clave": "mora_v1",
        },
        {
            "label": "Costo deuda",
            "value": _fmt_kpi(fondo.get("costo_deuda_anual_pct"), pct=True),
            "hint": "WACC",
            "clave": "costo_fondo_v1",
        },
        {
            "label": "Penalidad rentas",
            "value": _fmt_kpi(term.get("penalidad_pct_rentas_pendientes"), pct=True),
            "hint": "Terminación",
            "clave": "terminacion_v1",
        },
    ]


def diff_vs_defaults(clave: str, valor: dict[str, Any] | None) -> dict[str, Any]:
    """Compara valor actual vs defaults; útil para chip 'modificada'."""
    base = defaults_for(clave)
    cur = valor or {}
    if not base:
        return {"alineado": True, "cambios": 0}
    # comparación superficial (incluye nested escenarios)
    import json

    a = json.dumps(base, sort_keys=True, default=str)
    b = json.dumps(cur, sort_keys=True, default=str)
    alineado = a == b
    return {"alineado": alineado, "cambios": 0 if alineado else 1}


def build_politica_cards(rows: list[Any]) -> list[dict[str, Any]]:
    by_clave = {str(getattr(r, "clave", "")): r for r in rows}
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _card(clave: str, row: Any | None) -> dict[str, Any]:
        meta = meta_for(clave)
        valor = deepcopy(getattr(row, "valor_json", None) or defaults_for(clave) or {})
        if not isinstance(valor, dict):
            valor = {}
        cmp = diff_vs_defaults(clave, valor)
        return {
            "clave": clave,
            "titulo": meta["titulo"],
            "grupo": meta["grupo"],
            "icono": meta["icono"],
            "impacto": meta["impacto"],
            "impacto_tone": meta["impacto_tone"],
            "resumen": meta["resumen"],
            "decision_hint": meta["decision_hint"],
            "layout": meta["layout"],
            "fields": meta.get("fields") or [],
            "valor": valor,
            "descripcion": (getattr(row, "descripcion", None) if row else None) or meta["resumen"],
            "activo": bool(getattr(row, "activo", True)) if row else False,
            "existe": row is not None,
            "updated_at": getattr(row, "updated_at", None) if row else None,
            "alineado_default": cmp["alineado"],
            "escenario_keys": list(ESCENARIO_KEYS),
            "escenario_mult_keys": list(ESCENARIO_MULT_KEYS),
            "escenario_mult_labels": {
                "residual_mult": "Residual",
                "costo_mult": "Costos",
                "riesgo_mult": "Riesgo",
                "tasa_fondo_mult": "Tasa fondo",
            },
            "defaults": defaults_for(clave),
        }

    for clave in POLITICA_ORDER:
        seen.add(clave)
        cards.append(_card(clave, by_clave.get(clave)))

    # Políticas extra no catalogadas
    extras = sorted(k for k in by_clave if k and k not in seen)
    for clave in extras:
        cards.append(_card(clave, by_clave[clave]))

    return cards


def valores_by_clave(rows: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = str(getattr(r, "clave", "") or "")
        v = getattr(r, "valor_json", None)
        if k and isinstance(v, dict):
            out[k] = v
    return out
