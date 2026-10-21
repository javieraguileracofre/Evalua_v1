# services/finanzas/diferencia_cambio.py
# -*- coding: utf-8 -*-
"""Revaluación de saldos abiertos en moneda distinta de CLP.

Una fila por documento y periodo. El asiento usa origen DIFERENCIA_CAMBIO
con el id de esa fila, así el mismo documento puede revaluarse cada mes
sin repetir el mes ya contabilizado.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from crud.finanzas.config_contable import obtener_configuracion_evento_modulo
from modules.contabilidad import accounting_service

Q2 = Decimal("0.01")


def diferencia_clp(saldo_moneda: Decimal, tc_origen: Decimal, tc_cierre: Decimal) -> Decimal:
    """Positivo: la deuda en CLP sube (pérdida). Negativo: baja (ganancia)."""
    saldo = Decimal(str(saldo_moneda or 0))
    origen = Decimal(str(tc_origen or 0))
    cierre = Decimal(str(tc_cierre or 0))
    return (saldo * (cierre - origen)).quantize(Q2)


def lineas_desde_reglas(reglas: list[dict], diferencia: Decimal) -> list[dict]:
    """La configuración describe la pérdida. Si hay ganancia, se invierten los lados."""
    monto = abs(Decimal(str(diferencia))).quantize(Q2)
    invertir = Decimal(str(diferencia)) < 0
    detalles: list[dict] = []
    for regla in reglas:
        lado = str(regla["lado"]).upper().strip()
        if invertir:
            lado = "HABER" if lado == "DEBE" else "DEBE"
        detalles.append(
            {
                "codigo_cuenta": str(regla["codigo_cuenta"]).strip(),
                "nombre_cuenta": str(regla.get("nombre_cuenta") or regla["codigo_cuenta"]).strip(),
                "descripcion": "Diferencia de cambio",
                "debe": monto if lado == "DEBE" else Decimal("0"),
                "haber": monto if lado == "HABER" else Decimal("0"),
            }
        )
    return detalles


def _tabla(db: Session, nombre: str) -> bool:
    bind = db.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return False
    return db.execute(text("SELECT to_regclass(:nombre)"), {"nombre": nombre}).scalar() is not None


def guardar_tipo_cierre(db: Session, *, anio: int, mes: int, moneda: str, valor: Decimal) -> None:
    if not _tabla(db, "fin.tipo_cambio_cierre"):
        raise ValueError("Falta la tabla de tipos de cierre. Ejecute la migración 0009.")
    codigo = (moneda or "").strip().upper()
    if codigo in {"", "CLP"}:
        raise ValueError("Indique una moneda distinta de CLP.")
    if int(mes) < 1 or int(mes) > 12:
        raise ValueError("Mes inválido.")
    if Decimal(str(valor)) <= 0:
        raise ValueError("El tipo de cambio de cierre debe ser mayor a cero.")
    db.execute(
        text(
            """
            INSERT INTO fin.tipo_cambio_cierre (anio, mes, moneda, valor)
            VALUES (:anio, :mes, :moneda, :valor)
            ON CONFLICT (anio, mes, moneda)
            DO UPDATE SET valor = EXCLUDED.valor
            """
        ),
        {"anio": int(anio), "mes": int(mes), "moneda": codigo, "valor": Decimal(str(valor))},
    )


def revaluar_saldos_periodo(db: Session, *, anio: int, mes: int, usuario: str | None = None) -> list[int]:
    """Revalúa AP abierto en moneda extranjera. No hace commit."""
    if not _tabla(db, "fin.revaluacion_fx"):
        return []

    documentos = db.execute(
        text(
            """
            SELECT id, CAST(moneda AS text) AS moneda, saldo_pendiente, tipo_cambio
            FROM fin.ap_documento
            WHERE CAST(moneda AS text) <> 'CLP'
              AND saldo_pendiente > 0
              AND CAST(estado AS text) <> 'ANULADO'
            ORDER BY id
            """
        )
    ).mappings().all()
    if not documentos:
        return []

    tasas: dict[str, Decimal] = {}
    faltantes: list[str] = []
    for doc in documentos:
        moneda = str(doc["moneda"]).upper()
        if moneda in tasas or moneda in faltantes:
            continue
        tasa = db.execute(
            text(
                """
                SELECT valor
                FROM fin.tipo_cambio_cierre
                WHERE anio = :anio AND mes = :mes AND moneda = :moneda
                """
            ),
            {"anio": int(anio), "mes": int(mes), "moneda": moneda},
        ).scalar()
        if tasa is None:
            faltantes.append(moneda)
        else:
            tasas[moneda] = Decimal(str(tasa))
    if faltantes:
        raise ValueError(
            "Falta tipo de cambio de cierre para "
            + ", ".join(sorted(faltantes))
            + f" en {int(anio):04d}-{int(mes):02d}."
        )

    asientos: list[int] = []
    reglas: list[dict] | None = None
    for doc in documentos:
        existente = db.execute(
            text(
                """
                SELECT id, asiento_id
                FROM fin.revaluacion_fx
                WHERE anio = :anio AND mes = :mes
                  AND documento_tipo = 'AP_DOCUMENTO'
                  AND documento_id = :documento_id
                """
            ),
            {"anio": int(anio), "mes": int(mes), "documento_id": int(doc["id"])},
        ).mappings().first()
        if existente and existente["asiento_id"]:
            asientos.append(int(existente["asiento_id"]))
            continue

        moneda = str(doc["moneda"]).upper()
        delta = diferencia_clp(doc["saldo_pendiente"], doc["tipo_cambio"], tasas[moneda])
        if existente:
            fila_id = int(existente["id"])
        else:
            fila_id = int(
                db.execute(
                    text(
                        """
                        INSERT INTO fin.revaluacion_fx (
                            anio, mes, documento_tipo, documento_id, moneda,
                            saldo_moneda, tc_origen, tc_cierre, diferencia
                        )
                        VALUES (
                            :anio, :mes, 'AP_DOCUMENTO', :documento_id, :moneda,
                            :saldo, :tc_origen, :tc_cierre, :diferencia
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "anio": int(anio),
                        "mes": int(mes),
                        "documento_id": int(doc["id"]),
                        "moneda": moneda,
                        "saldo": Decimal(str(doc["saldo_pendiente"])),
                        "tc_origen": Decimal(str(doc["tipo_cambio"])),
                        "tc_cierre": tasas[moneda],
                        "diferencia": delta,
                    },
                ).scalar()
            )
        if delta == 0:
            continue
        if reglas is None:
            reglas = obtener_configuracion_evento_modulo(
                db,
                modulo="FINANZAS",
                submodulo="CIERRE",
                tipo_documento="DIFERENCIA_CAMBIO",
                codigo_evento="DIFERENCIA_CAMBIO",
            )
            if not reglas:
                raise ValueError(
                    "No existe configuración contable activa para FINANZAS / CIERRE / DIFERENCIA_CAMBIO."
                )
        asiento_id = accounting_service.post_entry(
            db,
            fecha=date(int(anio), int(mes), 1),
            origen_tipo="DIFERENCIA_CAMBIO",
            origen_id=fila_id,
            glosa=f"Diferencia de cambio AP {int(doc['id'])} {int(anio):04d}-{int(mes):02d}"[:255],
            detalles=lineas_desde_reglas(reglas, delta),
            usuario=usuario,
            moneda="CLP",
            do_commit=False,
        )
        db.execute(
            text("UPDATE fin.revaluacion_fx SET asiento_id = :asiento WHERE id = :id"),
            {"asiento": int(asiento_id), "id": fila_id},
        )
        asientos.append(int(asiento_id))
    return asientos
