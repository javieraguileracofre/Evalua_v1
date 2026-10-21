# services/finanzas/conciliacion_bancaria.py
# -*- coding: utf-8 -*-
"""Cartola, propuestas por monto y fecha, y confirmación con asiento de diferencia."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from modules.contabilidad import accounting_service

TOL = Decimal("0.01")


def proponer_pares(
    lineas: list[dict],
    movimientos: list[dict],
    *,
    tolerancia_dias: int = 3,
) -> list[dict]:
    """Empareja por valor absoluto y cercanía de fecha. No escribe."""
    usados: set[tuple[str, int]] = set()
    propuestas: list[dict] = []
    for linea in lineas:
        if str(linea.get("estado") or "PENDIENTE").upper() != "PENDIENTE":
            continue
        monto_linea = abs(Decimal(str(linea["monto"])))
        fecha_linea = _fecha(linea["fecha"])
        mejor: tuple[int, dict] | None = None
        for mov in movimientos:
            clave = (str(mov["tipo"]), int(mov["id"]))
            if clave in usados:
                continue
            if abs(abs(Decimal(str(mov["monto"]))) - monto_linea) > TOL:
                continue
            delta = abs((_fecha(mov["fecha"]) - fecha_linea).days)
            if delta > int(tolerancia_dias):
                continue
            if mejor is None or delta < mejor[0]:
                mejor = (delta, mov)
        if mejor is None:
            continue
        mov = mejor[1]
        usados.add((str(mov["tipo"]), int(mov["id"])))
        propuestas.append(
            {
                "linea_id": int(linea["id"]),
                "movimiento_tipo": str(mov["tipo"]),
                "movimiento_id": int(mov["id"]),
                "dias": mejor[0],
                "monto": str(monto_linea.quantize(TOL)),
            }
        )
    return propuestas


def _fecha(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _tabla(db: Session) -> bool:
    bind = db.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return False
    return db.execute(text("SELECT to_regclass('fin.cartola_linea')")).scalar() is not None


def importar_cartola(db: Session, *, nombre: str, lineas: list[dict]) -> int:
    if not _tabla(db):
        raise ValueError("Falta la cartola bancaria. Ejecute la migración 0009.")
    if not lineas:
        raise ValueError("La cartola no trae líneas.")
    cartola_id = db.execute(
        text("INSERT INTO fin.cartola_bancaria (nombre) VALUES (:nombre) RETURNING id"),
        {"nombre": (nombre or "Cartola").strip()[:120] or "Cartola"},
    ).scalar()
    for linea in lineas:
        db.execute(
            text(
                """
                INSERT INTO fin.cartola_linea (cartola_id, fecha, monto, glosa, referencia)
                VALUES (:cartola_id, :fecha, :monto, :glosa, :referencia)
                """
            ),
            {
                "cartola_id": int(cartola_id),
                "fecha": _fecha(linea["fecha"]),
                "monto": Decimal(str(linea["monto"])).quantize(TOL),
                "glosa": str(linea.get("glosa") or "")[:255],
                "referencia": str(linea.get("referencia") or "")[:80],
            },
        )
    db.flush()
    return int(cartola_id)


def proponer_cartola(db: Session, cartola_id: int, *, tolerancia_dias: int = 3) -> list[dict]:
    if not _tabla(db):
        return []
    lineas = [
        dict(row)
        for row in db.execute(
            text(
                """
                SELECT id, fecha, monto, estado
                FROM fin.cartola_linea
                WHERE cartola_id = :id AND estado = 'PENDIENTE'
                ORDER BY fecha, id
                """
            ),
            {"id": int(cartola_id)},
        ).mappings()
    ]
    movimientos = [
        dict(row)
        for row in db.execute(
            text(
                """
                SELECT 'PAGO_CLIENTE' AS tipo, id, fecha_pago AS fecha, monto_pago AS monto
                FROM public.pagos_clientes
                UNION ALL
                SELECT 'AP_PAGO', id, fecha_pago, monto_total
                FROM fin.ap_pago
                WHERE CAST(estado AS text) IN ('APLICADO', 'CONFIRMADO')
                """
            )
        ).mappings()
    ]
    return proponer_pares(lineas, movimientos, tolerancia_dias=tolerancia_dias)


def confirmar_linea(
    db: Session,
    *,
    linea_id: int,
    movimiento_tipo: str,
    movimiento_id: int,
    diferencia: Decimal = Decimal("0"),
    cuenta_debe: str | None = None,
    cuenta_haber: str | None = None,
    usuario: str | None = None,
) -> dict:
    if not _tabla(db):
        raise ValueError("Falta la conciliación bancaria. Ejecute la migración 0009.")
    tipo = (movimiento_tipo or "").strip().upper()
    if tipo not in {"PAGO_CLIENTE", "AP_PAGO"}:
        raise ValueError("El movimiento debe ser PAGO_CLIENTE o AP_PAGO.")
    previa = db.execute(
        text(
            """
            SELECT movimiento_tipo, movimiento_id, asiento_diferencia_id
            FROM fin.conciliacion
            WHERE linea_id = :linea_id
            """
        ),
        {"linea_id": int(linea_id)},
    ).mappings().first()
    if previa:
        return {
            "linea_id": int(linea_id),
            "movimiento_tipo": previa["movimiento_tipo"],
            "movimiento_id": int(previa["movimiento_id"]),
            "asiento_diferencia_id": previa["asiento_diferencia_id"],
            "ya_confirmada": True,
        }

    linea = db.execute(
        text("SELECT id, estado FROM fin.cartola_linea WHERE id = :id"),
        {"id": int(linea_id)},
    ).mappings().first()
    if not linea:
        raise ValueError("Línea de cartola no encontrada.")

    monto = abs(Decimal(str(diferencia or 0))).quantize(TOL)
    asiento_id = None
    if monto > 0:
        debe = (cuenta_debe or "").strip()
        haber = (cuenta_haber or "").strip()
        if not debe or not haber:
            raise ValueError("Indique cuenta_debe y cuenta_haber para registrar la diferencia.")
        asiento_id = accounting_service.post_entry(
            db,
            fecha=date.today(),
            origen_tipo="CONCILIACION_DIF",
            origen_id=int(linea_id),
            glosa=f"Diferencia conciliación línea {int(linea_id)}"[:255],
            detalles=[
                {
                    "codigo_cuenta": debe,
                    "descripcion": "Diferencia de conciliación",
                    "debe": monto,
                    "haber": Decimal("0"),
                },
                {
                    "codigo_cuenta": haber,
                    "descripcion": "Diferencia de conciliación",
                    "debe": Decimal("0"),
                    "haber": monto,
                },
            ],
            usuario=usuario,
            moneda="CLP",
            do_commit=False,
        )
    db.execute(
        text(
            """
            INSERT INTO fin.conciliacion (linea_id, movimiento_tipo, movimiento_id, asiento_diferencia_id)
            VALUES (:linea_id, :tipo, :movimiento_id, :asiento_id)
            """
        ),
        {
            "linea_id": int(linea_id),
            "tipo": tipo,
            "movimiento_id": int(movimiento_id),
            "asiento_id": int(asiento_id) if asiento_id else None,
        },
    )
    db.execute(
        text(
            """
            UPDATE fin.cartola_linea
            SET estado = :estado
            WHERE id = :id
            """
        ),
        {"estado": "DIFERENCIA" if monto > 0 else "CONCILIADA", "id": int(linea_id)},
    )
    return {
        "linea_id": int(linea_id),
        "movimiento_tipo": tipo,
        "movimiento_id": int(movimiento_id),
        "asiento_diferencia_id": int(asiento_id) if asiento_id else None,
        "ya_confirmada": False,
    }
