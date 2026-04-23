# services/finanzas/integracion_ventas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
import logging

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from crud.finanzas.config_contable import obtener_configuracion_evento_modulo
from crud.finanzas.contabilidad_asientos import (
    crear_asiento,
    eliminar_asiento_contable,
    obtener_asiento_detalle,
)
from models import InventarioMovimiento
from models.comercial.nota_venta import NotaVenta


logger = logging.getLogger(__name__)


def _d(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _tipo_documento_desde_nota(nota: NotaVenta) -> str:
    tipo_pago = (nota.tipo_pago or "").strip().upper()
    return "CONTADO" if tipo_pago == "CONTADO" else "CREDITO"


def _codigo_evento_venta_desde_nota(nota: NotaVenta) -> str:
    return "VENTA_CONTADO" if _tipo_documento_desde_nota(nota) == "CONTADO" else "VENTA_CREDITO"


def _codigo_evento_costo_desde_nota(nota: NotaVenta) -> str:
    return "COSTO_VENTA_CONTADO" if _tipo_documento_desde_nota(nota) == "CONTADO" else "COSTO_VENTA_CREDITO"


def _obtener_nota(db: Session, nota_venta_id: int) -> NotaVenta | None:
    stmt = (
        select(NotaVenta)
        .where(NotaVenta.id == nota_venta_id)
        .options(selectinload(NotaVenta.detalles))
    )
    return db.scalar(stmt)


def _obtener_configuracion_venta(db: Session, *, nota: NotaVenta) -> list[dict]:
    return obtener_configuracion_evento_modulo(
        db,
        modulo="VENTAS",
        submodulo="NOTA_VENTA",
        tipo_documento=_tipo_documento_desde_nota(nota),
        codigo_evento=_codigo_evento_venta_desde_nota(nota),
    )


def _obtener_configuracion_costo(db: Session, *, nota: NotaVenta) -> list[dict]:
    return obtener_configuracion_evento_modulo(
        db,
        modulo="VENTAS",
        submodulo="NOTA_VENTA",
        tipo_documento=_tipo_documento_desde_nota(nota),
        codigo_evento=_codigo_evento_costo_desde_nota(nota),
    )


def _descripcion_regla(regla: dict) -> str:
    return " ".join(
        [
            str(regla.get("nombre_evento") or ""),
            str(regla.get("descripcion") or ""),
            str(regla.get("nombre_cuenta") or ""),
            str(regla.get("codigo_cuenta") or ""),
        ]
    ).upper()


def _resolver_monto_regla_venta(
    *,
    regla: dict,
    neto: Decimal,
    iva: Decimal,
    total: Decimal,
) -> Decimal:
    lado = str(regla.get("lado") or "").strip().upper()
    tipo = str(regla.get("tipo") or "").strip().upper()
    clasificacion = str(regla.get("clasificacion") or "").strip().upper()
    texto = _descripcion_regla(regla)

    if "IVA" in texto:
        return iva

    if lado == "DEBE":
        if tipo == "ACTIVO":
            return total
        if clasificacion.startswith("ACTIVO"):
            return total
        if any(token in texto for token in ["CAJA", "BANCO", "CLIENTE", "COBRAR", "CUENTA POR COBRAR"]):
            return total

    if lado == "HABER":
        if tipo == "INGRESO":
            return neto
        if tipo == "PASIVO":
            return iva
        if clasificacion.startswith("PASIVO"):
            return iva

    return Decimal("0.00")


def _resolver_monto_regla_costo(
    *,
    regla: dict,
    costo_total: Decimal,
) -> Decimal:
    lado = str(regla.get("lado") or "").strip().upper()
    tipo = str(regla.get("tipo") or "").strip().upper()
    clasificacion = str(regla.get("clasificacion") or "").strip().upper()
    texto = _descripcion_regla(regla)

    if lado == "DEBE":
        if tipo in {"COSTO", "GASTO"}:
            return costo_total
        if "COSTO" in texto:
            return costo_total

    if lado == "HABER":
        if tipo == "ACTIVO":
            return costo_total
        if clasificacion.startswith("ACTIVO"):
            return costo_total
        if "INVENTARIO" in texto:
            return costo_total

    return Decimal("0.00")


def _construir_detalles_desde_reglas(
    *,
    reglas: list[dict],
    monto_resuelto,
    descripcion: str,
) -> list[dict]:
    detalles: list[dict] = []

    for regla in reglas:
        lado = str(regla.get("lado") or "").strip().upper()
        codigo_cuenta = str(regla.get("codigo_cuenta") or "").strip()
        nombre_cuenta = str(regla.get("nombre_cuenta") or "").strip()

        if not codigo_cuenta:
            continue

        monto = _d(monto_resuelto(regla))
        if monto <= 0:
            continue

        detalles.append(
            {
                "codigo_cuenta": codigo_cuenta,
                "nombre_cuenta": nombre_cuenta,
                "descripcion": descripcion,
                "debe": monto if lado == "DEBE" else Decimal("0.00"),
                "haber": monto if lado == "HABER" else Decimal("0.00"),
            }
        )

    return detalles


def _obtener_costo_total_nota(db: Session, *, nota: NotaVenta) -> Decimal:
    stmt = select(InventarioMovimiento).where(
        InventarioMovimiento.referencia_tipo == "VENTA",
        InventarioMovimiento.referencia_id == nota.id,
    )
    movimientos = list(db.scalars(stmt))

    if movimientos:
        total = sum(
            (_d(mov.cantidad) * _d(mov.costo_unitario)).quantize(Decimal("0.01"))
            for mov in movimientos
        )
        return _d(total).quantize(Decimal("0.01"))

    total_fallback = Decimal("0.00")
    for det in nota.detalles:
        total_fallback += (_d(det.cantidad) * Decimal("0.00")).quantize(Decimal("0.01"))

    return total_fallback.quantize(Decimal("0.01"))


def _existe_asiento(db: Session, *, origen_tipo: str, origen_id: int) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM asientos_contables
            WHERE origen_tipo = :origen_tipo
              AND origen_id = :origen_id
            LIMIT 1
            """
        ),
        {
            "origen_tipo": origen_tipo,
            "origen_id": origen_id,
        },
    ).first()
    return row is not None


def _obtener_id_asiento(db: Session, *, origen_tipo: str, origen_id: int) -> int | None:
    row = db.execute(
        text(
            """
            SELECT id
            FROM asientos_contables
            WHERE origen_tipo = :origen_tipo
              AND origen_id = :origen_id
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {
            "origen_tipo": origen_tipo,
            "origen_id": origen_id,
        },
    ).first()
    return int(row[0]) if row else None


