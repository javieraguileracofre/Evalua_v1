# services/leasing_financiero_workflow.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from typing import Any

CHECKLIST_DEFINICION: list[dict[str, Any]] = [
    {"codigo": "cliente_validado", "titulo": "Cliente creado y validado", "automatico": True, "bloqueante": True, "orden": 10},
    {"codigo": "direccion_registrada", "titulo": "Dirección registrada", "automatico": True, "bloqueante": True, "orden": 20},
    {"codigo": "activo_ingresado", "titulo": "Activo ingresado", "automatico": True, "bloqueante": True, "orden": 30},
    {"codigo": "cotizacion_calculada", "titulo": "Cotización financiera calculada", "automatico": True, "bloqueante": True, "orden": 40},
    {"codigo": "amortizacion_generada", "titulo": "Tabla de amortización generada", "automatico": True, "bloqueante": True, "orden": 50},
    {"codigo": "credito_aprobado", "titulo": "Análisis de crédito aprobado", "automatico": True, "bloqueante": True, "orden": 60},
    {"codigo": "contrato_generado", "titulo": "Contrato generado", "automatico": False, "bloqueante": True, "orden": 70},
    {"codigo": "contrato_aprobado", "titulo": "Contrato aprobado / firmado", "automatico": False, "bloqueante": True, "orden": 80},
    {"codigo": "orden_compra_generada", "titulo": "Orden de compra generada", "automatico": False, "bloqueante": True, "orden": 90},
    {"codigo": "factura_registrada", "titulo": "Factura de compra registrada", "automatico": False, "bloqueante": True, "orden": 100},
    {"codigo": "validacion_contable", "titulo": "Validaciones contables realizadas", "automatico": False, "bloqueante": True, "orden": 110},
    {"codigo": "aprobacion_contabilizacion", "titulo": "Aprobación para contabilización", "automatico": False, "bloqueante": True, "orden": 120},
    {"codigo": "solicitud_pago", "titulo": "Solicitud de pago al proveedor", "automatico": False, "bloqueante": False, "orden": 130},
]

TRANSICIONES_ESTADO: dict[str, set[str]] = {
    "BORRADOR": {"COTIZADA", "ANULADA"},
    "COTIZADA": {"EN_ANALISIS_COMERCIAL", "EN_ANALISIS_CREDITO", "BORRADOR", "ANULADA"},
    "EN_ANALISIS_COMERCIAL": {"EN_ANALISIS_CREDITO", "COTIZADA", "ANULADA"},
    "EN_ANALISIS_CREDITO": {"APROBADA", "APROBADA_CONDICIONES", "RECHAZADA", "ANULADA"},
    "APROBADA_CONDICIONES": {"EN_FORMALIZACION", "APROBADA", "ANULADA"},
    "APROBADA": {"EN_FORMALIZACION", "ANULADA"},
    "RECHAZADA": {"EN_ANALISIS_CREDITO", "ANULADA", "PERDIDA_CLIENTE"},
    "EN_FORMALIZACION": {"DOCUMENTACION_COMPLETA", "ANULADA"},
    "DOCUMENTACION_COMPLETA": {"ACTIVADA", "ANULADA"},
    "ACTIVADA": {"VIGENTE", "ANULADA"},
    "VIGENTE": {"ANULADA"},
    "ANULADA": set(),
    "PERDIDA_CLIENTE": set(),
}


def workflow_por_defecto() -> dict[str, Any]:
    return {
        "etapa_actual": "ANALISIS_CREDITO",
        "hitos": {
            "analisis_credito": False,
            "aceptacion_cliente": False,
            "orden_compra": False,
            "contrato_firmado": False,
            "acta_recepcion": False,
            "factura_compra": False,
            "activacion_contable": False,
            "solicitud_pago": False,
        },
        "checklist_documental": {d["codigo"]: False for d in CHECKLIST_DEFINICION},
    }


def merge_workflow(raw: dict | None) -> dict[str, Any]:
    base = workflow_por_defecto()
    if isinstance(raw, dict):
        if raw.get("etapa_actual"):
            base["etapa_actual"] = raw["etapa_actual"]
        for key in ("hitos", "checklist_documental"):
            if isinstance(raw.get(key), dict):
                base[key].update(raw[key])
    return base


def puede_transicionar(estado_actual: str, estado_nuevo: str) -> bool:
    actual = str(estado_actual or "BORRADOR").upper()
    nuevo = str(estado_nuevo or "").upper()
    if actual == nuevo:
        return True
    permitidos = TRANSICIONES_ESTADO.get(actual)
    if permitidos is None:
        return False
    return nuevo in permitidos


def checklist_bloqueantes_pendientes(items: list) -> list:
    return [
        i for i in items
        if getattr(i, "es_bloqueante", True)
        and str(getattr(i, "estado", "PENDIENTE")).upper() not in {"COMPLETADO", "APROBADO"}
    ]


def marcar_checklist_item(
    items: list,
    codigo: str,
    *,
    estado: str = "COMPLETADO",
    responsable: str | None = None,
    aprobado_por: str | None = None,
    evidencia_ref: str | None = None,
    comentario: str | None = None,
) -> None:
    codigo_norm = str(codigo or "").strip().lower()
    for item in items:
        if str(getattr(item, "codigo", "")).lower() == codigo_norm:
            item.estado = estado
            item.fecha_cumplimiento = datetime.utcnow()
            if responsable:
                item.responsable = responsable
            if aprobado_por:
                item.aprobado_por = aprobado_por
            if evidencia_ref:
                item.evidencia_ref = evidencia_ref
            if comentario:
                item.comentario = comentario
            return


def siguiente_etapa(workflow: dict[str, Any]) -> str:
    hitos = workflow.get("hitos") or {}
    if not hitos.get("analisis_credito"):
        return "ANALISIS_CREDITO"
    if not hitos.get("aceptacion_cliente"):
        return "ACEPTACION_CLIENTE"
    if not hitos.get("orden_compra"):
        return "ORDEN_COMPRA"
    if not hitos.get("contrato_firmado"):
        return "CONTRATO_FIRMADO"
    if not hitos.get("acta_recepcion"):
        return "ACTA_RECEPCION"
    if not hitos.get("factura_compra"):
        return "FACTURA_COMPRA"
    if not hitos.get("activacion_contable"):
        return "ACTIVACION_CONTABLE"
    if not hitos.get("solicitud_pago"):
        return "SOLICITUD_PAGO"
    return "CERRADA"
