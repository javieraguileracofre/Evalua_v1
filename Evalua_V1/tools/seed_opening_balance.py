#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Crea un asiento de apertura (MANUAL_APERTURA) para fijar saldos iniciales en demos.

Uso rápido (ejemplo):
  python tools/seed_opening_balance.py ^
    --tenant athletic ^
    --date 2026-04-01 ^
    --glosa "Apertura inicial demo" ^
    --contra 310101 ^
    --line 110101:144165 ^
    --line 110201:640599 ^
    --line 110201:9258 ^
    --line 110301:271128 ^
    --line 110401:-56045 ^
    --line 110503:180000

Regla de signo:
- Monto positivo => línea al DEBE de esa cuenta.
- Monto negativo => línea al HABER de esa cuenta.

Luego el script agrega una línea de contrapartida en --contra para cuadrar.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from sqlalchemy import text

# Permite ejecutar el script desde tools/ sin instalar paquete.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crud.finanzas.contabilidad_asientos import crear_asiento
from db.session import get_session_local


def _to_decimal(raw: str) -> Decimal:
    try:
        return Decimal(str(raw).strip().replace(".", "").replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Monto inválido: {raw}") from exc


def _parse_line(raw: str) -> tuple[str, Decimal]:
    if ":" not in raw:
        raise ValueError(f"Línea inválida '{raw}'. Formato esperado: CODIGO:MONTO")
    code, amount = raw.split(":", 1)
    code = code.strip()
    if not code:
        raise ValueError(f"Código vacío en línea '{raw}'.")
    return code, _to_decimal(amount)


def _build_detalles(lines: Iterable[tuple[str, Decimal]]) -> tuple[list[dict], Decimal, Decimal]:
    detalles: list[dict] = []
    total_debe = Decimal("0")
    total_haber = Decimal("0")
    for code, monto in lines:
        if monto == 0:
            continue
        if monto > 0:
            debe = monto
            haber = Decimal("0")
            total_debe += debe
        else:
            debe = Decimal("0")
            haber = abs(monto)
            total_haber += haber
        detalles.append(
            {
                "codigo_cuenta": code,
                "descripcion": "Saldo inicial apertura demo",
                "debe": debe,
                "haber": haber,
            }
        )
    return detalles, total_debe, total_haber


def main() -> int:
    ap = argparse.ArgumentParser(description="Semilla de asiento de apertura manual (demo).")
    ap.add_argument("--tenant", default=None, help="Código tenant (default: settings.default_tenant_code).")
    ap.add_argument("--date", required=True, help="Fecha asiento YYYY-MM-DD o YYYY-MM-DDTHH:MM.")
    ap.add_argument("--glosa", default="Apertura inicial demo", help="Glosa del asiento.")
    ap.add_argument("--contra", required=True, help="Cuenta contrapartida para cuadrar (ej. 310101).")
    ap.add_argument(
        "--line",
        action="append",
        default=[],
        help="Línea de saldo inicial CODIGO:MONTO. Repetible.",
    )
    ap.add_argument(
        "--origen-id",
        type=int,
        default=1,
        help="origen_id para MANUAL_APERTURA (default: 1).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Permite crear aunque ya exista MANUAL_APERTURA con ese origen_id.",
    )
    args = ap.parse_args()

    if not args.line:
        raise SystemExit("Debe indicar al menos una --line CODIGO:MONTO")

    fecha = datetime.fromisoformat(args.date.replace("T", " "))
    parsed_lines = [_parse_line(x) for x in args.line]
    detalles, total_debe, total_haber = _build_detalles(parsed_lines)

    if not detalles:
        raise SystemExit("No hay líneas con monto distinto de cero.")

    # Contrapartida automática para cuadrar
    diff = total_debe - total_haber
    if diff > 0:
        # Falta HABER en contrapartida
        detalles.append(
            {
                "codigo_cuenta": args.contra.strip(),
                "descripcion": "Contrapartida apertura",
                "debe": Decimal("0"),
                "haber": diff,
            }
        )
    elif diff < 0:
        # Falta DEBE en contrapartida
        detalles.append(
            {
                "codigo_cuenta": args.contra.strip(),
                "descripcion": "Contrapartida apertura",
                "debe": abs(diff),
                "haber": Decimal("0"),
            }
        )

    SessionLocal = get_session_local(args.tenant)
    db = SessionLocal()
    try:
        if not args.force:
            exists = db.execute(
                text(
                    """
                    SELECT 1
                    FROM asientos_contables
                    WHERE origen_tipo = 'MANUAL_APERTURA'
                      AND origen_id = :oid
                    LIMIT 1
                    """
                ),
                {"oid": args.origen_id},
            ).scalar()
            if exists:
                raise SystemExit(
                    f"Ya existe MANUAL_APERTURA origen_id={args.origen_id}. "
                    "Use --origen-id distinto o --force."
                )

        asiento_id = crear_asiento(
            db,
            fecha=fecha,
            origen_tipo="MANUAL_APERTURA",
            origen_id=args.origen_id,
            glosa=args.glosa[:255],
            detalles=detalles,
            usuario="seed_opening_balance",
            moneda="CLP",
            do_commit=True,
        )
        print(f"OK: asiento apertura creado id={asiento_id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