def eliminar_movimiento_contable_nota_venta(
    db: Session,
    *,
    nota_venta_id: int,
) -> int:
    """
    Elimina asientos ligados a una nota de venta:
    - NOTA_VENTA (original)
    - NOTA_VENTA_ANULACION (reversa)
    """
    ids: list[int] = []
    for origen in ("NOTA_VENTA_ANULACION", "NOTA_VENTA"):
        aid = _obtener_id_asiento(db, origen_tipo=origen, origen_id=nota_venta_id)
        if aid:
            ids.append(int(aid))

    eliminados = 0
    for aid in ids:
        eliminar_asiento_contable(db, aid)
        eliminados += 1
    return eliminados


def contabilizar_nota_venta(
    db: Session,
    *,
    nota_venta_id: int,
    usuario: str | None = None,
) -> None:
    nota = _obtener_nota(db, nota_venta_id)
    if not nota:
        raise ValueError("Nota de venta no encontrada.")

    if _existe_asiento(db, origen_tipo="NOTA_VENTA", origen_id=nota.id):
        logger.info("La nota %s ya tiene asiento contable generado.", nota.numero)
        return

    neto = _d(nota.total_neto).quantize(Decimal("0.01"))
    iva = _d(nota.total_iva).quantize(Decimal("0.01"))
    total = _d(nota.total_total).quantize(Decimal("0.01"))
    costo_total = _obtener_costo_total_nota(db, nota=nota).quantize(Decimal("0.01"))

    if total <= 0:
        raise ValueError("La nota de venta no tiene total válido.")

    try:
        reglas_venta = _obtener_configuracion_venta(db, nota=nota)
        if not reglas_venta:
            raise ValueError(
                f"No existe configuración contable para {_codigo_evento_venta_desde_nota(nota)}."
            )

        detalles_venta = _construir_detalles_desde_reglas(
            reglas=reglas_venta,
            monto_resuelto=lambda regla: _resolver_monto_regla_venta(
                regla=regla,
                neto=neto,
                iva=iva,
                total=total,
            ),
            descripcion=f"Venta NV {nota.numero}",
        )

        detalles_costo: list[dict] = []
        if costo_total > 0:
            reglas_costo = _obtener_configuracion_costo(db, nota=nota)
            if not reglas_costo:
                raise ValueError(
                    f"No existe configuración contable para {_codigo_evento_costo_desde_nota(nota)}."
                )

            detalles_costo = _construir_detalles_desde_reglas(
                reglas=reglas_costo,
                monto_resuelto=lambda regla: _resolver_monto_regla_costo(
                    regla=regla,
                    costo_total=costo_total,
                ),
                descripcion=f"Costo venta NV {nota.numero}",
            )

        detalles_asiento = detalles_venta + detalles_costo

        if not detalles_asiento:
            raise ValueError(
                f"No fue posible construir el asiento contable de la nota {nota.numero}."
            )

        crear_asiento(
            db=db,
            fecha=nota.fecha,
            origen_tipo="NOTA_VENTA",
            origen_id=nota.id,
            glosa=f"Venta NV {nota.numero}",
            detalles=detalles_asiento,
            usuario=usuario,
            moneda="CLP",
        )

        logger.info(
            "Asiento contable compuesto generado correctamente para nota de venta %s (id=%s).",
            nota.numero,
            nota.id,
        )

    except SQLAlchemyError as exc:
        logger.exception(
            "No fue posible contabilizar la nota de venta %s (id=%s): %s",
            nota.numero,
            nota.id,
            exc,
        )
        db.rollback()

    except Exception as exc:
        logger.exception(
            "Error inesperado al contabilizar la nota de venta %s (id=%s): %s",
            nota.numero,
            nota.id,
            exc,
        )
        db.rollback()


