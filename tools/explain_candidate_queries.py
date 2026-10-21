# tools/explain_candidate_queries.py
# -*- coding: utf-8 -*-
"""
EXPLAIN de consultas candidatas. No crea índices.

Si EVALUA_TEST_DATABASE_URL no está definida, sale 0 y no mide nada.
No usa DATABASE_URL operativa.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

# Consultas de lectura. Prohibido incluir DDL.
CANDIDATE_QUERIES: tuple[tuple[str, str], ...] = (
    (
        "asientos por fecha y origen",
        """
        SELECT id, fecha, origen_tipo, origen_id
        FROM asientos_contables
        WHERE fecha >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY fecha DESC, id DESC
        LIMIT 100
        """,
    ),
    (
        "cartera CxC con saldo",
        """
        SELECT id, cliente_id, saldo_pendiente, estado
        FROM cuentas_por_cobrar
        WHERE saldo_pendiente > 0
        ORDER BY fecha_vencimiento
        LIMIT 100
        """,
    ),
    (
        "documentos AP abiertos",
        """
        SELECT id, proveedor_id, folio, total
        FROM fin.ap_documento
        ORDER BY fecha_emision DESC
        LIMIT 100
        """,
    ),
    (
        "contratos LOP por estado",
        """
        SELECT id, estado
        FROM leasing_op_contrato
        WHERE estado IS NOT NULL
        LIMIT 100
        """,
    ),
    (
        "auditoría reciente",
        """
        SELECT id, action, created_at
        FROM auth_audit_event
        ORDER BY id DESC
        LIMIT 100
        """,
    ),
)


def main() -> int:
    joined = "\n".join(sql for _, sql in CANDIDATE_QUERIES).upper()
    if "CREATE INDEX" in joined or "ALTER TABLE" in joined:
        print("FAIL: el catálogo de EXPLAIN no puede contener DDL.", file=sys.stderr)
        return 1

    url = (os.getenv("EVALUA_TEST_DATABASE_URL") or "").strip()
    if not url:
        print(
            "SIN MEDICIÓN: EVALUA_TEST_DATABASE_URL no está definida. "
            "No se creó ningún índice."
        )
        return 0

    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            for name, sql in CANDIDATE_QUERIES:
                print(f"== {name} ==")
                try:
                    rows = conn.execute(text("EXPLAIN " + sql)).all()
                except Exception as exc:
                    print(f"OMITIDA ({type(exc).__name__}: {exc})")
                    continue
                for row in rows:
                    print(row[0])
    finally:
        engine.dispose()
    print("Fin de EXPLAIN. No se aplicó DDL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
