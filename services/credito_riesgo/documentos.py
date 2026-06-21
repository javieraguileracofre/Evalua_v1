# services/credito_riesgo/documentos.py
# -*- coding: utf-8 -*-
"""Checklist documental por segmento de cliente."""
from __future__ import annotations

from typing import Any

DOCUMENTOS_DEFAULT: dict[str, Any] = {
    "PYME": [
        "CARPETA_TRIBUTARIA",
        "IVA_F29",
        "BALANCE",
        "CERTIFICADO_DEUDA",
        "ESTADOS_FINANCIEROS",
        "DECLARACION_RENTA",
    ],
    "MEDIANA": [
        "CARPETA_TRIBUTARIA",
        "IVA_F29",
        "BALANCE",
        "ESTADOS_FINANCIEROS",
        "DECLARACION_RENTA",
        "CERTIFICADO_DEUDA",
        "DOCUMENTOS_SOCIETARIOS",
        "GARANTIAS",
    ],
    "GRAN_EMPRESA": [
        "CARPETA_TRIBUTARIA",
        "IVA_F29",
        "BALANCE",
        "ESTADOS_FINANCIEROS",
        "DECLARACION_RENTA",
        "CERTIFICADO_DEUDA",
        "DOCUMENTOS_SOCIETARIOS",
        "GARANTIAS",
        "EEFF_CONSOLIDADOS",
        "COVENANTS",
        "INFORME_DICOM",
    ],
    "labels": {
        "CARPETA_TRIBUTARIA": "Carpeta tributaria SII",
        "IVA_F29": "Formulario IVA F29",
        "BALANCE": "Balance general",
        "ESTADOS_FINANCIEROS": "Estados financieros auditados / firmados",
        "DECLARACION_RENTA": "Declaración de renta (F22)",
        "CERTIFICADO_DEUDA": "Certificado de deuda CMF/SBIF",
        "DOCUMENTOS_SOCIETARIOS": "Extracto / escritura societaria",
        "GARANTIAS": "Documentación de garantías",
        "EEFF_CONSOLIDADOS": "EEFF consolidados grupo",
        "COVENANTS": "Covenants financieros vigentes",
        "INFORME_DICOM": "Informe DICOM / boletín comercial (placeholder)",
    },
}


def tipos_documento_segmento(segmento: str, politica: dict[str, Any] | None = None) -> list[str]:
    pol = {**DOCUMENTOS_DEFAULT, **(politica or {})}
    return list(pol.get(segmento.upper(), pol.get("PYME", [])))


def etiqueta_documento(tipo: str, politica: dict[str, Any] | None = None) -> str:
    pol = {**DOCUMENTOS_DEFAULT, **(politica or {})}
    labels = pol.get("labels", {})
    return str(labels.get(tipo, tipo.replace("_", " ").title()))


def documentos_pendientes(
    documentos_existentes: list[dict[str, Any]],
    segmento: str,
    politica: dict[str, Any] | None = None,
) -> list[str]:
    requeridos = set(tipos_documento_segmento(segmento, politica))
    recibidos = {
        d["tipo_documento"]
        for d in documentos_existentes
        if d.get("estado") in ("RECIBIDO", "VALIDADO")
    }
    return sorted(requeridos - recibidos)
