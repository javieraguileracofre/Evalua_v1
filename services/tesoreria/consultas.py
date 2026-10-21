# services/tesoreria/consultas.py
# -*- coding: utf-8 -*-
"""Lecturas del libro para la pantalla de Tesorería."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from crud.tesoreria import sii as crud_sii

MESES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)

ETIQUETAS_ESTADO = {
    "PENDIENTE": "Pendiente",
    "EN_PROCESO": "En proceso",
    "DESCARGANDO_COMPRAS": "Descargando compras",
    "DESCARGANDO_VENTAS": "Descargando ventas",
    "PROCESANDO_COMPRAS": "Procesando compras",
    "PROCESANDO_VENTAS": "Procesando ventas",
    "IMPORTANDO": "Importando",
    "COMPLETADO": "Completado",
    "COMPLETADO_CON_OBSERVACIONES": "Completado con observaciones",
    "REQUIERE_INTERVENCION_USUARIO": "Requiere su intervención",
    "ERROR": "Error",
}


def etiqueta_periodo(anio: int, mes: int) -> str:
    if 1 <= int(mes) <= 12:
        return f"{MESES[int(mes)]} {int(anio)}"
    return f"{anio}-{mes:02d}"


def formato_clp(value) -> str:
    entero = int(Decimal(str(value or 0)).quantize(Decimal("1")))
    return "$ " + f"{entero:,}".replace(",", ".")


def resumen(db: Session, *, anio: int, mes: int) -> dict:
    if not crud_sii.esquema_listo(db):
        vacio = {"documentos": 0, "neto": formato_clp(0), "iva": formato_clp(0), "total": formato_clp(0)}
        return {"compras": {**vacio, "filas": []}, "ventas": {**vacio, "filas": []}, "listo": False}
    compras = crud_sii.resumen_periodo(db, direccion="RECIBIDO", anio=anio, mes=mes)
    ventas = crud_sii.resumen_periodo(db, direccion="EMITIDO", anio=anio, mes=mes)
    return {
        "listo": True,
        "compras": {**_montos(compras), "filas": _filas(db, "RECIBIDO", anio, mes)},
        "ventas": {**_montos(ventas), "filas": _filas(db, "EMITIDO", anio, mes)},
    }


def vista_ejecucion(row: dict, *, empresa: str, rut: str = "", puede_continuar_flag: bool) -> dict:
    import json

    try:
        pasos = json.loads(row.get("pasos") or "[]")
    except json.JSONDecodeError:
        pasos = []
    estado = str(row.get("estado") or "")
    terminados = {"COMPLETADO", "COMPLETADO_CON_OBSERVACIONES", "ERROR"}
    terminal = estado in terminados or (
        estado == "REQUIERE_INTERVENCION_USUARIO" and not puede_continuar_flag
    )
    return {
        "id": int(row["id"]),
        "estado": estado,
        "estado_label": ETIQUETAS_ESTADO.get(estado, estado),
        "terminal": terminal,
        "pasos": pasos,
        "empresa": empresa,
        "rut": rut,
        "periodo": etiqueta_periodo(int(row["periodo_anio"]), int(row["periodo_mes"])),
        "inicio": _fecha(row.get("inicio_at")),
        "fin": _fecha(row.get("fin_at")),
        "mensaje": row.get("error_publico") or "",
        "puede_continuar": bool(puede_continuar_flag and estado == "REQUIERE_INTERVENCION_USUARIO"),
        "compras": {
            "encontrados": int(row.get("compras_encontrados") or 0),
            "importados": int(row.get("compras_importados") or 0),
            "omitidos": int(row.get("compras_omitidos") or 0),
            "errores": int(row.get("compras_errores") or 0),
        },
        "ventas": {
            "encontrados": int(row.get("ventas_encontrados") or 0),
            "importados": int(row.get("ventas_importados") or 0),
            "omitidos": int(row.get("ventas_omitidos") or 0),
            "errores": int(row.get("ventas_errores") or 0),
        },
    }


def _montos(row: dict) -> dict:
    return {
        "documentos": int(row.get("documentos") or 0),
        "neto": formato_clp(row.get("neto")),
        "iva": formato_clp(row.get("iva")),
        "total": formato_clp(row.get("total")),
    }


def _filas(db: Session, direccion: str, anio: int, mes: int) -> list[dict]:
    salida = []
    for row in crud_sii.listar_documentos(db, direccion=direccion, anio=anio, mes=mes):
        rut = row["rut_emisor"] if direccion == "RECIBIDO" else row["rut_receptor"]
        salida.append(
            {
                "folio": row["folio"],
                "tipo": row["tipo"],
                "rut": rut,
                "razon": row["razon_social"],
                "fecha": row["fecha_emision"].isoformat() if row.get("fecha_emision") else "",
                "neto": formato_clp(row["neto"]),
                "iva": formato_clp(row["iva"]),
                "total": formato_clp(row["total"]),
            }
        )
    return salida


def _fecha(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return ""