def contabilizar_anulacion_nota_venta(
    db: Session,
    *,
    nota_venta_id: int,
    usuario: str | None = None,
) -> None:
    nota = _obtener_nota(db, nota_venta_id)
    if not nota:
        raise ValueError("Nota de venta no encontrada.")

    if _existe_asiento(db, origen_tipo="NOTA_VENTA_ANULACION", origen_id=nota.id):
        logger.info("La nota %s ya tiene asiento de anulación.", nota.numero)
        return

    asiento_original_id = _obtener_id_asiento(db, origen_tipo="NOTA_VENTA", origen_id=nota.id)
    if not asiento_original_id:
        logger.warning(
            "La nota %s no tiene asiento original; no se genera reversa contable.",
            nota.numero,
        )
        return

    asiento_original = obtener_asiento_detalle(db, asiento_original_id)
    if not asiento_original:
        logger.warning(
            "No fue posible leer el asiento original de la nota %s.",
            nota.numero,
        )
        return

    detalles_reversa: list[dict] = []
    for det in asiento_original["detalles"]:
        detalles_reversa.append(
            {
                "codigo_cuenta": det["codigo_cuenta"],
                "nombre_cuenta": det["nombre_cuenta"],
                "descripcion": f"Reversa anulación NV {nota.numero}",
                "debe": _d(det["haber"]),
                "haber": _d(det["debe"]),
            }
        )

    if not detalles_reversa:
        logger.warning(
            "La nota %s no tiene detalles contables para reversar.",
            nota.numero,
        )
        return

    try:
        crear_asiento(
            db=db,
            fecha=nota.fecha,
            origen_tipo="NOTA_VENTA_ANULACION",
            origen_id=nota.id,
            glosa=f"Reversa venta NV {nota.numero}",
            detalles=detalles_reversa,
            usuario=usuario,
            moneda="CLP",
        )

        logger.info(
            "Asiento reverso generado correctamente para anulación de nota %s (id=%s).",
            nota.numero,
            nota.id,
        )

    except SQLAlchemyError as exc:
        logger.exception(
            "No fue posible contabilizar la anulación de la nota %s (id=%s): %s",
            nota.numero,
            nota.id,
            exc,
        )
        db.rollback()

    except Exception as exc:
        logger.exception(
            "Error inesperado al contabilizar la anulación de la nota %s (id=%s): %s",
            nota.numero,
            nota.id,
            exc,
        )
        db.rollback()