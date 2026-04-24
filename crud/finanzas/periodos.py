# crud/finanzas/periodos.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def assert_periodo_abierto_para_fecha(db: Session, fecha: datetime | date) -> None:
    """
    Impide registrar asientos en un mes contable cerrado (fin.periodo).

    Usa bloqueo de fila ``FOR UPDATE`` sobre ``fin.periodo`` para el (año, mes) del
    asiento, serializando con cierre/reapertura de período en otras transacciones.

    Comportamiento fail-closed: si no se puede consultar o bloquear ``fin.periodo``,
    se rechaza el asiento (no se asume período abierto ante error).
    """
    if isinstance(fecha, datetime):
        y, m = fecha.year, fecha.month
    else:
        y, m = fecha.year, fecha.month

    params = {"anio": y, "mes": m}
    try:
        # Garantiza fila bajo ``ux_periodo`` para poder aplicar FOR UPDATE (evita
        # validar sin candado si el mes aún no existía en la tabla).
        db.execute(
            text(
                """
                INSERT INTO fin.periodo (anio, mes, estado)
                VALUES (:anio, :mes, 'ABIERTO')
                ON CONFLICT (anio, mes) DO NOTHING
                """
            ),
            params,
        )
        row = db.execute(
            text(
                """
                SELECT
                    id,
                    anio,
                    mes,
                    estado::text AS estado,
                    cerrado_at,
                    cerrado_por,
                    notas,
                    created_at,
                    updated_at
                FROM fin.periodo
                WHERE anio = :anio
                  AND mes = :mes
                FOR UPDATE
                """
            ),
            params,
        ).mappings().first()
    except Exception as exc:
        raise ValueError(
            "No se pudo verificar el estado del período contable en fin.periodo. "
            "Por seguridad no se registrará el asiento hasta corregir el error "
            f"(período solicitado: {y}-{m:02d}). Revise esquema fin, permisos de base de datos o el log del servidor."
        ) from exc

    if not row:
        raise ValueError(
            f"No se encontró el período contable {y}-{m:02d} tras intentar crearlo. "
            "Revise restricciones en fin.periodo."
        )

    if str(row.get("estado", "")).upper() == "CERRADO":
        raise ValueError(
            f"El período contable {y}-{m:02d} está cerrado. "
            "Ábralo desde Cierre mensual o elija otra fecha para el asiento."
        )


def list_periodos(db: Session, limit: int = 60) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT
                id,
                anio,
                mes,
                estado,
                cerrado_at,
                cerrado_por,
                notas,
                created_at,
                updated_at
            FROM fin.periodo
            ORDER BY anio DESC, mes DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_periodo(db: Session, anio: int, mes: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT
                id,
                anio,
                mes,
                estado,
                cerrado_at,
                cerrado_por,
                notas,
                created_at,
                updated_at
            FROM fin.periodo
            WHERE anio = :anio
              AND mes = :mes
            """
        ),
        {"anio": anio, "mes": mes},
    ).mappings().first()

    return dict(row) if row else None


def ensure_periodos_rango(
    db: Session,
    anio_ini: int,
    mes_ini: int,
    anio_fin: int,
    mes_fin: int,
) -> None:
    start = anio_ini * 12 + (mes_ini - 1)
    end = anio_fin * 12 + (mes_fin - 1)

    if end < start:
        start, end = end, start

    for idx in range(start, end + 1):
        anio = idx // 12
        mes = (idx % 12) + 1

        db.execute(
            text(
                """
                INSERT INTO fin.periodo(anio, mes, estado)
                VALUES (:anio, :mes, 'ABIERTO')
                ON CONFLICT (anio, mes) DO NOTHING
                """
            ),
            {"anio": anio, "mes": mes},
        )

    db.commit()


def cerrar_periodo(
    db: Session,
    anio: int,
    mes: int,
    user_email: str,
    notas: str | None = None,
) -> None:
    params = {"anio": anio, "mes": mes, "user_email": user_email, "notas": notas}
    try:
        db.execute(
            text(
                """
                INSERT INTO fin.periodo (anio, mes, estado)
                VALUES (:anio, :mes, 'ABIERTO')
                ON CONFLICT (anio, mes) DO NOTHING
                """
            ),
            params,
        )
        db.execute(
            text(
                """
                SELECT 1
                FROM fin.periodo
                WHERE anio = :anio
                  AND mes = :mes
                FOR UPDATE
                """
            ),
            params,
        )
        db.execute(
            text(
                """
                UPDATE fin.periodo
                SET
                    estado = 'CERRADO',
                    cerrado_at = NOW(),
                    cerrado_por = :user_email,
                    notas = COALESCE(:notas, notas),
                    updated_at = NOW()
                WHERE anio = :anio
                  AND mes = :mes
                """
            ),
            params,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def abrir_periodo(
    db: Session,
    anio: int,
    mes: int,
    user_email: str,
    notas: str | None = None,
) -> None:
    params = {"anio": anio, "mes": mes, "user_email": user_email, "notas": notas}
    try:
        db.execute(
            text(
                """
                INSERT INTO fin.periodo (anio, mes, estado)
                VALUES (:anio, :mes, 'ABIERTO')
                ON CONFLICT (anio, mes) DO NOTHING
                """
            ),
            params,
        )
        db.execute(
            text(
                """
                SELECT 1
                FROM fin.periodo
                WHERE anio = :anio
                  AND mes = :mes
                FOR UPDATE
                """
            ),
            params,
        )
        db.execute(
            text(
                """
                UPDATE fin.periodo
                SET
                    estado = 'ABIERTO',
                    cerrado_at = NULL,
                    cerrado_por = NULL,
                    notas = COALESCE(:notas, notas),
                    updated_at = NOW()
                WHERE anio = :anio
                  AND mes = :mes
                """
            ),
            params,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise