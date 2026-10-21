# services/finanzas/documento_tributario.py
# -*- coding: utf-8 -*-
"""Libro interno de compras y ventas.

Vincula folio, montos y asiento. No arma un DTE ni lo transmite a un servicio externo.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

TOL = Decimal("0.02")

_TIPOS = {
    "FACTURA": "FACTURA",
    "FACTURA_EXENTA": "FACTURA_EXENTA",
    "BOLETA": "BOLETA",
    "NC": "NOTA_CREDITO",
    "NOTA_CREDITO": "NOTA_CREDITO",
    "ND": "NOTA_DEBITO",
    "NOTA_DEBITO": "NOTA_DEBITO",
    "GUIA": "GUIA",
    "OTRO": "OTRO",
}


def montos_cuadran(
    neto: Decimal,
    iva: Decimal,
    total: Decimal,
    *,
    exento: Decimal = Decimal("0"),
    otros: Decimal = Decimal("0"),
    tolerancia: Decimal = TOL,
) -> bool:
    base = Decimal(str(neto)) + Decimal(str(exento)) + Decimal(str(iva)) + Decimal(str(otros))
    return abs(base - Decimal(str(total))) <= tolerancia


def normalizar_tipo(tipo: object) -> str:
    raw = getattr(tipo, "value", tipo)
    clave = str(raw or "").strip().upper()
    if clave not in _TIPOS:
        raise ValueError(f"Tipo de documento tributario no soportado: {clave or 'vacío'}.")
    return _TIPOS[clave]


def rut_emisor_empresa() -> str:
    """RUT de la empresa emisora. Se configura con EVALUA_RUT_EMISOR."""
    return (os.environ.get("EVALUA_RUT_EMISOR") or "SIN-CONFIGURAR").strip()[:20] or "SIN-CONFIGURAR"


def tabla_lista(db: Session) -> bool:
    bind = db.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return False
    found = db.execute(text("SELECT to_regclass('fin.documento_tributario')")).scalar()
    return found is not None


def registrar_documento(
    db: Session,
    *,
    direccion: str,
    tipo: object,
    folio: str,
    rut_emisor: str,
    rut_receptor: str,
    razon_social: str,
    fecha_emision: date | datetime,
    neto: Decimal,
    iva: Decimal,
    total: Decimal,
    moneda: str,
    asiento_id: int | None,
    origen_tipo: str,
    origen_id: int,
    exento: Decimal = Decimal("0"),
    otros: Decimal = Decimal("0"),
) -> int | None:
    """Inserta o actualiza el vínculo al asiento. None si la tabla aún no existe."""
    if not tabla_lista(db):
        return None
    lado = (direccion or "").strip().upper()
    if lado not in {"EMITIDO", "RECIBIDO"}:
        raise ValueError("La dirección del documento tributario debe ser EMITIDO o RECIBIDO.")
    if not montos_cuadran(neto, iva, total, exento=exento, otros=otros):
        raise ValueError("El documento tributario no cuadra: neto + exento + IVA + otros debe igualar el total.")
    folio_n = (folio or "").strip()[:40]
    if not folio_n:
        raise ValueError("El documento tributario requiere folio.")
    if isinstance(fecha_emision, datetime):
        fecha_emision = fecha_emision.date()
    neto_libro = (Decimal(str(neto)) + Decimal(str(exento))).quantize(Decimal("0.01"))
    row = db.execute(
        text(
            """
            INSERT INTO fin.documento_tributario (
                direccion, tipo, folio, rut_emisor, rut_receptor, razon_social,
                fecha_emision, neto, iva, total, moneda, asiento_id, origen_tipo, origen_id
            )
            VALUES (
                :direccion, :tipo, :folio, :rut_emisor, :rut_receptor, :razon_social,
                :fecha_emision, :neto, :iva, :total, :moneda, :asiento_id, :origen_tipo, :origen_id
            )
            ON CONFLICT (direccion, tipo, folio, rut_emisor)
            DO UPDATE SET asiento_id = COALESCE(fin.documento_tributario.asiento_id, EXCLUDED.asiento_id)
            RETURNING id
            """
        ),
        {
            "direccion": lado,
            "tipo": normalizar_tipo(tipo),
            "folio": folio_n,
            "rut_emisor": (rut_emisor or "").strip()[:20],
            "rut_receptor": (rut_receptor or "").strip()[:20],
            "razon_social": (razon_social or "").strip()[:180],
            "fecha_emision": fecha_emision,
            "neto": neto_libro,
            "iva": Decimal(str(iva)).quantize(Decimal("0.01")),
            "total": Decimal(str(total)).quantize(Decimal("0.01")),
            "moneda": (moneda or "CLP").strip()[:8] or "CLP",
            "asiento_id": int(asiento_id) if asiento_id else None,
            "origen_tipo": (origen_tipo or "").strip()[:30],
            "origen_id": int(origen_id),
        },
    ).scalar()
    return int(row) if row is not None else None


def registrar_desde_documento_ap(db: Session, documento, proveedor, asiento_id: int | None) -> int | None:
    return registrar_documento(
        db,
        direccion="RECIBIDO",
        tipo=getattr(documento, "tipo", "FACTURA"),
        folio=str(getattr(documento, "folio", "") or ""),
        rut_emisor=str(getattr(proveedor, "rut", "") or ""),
        rut_receptor=rut_emisor_empresa(),
        razon_social=str(getattr(proveedor, "razon_social", "") or ""),
        fecha_emision=getattr(documento, "fecha_emision"),
        neto=getattr(documento, "neto", 0) or 0,
        iva=getattr(documento, "iva", 0) or 0,
        total=getattr(documento, "total", 0) or 0,
        moneda=str(getattr(documento, "moneda", "CLP") or "CLP"),
        asiento_id=asiento_id,
        origen_tipo="AP_DOCUMENTO",
        origen_id=int(documento.id),
        exento=getattr(documento, "exento", 0) or 0,
        otros=getattr(documento, "otros_impuestos", 0) or 0,
    )


def registrar_emitido_nota(db: Session, nota, asiento_id: int | None) -> int | None:
    from models.maestros.cliente import Cliente

    cliente = db.get(Cliente, getattr(nota, "cliente_id", None)) if getattr(nota, "cliente_id", None) else None
    iva = Decimal(str(getattr(nota, "total_iva", 0) or 0))
    tipo = "FACTURA" if iva > 0 else "FACTURA_EXENTA"
    return registrar_documento(
        db,
        direccion="EMITIDO",
        tipo=tipo,
        folio=str(getattr(nota, "numero", "") or ""),
        rut_emisor=rut_emisor_empresa(),
        rut_receptor=str(getattr(cliente, "rut", "") or ""),
        razon_social=str(getattr(cliente, "razon_social", "") or ""),
        fecha_emision=getattr(nota, "fecha"),
        neto=getattr(nota, "total_neto", 0) or 0,
        iva=iva,
        total=getattr(nota, "total_total", 0) or 0,
        moneda="CLP",
        asiento_id=asiento_id,
        origen_tipo="NOTA_VENTA",
        origen_id=int(nota.id),
    )


def listar_libro(db: Session, direccion: str, *, anio: int | None = None, mes: int | None = None) -> list[dict]:
    if not tabla_lista(db):
        return []
    lado = (direccion or "").strip().upper()
    if lado not in {"EMITIDO", "RECIBIDO"}:
        raise ValueError("Libro desconocido.")
    filtros = ["direccion = :direccion"]
    params: dict = {"direccion": lado}
    if anio:
        filtros.append("EXTRACT(YEAR FROM fecha_emision) = :anio")
        params["anio"] = int(anio)
    if mes:
        filtros.append("EXTRACT(MONTH FROM fecha_emision) = :mes")
        params["mes"] = int(mes)
    rows = db.execute(
        text(
            f"""
            SELECT id, direccion, tipo, folio, rut_emisor, rut_receptor, razon_social,
                   fecha_emision, neto, iva, total, moneda, asiento_id, origen_tipo, origen_id
            FROM fin.documento_tributario
            WHERE {' AND '.join(filtros)}
            ORDER BY fecha_emision, folio
            """
        ),
        params,
    ).mappings()
    return [_jsonable(dict(row)) for row in rows]


def _jsonable(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            out[key] = str(value)
        elif isinstance(value, (date, datetime)):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out
