# services/platform/api_idempotency.py
# -*- coding: utf-8 -*-
"""Clave de idempotencia HTTP en la misma transacción de negocio."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class IdempotencyConflict(Exception):
    """La misma clave ya está en curso en otra solicitud."""


class IdempotencyUnavailable(Exception):
    """La tabla aún no fue migrada."""


def _tabla(db: Session) -> bool:
    bind = db.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return False
    return db.execute(text("SELECT to_regclass('fin.api_idempotencia')")).scalar() is not None


def begin(db: Session, *, alcance: str, clave: str) -> dict | None:
    """Reserva la clave. Devuelve el cuerpo ya guardado si la operación terminó."""
    if not _tabla(db):
        raise IdempotencyUnavailable("Falta fin.api_idempotencia. Ejecute la migración 0009.")
    clave_n = (clave or "").strip()
    if not clave_n or len(clave_n) > 80:
        raise ValueError("Idempotency-Key es obligatoria y admite hasta 80 caracteres.")
    alcance_n = (alcance or "").strip()[:40]
    row = db.execute(
        text(
            """
            SELECT estado, cuerpo
            FROM fin.api_idempotencia
            WHERE alcance = :alcance AND clave = :clave
            """
        ),
        {"alcance": alcance_n, "clave": clave_n},
    ).mappings().first()
    if row and row["estado"] == "OK" and row["cuerpo"]:
        return json.loads(row["cuerpo"])
    if row:
        raise IdempotencyConflict()
    try:
        db.execute(
            text(
                """
                INSERT INTO fin.api_idempotencia (alcance, clave, estado)
                VALUES (:alcance, :clave, 'EN_CURSO')
                """
            ),
            {"alcance": alcance_n, "clave": clave_n},
        )
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise IdempotencyConflict() from exc
    return None


def finish(db: Session, *, alcance: str, clave: str, body: dict) -> None:
    """Marca la clave como terminada. El commit lo hace el caso de uso."""
    db.execute(
        text(
            """
            UPDATE fin.api_idempotencia
            SET estado = 'OK', cuerpo = :cuerpo
            WHERE alcance = :alcance AND clave = :clave
            """
        ),
        {
            "alcance": (alcance or "").strip()[:40],
            "clave": (clave or "").strip(),
            "cuerpo": json.dumps(body, ensure_ascii=False),
        },
    )
