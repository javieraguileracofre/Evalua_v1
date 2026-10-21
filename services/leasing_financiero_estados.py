# services/leasing_financiero_estados.py
# -*- coding: utf-8 -*-
"""Estados canónicos del flujo de cotización de leasing financiero (Fase 1)."""
from __future__ import annotations

# Flujo Fase 1 (el activo NO se adquiere al cotizar):
# Borrador → Cotizada → En evaluación → Aprobada → Acuerdo firmado
# → Activo pendiente de compra → Activo adquirido.
ESTADOS_LF_CANONICOS = (
    "BORRADOR",
    "COTIZADA",
    "EN_EVALUACION",
    "APROBADA",
    "ACUERDO_FIRMADO",
    "ACTIVO_PENDIENTE_COMPRA",
    "ACTIVO_ADQUIRIDO",
    "RECHAZADA",
    "ANULADA",
)

ESTADOS_LF_LABELS = {
    "BORRADOR": "Borrador",
    "COTIZADA": "Cotizada",
    "EN_EVALUACION": "En evaluación",
    "EN_ANALISIS_COMERCIAL": "En evaluación",
    "EN_ANALISIS_CREDITO": "En evaluación",
    "APROBADA": "Aprobada",
    "APROBADA_CONDICIONES": "Aprobada",
    "ACUERDO_FIRMADO": "Acuerdo firmado",
    "EN_FORMALIZACION": "Acuerdo firmado",
    "DOCUMENTACION_COMPLETA": "Acuerdo firmado",
    "ACTIVO_PENDIENTE_COMPRA": "Activo pendiente de compra",
    "ACTIVO_ADQUIRIDO": "Activo adquirido",
    "ACTIVADA": "Activo adquirido",
    "VIGENTE": "Activo adquirido",
    "RECHAZADA": "Rechazada",
    "ANULADA": "Anulada",
    "PERDIDA_CLIENTE": "Anulada",
}

# Compatibilidad con operaciones históricas (no se pierden al migrar).
ESTADOS_LF_ALIAS = {
    "EN_ANALISIS_COMERCIAL": "EN_EVALUACION",
    "EN_ANALISIS_CREDITO": "EN_EVALUACION",
    "APROBADA_CONDICIONES": "APROBADA",
    "EN_FORMALIZACION": "ACUERDO_FIRMADO",
    "DOCUMENTACION_COMPLETA": "ACUERDO_FIRMADO",
    "ACTIVADA": "ACTIVO_ADQUIRIDO",
    "VIGENTE": "ACTIVO_ADQUIRIDO",
    "PERDIDA_CLIENTE": "ANULADA",
}

ESTADOS_LF_LEGACY = frozenset(ESTADOS_LF_ALIAS.keys())

ESTADOS_LF = frozenset(ESTADOS_LF_CANONICOS) | ESTADOS_LF_LEGACY

# chk_comercial_lf_estado (parche 109): el rol de la app no puede ALTER.
# Los canónicos de Fase 1 se persisten con el alias permitido más cercano.
ESTADOS_LF_DB_CHECK = frozenset(
    {
        "BORRADOR",
        "COTIZADA",
        "EN_ANALISIS_COMERCIAL",
        "EN_ANALISIS_CREDITO",
        "APROBADA_CONDICIONES",
        "APROBADA",
        "RECHAZADA",
        "EN_FORMALIZACION",
        "DOCUMENTACION_COMPLETA",
        "ACTIVADA",
        "VIGENTE",
        "ANULADA",
        "PERDIDA_CLIENTE",
    }
)

ESTADO_CANONICO_A_DB = {
    "EN_EVALUACION": "EN_ANALISIS_CREDITO",
    "ACUERDO_FIRMADO": "EN_FORMALIZACION",
    "ACTIVO_PENDIENTE_COMPRA": "DOCUMENTACION_COMPLETA",
    "ACTIVO_ADQUIRIDO": "ACTIVADA",
}

ESTADOS_TERMINALES = frozenset({"ACTIVO_ADQUIRIDO", "ACTIVADA", "VIGENTE"})
ESTADOS_NO_EDITABLES = ESTADOS_TERMINALES
ESTADOS_NO_ELIMINABLES = ESTADOS_TERMINALES | frozenset({"ACUERDO_FIRMADO", "ACTIVO_PENDIENTE_COMPRA"})

# Compra/adquisición del activo: solo después del acuerdo firmado.
ESTADOS_PERMITE_COMPRA = frozenset(
    {
        "ACUERDO_FIRMADO",
        "ACTIVO_PENDIENTE_COMPRA",
        "ACTIVO_ADQUIRIDO",
        "EN_FORMALIZACION",
        "DOCUMENTACION_COMPLETA",
        "ACTIVADA",
        "VIGENTE",
    }
)

ESTADOS_ACTIVO_ADQUIRIDO = frozenset({"ACTIVO_ADQUIRIDO", "ACTIVADA", "VIGENTE"})

FLUJO_CANONICO_UI = [
    ("BORRADOR", "Borrador"),
    ("COTIZADA", "Cotizada"),
    ("EN_EVALUACION", "En evaluación"),
    ("APROBADA", "Aprobada"),
    ("ACUERDO_FIRMADO", "Acuerdo firmado"),
    ("ACTIVO_PENDIENTE_COMPRA", "Pendiente de compra"),
    ("ACTIVO_ADQUIRIDO", "Activo adquirido"),
]


def normalizar_estado_lf(value: str | None, *, default: str = "BORRADOR") -> str:
    v = str(value or "").strip().upper()
    if not v:
        return default
    if v in ESTADOS_LF:
        return v
    return default


def estado_canonico(value: str | None) -> str:
    v = str(value or "BORRADOR").strip().upper()
    return ESTADOS_LF_ALIAS.get(v, v if v in ESTADOS_LF else "BORRADOR")


def estado_para_db(value: str | None) -> str:
    """Valor que cumple chk_comercial_lf_estado."""
    canon = estado_canonico(value)
    mapped = ESTADO_CANONICO_A_DB.get(canon, canon)
    if mapped in ESTADOS_LF_DB_CHECK:
        return mapped
    return "BORRADOR"


def estados_equivalentes_db(value: str | None) -> tuple[str, ...]:
    """Valores de columna estado que representan el mismo paso de flujo."""
    canon = estado_canonico(value)
    found = {canon, estado_para_db(canon)}
    found.update(alias for alias, dest in ESTADOS_LF_ALIAS.items() if dest == canon)
    return tuple(sorted(found))


def etiqueta_estado(value: str | None) -> str:
    v = str(value or "").strip().upper()
    return ESTADOS_LF_LABELS.get(v) or ESTADOS_LF_LABELS.get(estado_canonico(v), v or "Borrador")


def puede_editar_cotizacion(estado: str | None) -> bool:
    return estado_canonico(estado) not in {
        "ACTIVO_ADQUIRIDO",
        "ANULADA",
    } and str(estado or "").upper() not in ESTADOS_NO_EDITABLES


def puede_comprar_activo(estado: str | None) -> bool:
    """True solo si el acuerdo ya está firmado (o etapas posteriores)."""
    return str(estado or "").upper() in ESTADOS_PERMITE_COMPRA


def activo_esta_adquirido(estado_cotizacion: str | None, estado_activo: str | None = None) -> bool:
    if str(estado_cotizacion or "").upper() in ESTADOS_ACTIVO_ADQUIRIDO:
        return True
    return str(estado_activo or "").upper() in {"ADQUIRIDO", "COMPRADO", "FACTURADO", "ACTIVADO"}
