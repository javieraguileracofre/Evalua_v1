# modules/analytics/lecturas.py
# -*- coding: utf-8 -*-
"""Lecturas de modelos analíticos. No contabilizan ni mueven stock."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

VISTAS = frozenset(
    {
        "analytics_cartera_cxc",
        "analytics_contratos_lop_vigentes",
        "analytics_resultado_mes",
        "analytics_libro_venta",
        "analytics_libro_compra",
    }
)


def leer_vista(db: Session, nombre: str, *, limite: int = 500) -> list[dict]:
    if nombre not in VISTAS:
        raise ValueError("Vista analítica no permitida.")
    tope = max(1, min(int(limite), 2000))
    try:
        rows = db.execute(text(f"SELECT * FROM public.{nombre} LIMIT :tope"), {"tope": tope}).mappings()
    except SQLAlchemyError as exc:
        raise ValueError(
            f"La vista {nombre} no está disponible. Ejecute la migración 0009."
        ) from exc
    return [_jsonable(dict(row)) for row in rows]


def cartera_cxc(db: Session, *, limite: int = 500) -> list[dict]:
    return leer_vista(db, "analytics_cartera_cxc", limite=limite)


def contratos_lop_vigentes(db: Session, *, limite: int = 500) -> list[dict]:
    return leer_vista(db, "analytics_contratos_lop_vigentes", limite=limite)


def resultado_mes(
    db: Session,
    *,
    anio: int | None = None,
    mes: int | None = None,
    limite: int = 500,
) -> list[dict]:
    """Agrega el mayor de un solo mes. Sin año ni mes, usa el mes en curso."""
    hoy = date.today()
    anio_i = int(anio or hoy.year)
    mes_i = int(mes or hoy.month)
    if mes_i < 1 or mes_i > 12:
        raise ValueError("Mes inválido.")
    desde = date(anio_i, mes_i, 1)
    hasta = date(anio_i + 1, 1, 1) if mes_i == 12 else date(anio_i, mes_i + 1, 1)
    tope = max(1, min(int(limite), 2000))
    try:
        rows = db.execute(
            text(
                """
                SELECT
                    CAST(EXTRACT(YEAR FROM a.fecha) AS integer) AS anio,
                    CAST(EXTRACT(MONTH FROM a.fecha) AS integer) AS mes,
                    d.codigo_cuenta,
                    SUM(d.debe) AS debe,
                    SUM(d.haber) AS haber
                FROM public.asientos_contables a
                JOIN public.asientos_detalle d ON d.asiento_id = a.id
                WHERE a.fecha >= :desde
                  AND a.fecha < :hasta
                GROUP BY 1, 2, 3
                ORDER BY 3
                LIMIT :tope
                """
            ),
            {"desde": desde, "hasta": hasta, "tope": tope},
        ).mappings()
    except SQLAlchemyError as exc:
        raise ValueError("No se pudo leer el resultado del mes.") from exc
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
