# services/leasing_operativo/market_benchmarks.py
# -*- coding: utf-8 -*-
"""
Referencias de parametrización LOP basadas en análisis de mercado chileno.

Fuente metodológica (no es cotización en vivo):
  - Mercado secundario de vehículos (Chileautos / Autocosmos / Mercado Libre CL)
  - Práctica comercial de leasing operativo en flotas (plazos 24–48 m)
  - Obsolescencia tecnológica y remarketing de maquinaria
  - Indicadores macro (UF/IPC vía mindicador.cl) como contexto

Los valores son **sugerencias** para que el comercial/admin decida.
No reemplazan tasación ni política de riesgo de la empresa.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.leasing_operativo.market_data import fetch_cl_market_indicators

# Campos del tipo de activo que el usuario puede adoptar desde mercado.
PARAM_KEYS = (
    "residual_base_pct",
    "residual_max_pct",
    "haircut_residual_pct",
    "liquidez_factor",
    "obsolescencia_factor",
    "desgaste_km_factor",
    "desgaste_hora_factor",
)

LABELS_ES = {
    "residual_base_pct": "Residual base %",
    "residual_max_pct": "Residual máx. %",
    "haircut_residual_pct": "Colchón residual %",
    "liquidez_factor": "Liquidez",
    "obsolescencia_factor": "Obsolescencia",
    "desgaste_km_factor": "Desgaste km",
    "desgaste_hora_factor": "Desgaste hora",
}


def _d(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


# Benchmarks por código de catálogo (plazo de referencia ~36 meses).
BENCHMARKS_CL: dict[str, dict[str, Any]] = {
    "CAMIONETA": {
        "nombre_ref": "Camioneta liviana / pickup",
        "sector": "TRANSPORTE",
        "plazo_ref_meses": 36,
        "km_anual_tipico": 80000,
        "confianza": "alta",
        "residual_base_pct": Decimal("22"),
        "residual_max_pct": Decimal("48"),
        "haircut_residual_pct": Decimal("5"),
        "liquidez_factor": Decimal("1.05"),
        "obsolescencia_factor": Decimal("1.02"),
        "desgaste_km_factor": Decimal("0.00015"),
        "desgaste_hora_factor": Decimal("0.00003"),
        "fuentes": [
            "Mercado secundario CL (Chileautos / Autocosmos / ML): pickups de alta rotación (Hilux, Ranger, Amarok).",
            "Flotas comerciales suelen recorrer 60–100 mil km/año; a 36 meses el residual típico de remarketing está en banda 40–55% del valor nuevo en buen estado; para pricing LOP se usa base ~22% con tope ~48%.",
            "Alta liquidez → factor >1; colchón residual moderado (5%).",
        ],
        "decision_hint": "Si su cartera es principalmente 4x4 urbanas con bajo km, puede subir residual base 1–3 pts. Si es faena minera/ruta, baje base y suba colchón.",
    },
    "VEHICULO_PESADO": {
        "nombre_ref": "Vehículo pesado / camión",
        "sector": "TRANSPORTE",
        "plazo_ref_meses": 36,
        "km_anual_tipico": 100000,
        "confianza": "media",
        "residual_base_pct": Decimal("18"),
        "residual_max_pct": Decimal("42"),
        "haircut_residual_pct": Decimal("6"),
        "liquidez_factor": Decimal("0.95"),
        "obsolescencia_factor": Decimal("1.05"),
        "desgaste_km_factor": Decimal("0.00012"),
        "desgaste_hora_factor": Decimal("0.00002"),
        "fuentes": [
            "Segmento camiones/buses en Chile: menor rotación que pickups; compradores flota/minería/logística.",
            "Leasing operativo típico 24–48 meses; residual más conservador por remarketing más lento.",
            "Liquidez <1 y colchón 6% reflejan mayor fricción de venta forzada.",
        ],
        "decision_hint": "Tractos y semirremolques de marcas premium con red de postventa pueden tolerar más residual. Unidades especializadas: baje liquidez y suba colchón.",
    },
    "MAQUINARIA": {
        "nombre_ref": "Maquinaria industrial",
        "sector": "INDUSTRIA",
        "plazo_ref_meses": 36,
        "km_anual_tipico": 0,
        "horas_anual_tipico": 1800,
        "confianza": "media",
        "residual_base_pct": Decimal("15"),
        "residual_max_pct": Decimal("40"),
        "haircut_residual_pct": Decimal("8"),
        "liquidez_factor": Decimal("0.88"),
        "obsolescencia_factor": Decimal("1.08"),
        "desgaste_km_factor": Decimal("0.00005"),
        "desgaste_hora_factor": Decimal("0.0006"),
        "fuentes": [
            "Remarketing de maquinaria en Chile es menos líquido y muy sensible a horas de uso y mantención.",
            "El desgaste se modela sobre horas-motor (no km). Colchón residual más alto (8%).",
            "Plazos LOP habituales más cortos que la vida útil técnica del equipo.",
        ],
        "decision_hint": "Excavadoras/cargadores con horas certificadas y marca con red local: puede subir liquidez hacia 0.95. Equipos importados sin repuestos: baje residual máx.",
    },
    "EQUIPO_IT": {
        "nombre_ref": "Equipos TI / oficina",
        "sector": "TECNOLOGIA",
        "plazo_ref_meses": 24,
        "km_anual_tipico": 0,
        "horas_anual_tipico": 0,
        "confianza": "alta",
        "residual_base_pct": Decimal("8"),
        "residual_max_pct": Decimal("25"),
        "haircut_residual_pct": Decimal("10"),
        "liquidez_factor": Decimal("0.92"),
        "obsolescencia_factor": Decimal("1.15"),
        "desgaste_km_factor": Decimal("0"),
        "desgaste_hora_factor": Decimal("0.0001"),
        "fuentes": [
            "Ciclo de renovación TI corporativo en Chile ~24–36 meses; valor de reventa cae fuerte tras el 2º año.",
            "Obsolescencia tecnológica es el driver principal (factor 1.15); km no aplica.",
            "Colchón residual alto (10%) por mercado de usados fragmentado y rápido cambio de generación.",
        ],
        "decision_hint": "Notebooks/servidores con buy-back del fabricante: puede bajar colchón a 6–8%. Equipamiento genérico sin canal de recompra: mantenga o suba colchón.",
    },
    "VEHICULO_LIVIANO": {
        "nombre_ref": "Vehículo liviano (sedán / hatch / city)",
        "sector": "TRANSPORTE",
        "plazo_ref_meses": 36,
        "km_anual_tipico": 25000,
        "confianza": "alta",
        "residual_base_pct": Decimal("20"),
        "residual_max_pct": Decimal("45"),
        "haircut_residual_pct": Decimal("5"),
        "liquidez_factor": Decimal("1.04"),
        "obsolescencia_factor": Decimal("1.03"),
        "desgaste_km_factor": Decimal("0.00014"),
        "desgaste_hora_factor": Decimal("0.00002"),
        "fuentes": [
            "Mercado secundario CL muy líquido para autos de pasajeros (Yaris, Rio, Onix, Versa, etc.).",
            "Uso corporativo urbano típico 18–30 mil km/año; residual a 36 meses más estable que flota comercial intensiva.",
            "Liquidez alta; colchón residual 5%.",
        ],
        "decision_hint": "Si cotiza flotas de app / pooling con alto km, baje residual base 2–3 pts. Si es pool urbano de baja rotación, puede subir liquidez.",
    },
    "VEHICULO_GERENCIAL": {
        "nombre_ref": "Vehículos gerenciales",
        "sector": "TRANSPORTE",
        "plazo_ref_meses": 36,
        "km_anual_tipico": 18000,
        "confianza": "media",
        "residual_base_pct": Decimal("24"),
        "residual_max_pct": Decimal("52"),
        "haircut_residual_pct": Decimal("6"),
        "liquidez_factor": Decimal("1.06"),
        "obsolescencia_factor": Decimal("1.04"),
        "desgaste_km_factor": Decimal("0.00011"),
        "desgaste_hora_factor": Decimal("0.00002"),
        "fuentes": [
            "SUV/sedán premium (RAV4, Tucson, CR-V, Camry, etc.): buena demanda en usados CL si están bien mantencionados.",
            "Km anuales bajos (15–22 mil) sostienen residual más alto; el riesgo es especificación/versión y color de flota.",
            "Colchón 6% por mayor ticket y sensibilidad a reacondicionamiento estético.",
        ],
        "decision_hint": "Marcas con red fuerte y versión tope de gama: puede subir residual máx. Versiones importadas o poco demandadas: suba colchón a 8%.",
    },
    "GRUA": {
        "nombre_ref": "Grúas",
        "sector": "INDUSTRIA",
        "plazo_ref_meses": 36,
        "km_anual_tipico": 0,
        "horas_anual_tipico": 1600,
        "confianza": "media",
        "residual_base_pct": Decimal("14"),
        "residual_max_pct": Decimal("38"),
        "haircut_residual_pct": Decimal("10"),
        "liquidez_factor": Decimal("0.82"),
        "obsolescencia_factor": Decimal("1.10"),
        "desgaste_km_factor": Decimal("0.00002"),
        "desgaste_hora_factor": Decimal("0.00075"),
        "fuentes": [
            "Remarketing de grúas en Chile es especializado (torre, móvil, pluma); compradores acotados.",
            "El valor depende de horas, certificaciones y capacidad de carga; liquidez baja → colchón 10%.",
            "Desgaste se modela por horas de operación, no por km.",
        ],
        "decision_hint": "Grúa torre con contrato de obra y certificación vigente: puede subir liquidez hacia 0.90. Equipo sin historial de horas: baje residual base.",
    },
    "FURGON": {
        "nombre_ref": "Furgón / utilitario (Partner, Kangoo, Berlingo…)",
        "sector": "TRANSPORTE",
        "plazo_ref_meses": 36,
        "km_anual_tipico": 45000,
        "confianza": "alta",
        "residual_base_pct": Decimal("18"),
        "residual_max_pct": Decimal("42"),
        "haircut_residual_pct": Decimal("6"),
        "liquidez_factor": Decimal("1.00"),
        "obsolescencia_factor": Decimal("1.04"),
        "desgaste_km_factor": Decimal("0.00016"),
        "desgaste_hora_factor": Decimal("0.00003"),
        "fuentes": [
            "Segmento last-mile / delivery en Chile: Peugeot Partner, Renault Kangoo, Citroën Berlingo, Fiat Fiorino, etc.",
            "Uso intensivo urbano 40–60 mil km/año; carrocería y carga impactan residual más que en pickup.",
            "Liquidez media-alta; colchón 6% por desgaste comercial y configuración de carga.",
        ],
        "decision_hint": "Si la unidad es panel cerrado de flota courier, baje residual 1–2 pts. Versión pasajeros / mixtas con baja carga: puede alinearse a vehículo liviano.",
    },
}


def _match_codigo(codigo: str | None, nombre: str | None = None, sector: str | None = None) -> str | None:
    cod = (codigo or "").strip().upper()
    if cod in BENCHMARKS_CL:
        return cod
    blob = f"{cod} {(nombre or '')} {(sector or '')}".upper()
    # Orden: más específico primero (evitar que CAMIONETA/MAQUINARIA absorban furgón/grúa).
    rules = (
        ("FURGON", ("FURGON", "PARTNER", "KANGOO", "BERLINGO", "DOBLO", "FIORINO", "UTILITARIO")),
        ("VEHICULO_GERENCIAL", ("GERENCIAL", "EJECUTIV", "DIRECTIV", "PREMIUM")),
        ("VEHICULO_LIVIANO", ("VEHICULO_LIVIANO", "SEDAN", "HATCH", "CITYCAR", "AUTOMOVIL", "AUTO ")),
        ("GRUA", ("GRUA", "GRUAS", "PLUMA")),
        ("CAMIONETA", ("CAMIONETA", "PICKUP", "4X4")),
        ("VEHICULO_PESADO", ("PESADO", "CAMION", "BUS", "TRACTO", "SEMI")),
        ("MAQUINARIA", ("MAQUIN", "INDUSTR", "EXCAV", "CARGADOR")),
        ("EQUIPO_IT", ("TI", "IT", "OFICINA", "NOTEBOOK", "SERVIDOR", "TECNO")),
    )
    for key, tokens in rules:
        if any(t in blob for t in tokens):
            return key
    return None


def contexto_mercado_cl() -> dict[str, Any]:
    ind = fetch_cl_market_indicators()
    return {
        "uf_clp": ind.get("uf_clp") or 0,
        "usd_clp": ind.get("usd_clp") or 0,
        "ipc_pct": ind.get("ipc_pct") or 0,
        "fuente_indicadores": ind.get("source") or "fallback",
        "as_of": ind.get("as_of"),
        "metodologia": (
            "Sugerencias construidas con referencias del mercado secundario chileno "
            "(vehículos/flota), práctica de leasing operativo 24–48 meses y obsolescencia por tipo. "
            "Indicadores UF/USD/IPC desde mindicador.cl. Usted decide qué adoptar."
        ),
    }


def sugerencia_mercado(
    *,
    codigo: str | None = None,
    nombre: str | None = None,
    sector: str | None = None,
) -> dict[str, Any] | None:
    key = _match_codigo(codigo, nombre, sector)
    if not key:
        return None
    b = BENCHMARKS_CL[key]
    params = {k: b[k] for k in PARAM_KEYS}
    return {
        "codigo_benchmark": key,
        "nombre_ref": b["nombre_ref"],
        "sector": b.get("sector"),
        "plazo_ref_meses": b.get("plazo_ref_meses"),
        "km_anual_tipico": b.get("km_anual_tipico"),
        "horas_anual_tipico": b.get("horas_anual_tipico"),
        "confianza": b.get("confianza", "media"),
        "fuentes": list(b.get("fuentes") or []),
        "decision_hint": b.get("decision_hint") or "",
        "params": params,
    }


def comparar_tipo_con_mercado(tipo: Any) -> dict[str, Any]:
    """Compara valores actuales del tipo vs sugerencia de mercado."""
    sug = sugerencia_mercado(
        codigo=getattr(tipo, "codigo", None),
        nombre=getattr(tipo, "nombre", None),
        sector=getattr(tipo, "sector", None),
    )
    if not sug:
        return {
            "tiene_sugerencia": False,
            "sugerencia": None,
            "diffs": [],
            "diffs_by_key": {},
            "alineado": False,
        }
    diffs = []
    alineado = True
    for key in PARAM_KEYS:
        actual = _d(getattr(tipo, key, 0))
        sugerido = _d(sug["params"][key])
        delta = actual - sugerido
        same = abs(delta) < Decimal("0.00000001")
        if not same:
            alineado = False
        diffs.append(
            {
                "key": key,
                "label": LABELS_ES.get(key, key),
                "actual": actual,
                "sugerido": sugerido,
                "delta": delta,
                "alineado": same,
            }
        )
    return {
        "tiene_sugerencia": True,
        "sugerencia": sug,
        "diffs": diffs,
        "diffs_by_key": {d["key"]: d for d in diffs},
        "alineado": alineado,
    }


def params_sugeridos_para_aplicar(tipo: Any) -> dict[str, Decimal] | None:
    sug = sugerencia_mercado(
        codigo=getattr(tipo, "codigo", None),
        nombre=getattr(tipo, "nombre", None),
        sector=getattr(tipo, "sector", None),
    )
    if not sug:
        return None
    return dict(sug["params"])
