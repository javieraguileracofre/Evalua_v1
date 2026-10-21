# crud/finanzas/contabilidad_asientos.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.domain_errors import AsientoDescuadradoError, AsientoInmutableError
from crud.finanzas import periodos as crud_periodos
from crud.finanzas.plan_cuentas import obtener_plan_cuenta_por_codigo


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal("0")


def _normalize_datetime(value: datetime | date | None) -> datetime:
    if value is None:
        return datetime.utcnow()
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def _table_columns(db: Session, table_name: str, schema: str = "public") -> set[str]:
    """Contrato fijo de la revisión de asientos. No consulta information_schema."""
    del db, schema
    if table_name == "asientos_contables":
        return {
            "id",
            "fecha",
            "origen_tipo",
            "origen_id",
            "glosa",
            "moneda",
            "estado",
            "usuario",
            "fecha_creacion",
            "fecha_actualizacion",
        }
    if table_name == "asientos_detalle":
        return {
            "id",
            "asiento_id",
            "codigo_cuenta",
            "nombre_cuenta",
            "descripcion",
            "debe",
            "haber",
        }
    return set()


def _detalle_exprs(db: Session) -> tuple[str, str]:
    del db
    return "ad.codigo_cuenta", "ad.nombre_cuenta"


def _insert_header_dynamic(
    db: Session,
    *,
    fecha: datetime,
    origen_tipo: str,
    origen_id: int,
    glosa: str,
    usuario: str | None,
    moneda: str,
) -> int:
    now = datetime.utcnow()
    asiento_id = db.execute(
        text(
            """
            INSERT INTO asientos_contables (
                fecha, origen_tipo, origen_id, glosa, moneda, estado,
                usuario, fecha_creacion, fecha_actualizacion
            )
            VALUES (
                :fecha, :origen_tipo, :origen_id, :glosa, :moneda, 'PUBLICADO',
                :usuario, :ahora, :ahora
            )
            RETURNING id
            """
        ),
        {
            "fecha": fecha,
            "origen_tipo": origen_tipo,
            "origen_id": origen_id,
            "glosa": (glosa or "")[:255],
            "moneda": moneda,
            "usuario": usuario,
            "ahora": now,
        },
    ).scalar_one()
    return int(asiento_id)


def _insert_detail_dynamic(
    db: Session,
    *,
    asiento_id: int,
    codigo_cuenta: str,
    nombre_cuenta: str,
    descripcion: str | None,
    debe: Decimal,
    haber: Decimal,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO asientos_detalle (
                asiento_id, codigo_cuenta, nombre_cuenta, descripcion, debe, haber
            )
            VALUES (
                :asiento_id, :codigo_cuenta, :nombre_cuenta, :descripcion, :debe, :haber
            )
            """
        ),
        {
            "asiento_id": asiento_id,
            "codigo_cuenta": codigo_cuenta,
            "nombre_cuenta": nombre_cuenta,
            "descripcion": descripcion,
            "debe": debe,
            "haber": haber,
        },
    )


# Orígenes con a lo sumo un asiento vivo por (origen_tipo, origen_id>0).
ORIGENES_IDEMPOTENTES = frozenset(
    {
        "AP_DOCUMENTO",
        "AP_PAGO",
        "NOTA_VENTA",
        "NOTA_VENTA_ANULACION",
        "PAGO_CLIENTE",
        "LEASING_FIN_ACTIVACION",
        "LOP_ACTIVACION",
        "LOP_FACTURACION",
        "FONDO_RENDIR_ENT",
        "FONDO_RENDIR_LIQ",
        "REMUNERACION_PROVISION",
        "REMUNERACION_PAGO",
        "REV_MANUAL",
        "INVENTARIO_MOV",
        "LOP_DEPRECIACION",
        "AP_DOCUMENTO_REVERSA",
        "NOTA_VENTA_REVERSA",
        "FONDO_RENDIR_ENT_REVERSA",
        "INVENTARIO_SALIDA",
        "DIFERENCIA_CAMBIO",
        "CONCILIACION_DIF",
    }
)


def obtener_asiento_id_por_origen(
    db: Session,
    *,
    origen_tipo: str,
    origen_id: int,
) -> int | None:
    """Devuelve el id del asiento existente para (origen_tipo, origen_id), si hay."""
    if origen_id is None or int(origen_id) <= 0:
        return None
    row = db.execute(
        text(
            """
            SELECT id
            FROM asientos_contables
            WHERE origen_tipo = :ot
              AND origen_id = :oid
            ORDER BY id ASC
            LIMIT 1
            """
        ),
        {"ot": str(origen_tipo or "").strip(), "oid": int(origen_id)},
    ).first()
    if row is None:
        return None
    return int(row[0])


def crear_asiento(
    db: Session,
    *,
    fecha: datetime | date | None,
    origen_tipo: str,
    origen_id: int,
    glosa: str,
    detalles: Sequence[dict],
    usuario: str | None = None,
    moneda: str = "CLP",
    do_commit: bool = True,
    idempotent: bool | None = None,
) -> int:
    if not detalles:
        raise ValueError("El asiento debe tener al menos un detalle.")

    ot = str(origen_tipo or "").strip().upper()
    oid = int(origen_id or 0)
    use_idempotent = (
        bool(idempotent)
        if idempotent is not None
        else (oid > 0 and ot in ORIGENES_IDEMPOTENTES)
    )
    if use_idempotent:
        existing = obtener_asiento_id_por_origen(db, origen_tipo=ot, origen_id=oid)
        if existing is not None:
            return existing

    total_debe = Decimal("0")
    total_haber = Decimal("0")
    fecha_asiento = _normalize_datetime(fecha)

    detalle_normalizado: list[dict[str, Any]] = []

    for item in detalles:
        codigo_cuenta = str(item.get("codigo_cuenta") or "").strip()
        descripcion = item.get("descripcion")
        debe = _to_decimal(item.get("debe"))
        haber = _to_decimal(item.get("haber"))

        if not codigo_cuenta:
            raise ValueError("Cada detalle debe incluir codigo_cuenta.")

        cuenta = obtener_plan_cuenta_por_codigo(db, codigo_cuenta)
        if not cuenta:
            raise ValueError(f"La cuenta {codigo_cuenta} no existe en el plan de cuentas.")
        if str(cuenta.estado).upper() != "ACTIVO":
            raise ValueError(f"La cuenta {codigo_cuenta} está inactiva.")
        if not cuenta.acepta_movimiento:
            raise ValueError(f"La cuenta {codigo_cuenta} no acepta movimiento.")

        if debe < 0 or haber < 0:
            raise ValueError("Debe y haber no pueden ser negativos.")
        if debe == 0 and haber == 0:
            raise ValueError("Cada línea debe tener debe u haber mayor a 0.")
        if debe > 0 and haber > 0:
            raise ValueError("Una línea no puede tener debe y haber simultáneamente.")

        total_debe += debe
        total_haber += haber

        detalle_normalizado.append(
            {
                "codigo_cuenta": cuenta.codigo,
                "nombre_cuenta": cuenta.nombre,
                "descripcion": descripcion,
                "debe": debe,
                "haber": haber,
            }
        )

    if total_debe != total_haber:
        raise AsientoDescuadradoError(
            f"Asiento no cuadra (Debe {total_debe} != Haber {total_haber})"
        )

    try:
        # Bloqueo de período lo más cerca posible del INSERT para no retener
        # fin.periodo FOR UPDATE durante toda la validación de líneas.
        crud_periodos.assert_periodo_abierto_para_fecha(db, fecha_asiento)

        # SAVEPOINT: ante carrera concurrente el índice único puede fallar sin
        # abortar toda la transacción de negocio padre.
        nested = db.begin_nested()
        try:
            asiento_id = _insert_header_dynamic(
                db,
                fecha=fecha_asiento,
                origen_tipo=ot or str(origen_tipo or "").strip(),
                origen_id=oid,
                glosa=glosa,
                usuario=usuario,
                moneda=moneda,
            )

            for item in detalle_normalizado:
                _insert_detail_dynamic(
                    db,
                    asiento_id=asiento_id,
                    codigo_cuenta=item["codigo_cuenta"],
                    nombre_cuenta=item["nombre_cuenta"],
                    descripcion=item["descripcion"],
                    debe=item["debe"],
                    haber=item["haber"],
                )
            nested.commit()
        except IntegrityError:
            nested.rollback()
            if use_idempotent:
                existing = obtener_asiento_id_por_origen(db, origen_tipo=ot, origen_id=oid)
                if existing is not None:
                    if do_commit:
                        db.commit()
                    return existing
            raise

        if do_commit:
            db.commit()
        return asiento_id

    except Exception:
        if do_commit:
            db.rollback()
        raise


def eliminar_asiento_contable(db: Session, asiento_id: int) -> None:
    """Prohibido. El historial contable se corrige con reversión, no con DELETE."""
    raise AsientoInmutableError(
        f"El asiento #{int(asiento_id)} no se elimina. Registre un asiento de reversión."
    )


def archivar_origen_asiento(db: Session, asiento_id: int) -> None:
    """
    Quita la clave viva (origen_tipo, origen_id) sin borrar líneas.

    El asiento queda como ``<tipo>_HIST`` para poder registrar uno nuevo
    del mismo documento (edición de nota de venta).
    """
    if asiento_id <= 0:
        return
    db.execute(
        text(
            """
            UPDATE asientos_contables
            SET origen_tipo = CASE
                WHEN right(COALESCE(origen_tipo, ''), 5) = '_HIST' THEN origen_tipo
                ELSE COALESCE(origen_tipo, 'ASIENTO') || '_HIST'
            END
            WHERE id = :id
            """
        ),
        {"id": int(asiento_id)},
    )


def revertir_asiento_negocio(
    db: Session,
    *,
    asiento_original_id: int,
    origen_tipo: str,
    origen_id: int,
    glosa: str | None = None,
    usuario: str | None = None,
    do_commit: bool = False,
) -> int:
    """Asiento espejo idempotente. No borra el original."""
    ot = str(origen_tipo or "").strip().upper()
    if ot not in ORIGENES_IDEMPOTENTES:
        raise ValueError(f"Origen de reversión no permitido: {ot}")
    data = obtener_asiento_detalle(db, asiento_original_id)
    if not data:
        raise ValueError("Asiento original no encontrado.")

    detalles_invertidos: list[dict[str, Any]] = []
    for d in data["detalles"]:
        detalles_invertidos.append(
            {
                "codigo_cuenta": d.get("codigo_cuenta"),
                "descripcion": d.get("descripcion"),
                "debe": d.get("haber"),
                "haber": d.get("debe"),
            }
        )
    cab = data["cabecera"]
    glosa_final = (glosa or "").strip() or f"Reversión asiento #{asiento_original_id}"
    return crear_asiento(
        db,
        fecha=datetime.utcnow(),
        origen_tipo=ot,
        origen_id=int(origen_id),
        glosa=glosa_final[:255],
        detalles=detalles_invertidos,
        usuario=usuario,
        moneda=str(cab.get("moneda") or "CLP"),
        do_commit=do_commit,
        idempotent=True,
    )


ORIGENES_MANUALES_REVERSIBLES = frozenset({"MANUAL_AJUSTE", "MANUAL_APERTURA"})


def crear_reversion_asiento_manual(
    db: Session,
    *,
    asiento_original_id: int,
    glosa: str | None,
    usuario: str | None = None,
    do_commit: bool = True,
) -> int:
    """
    Crea un asiento espejo (debe/haber intercambiados) ligado al original vía origen_tipo REV_MANUAL.
    Solo permitido para asientos manuales de ajuste o apertura.
    """
    data = obtener_asiento_detalle(db, asiento_original_id)
    if not data:
        raise ValueError("Asiento original no encontrado.")

    cab = data["cabecera"]
    ot = str(cab.get("origen_tipo") or "").upper()
    if ot not in ORIGENES_MANUALES_REVERSIBLES:
        raise ValueError("Solo se pueden revertir asientos manuales (apertura o ajuste).")

    detalles_invertidos: list[dict[str, Any]] = []
    for d in data["detalles"]:
        detalles_invertidos.append(
            {
                "codigo_cuenta": d.get("codigo_cuenta"),
                "descripcion": d.get("descripcion"),
                "debe": d.get("haber"),
                "haber": d.get("debe"),
            }
        )

    glosa_final = (glosa or "").strip() or f"Reversión asiento #{asiento_original_id}"
    return crear_asiento(
        db,
        fecha=datetime.utcnow(),
        origen_tipo="REV_MANUAL",
        origen_id=asiento_original_id,
        glosa=glosa_final[:255],
        detalles=detalles_invertidos,
        usuario=usuario,
        moneda=str(cab.get("moneda") or "CLP"),
        do_commit=do_commit,
        idempotent=True,
    )


def listar_asientos(
    db: Session,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    origen_tipo: str | None = None,
    limit: int = 200,
) -> list[dict]:
    tope = max(1, min(int(limit), 500))
    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": tope}

    if fecha_desde:
        where_parts.append("fecha >= :fecha_desde")
        params["fecha_desde"] = fecha_desde

    if fecha_hasta:
        where_parts.append("fecha <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta

    if origen_tipo:
        where_parts.append("origen_tipo = :origen_tipo")
        params["origen_tipo"] = origen_tipo

    query = text(
        f"""
        SELECT
            id,
            fecha,
            glosa,
            origen_tipo,
            origen_id,
            moneda,
            estado,
            usuario
        FROM asientos_contables
        WHERE {" AND ".join(where_parts)}
        ORDER BY fecha DESC, id DESC
        LIMIT :limit
        """
    )

    rows = db.execute(query, params).mappings().all()
    return [dict(r) for r in rows]


def obtener_asiento_detalle(db: Session, asiento_id: int) -> dict | None:
    cab = db.execute(
        text(
            """
            SELECT
                id,
                fecha,
                glosa,
                origen_tipo,
                origen_id,
                moneda,
                estado,
                usuario
            FROM asientos_contables
            WHERE id = :asiento_id
            """
        ),
        {"asiento_id": asiento_id},
    ).mappings().first()
    if not cab:
        return None

    det_query = text(
        """
        SELECT
            id,
            asiento_id,
            codigo_cuenta,
            nombre_cuenta,
            descripcion,
            debe,
            haber
        FROM asientos_detalle
        WHERE asiento_id = :asiento_id
        ORDER BY id ASC
        """
    )

    detalles = db.execute(det_query, {"asiento_id": asiento_id}).mappings().all()

    total_debe = sum(Decimal(str(x["debe"] or 0)) for x in detalles)
    total_haber = sum(Decimal(str(x["haber"] or 0)) for x in detalles)

    return {
        "cabecera": dict(cab),
        "detalles": [dict(x) for x in detalles],
        "total_debe": total_debe,
        "total_haber": total_haber,
    }


def obtener_estado_resultados(
    db: Session,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> dict:
    params: dict[str, Any] = {}
    where_fecha = []

    if fecha_desde:
        where_fecha.append("ac.fecha >= :fecha_desde")
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        where_fecha.append("ac.fecha <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta

    extra = f" AND {' AND '.join(where_fecha)}" if where_fecha else ""

    code_expr, name_expr = _detalle_exprs(db)
    query = text(
        f"""
        SELECT
            pc.tipo,
            pc.clasificacion,
            {code_expr} AS codigo_cuenta,
            {name_expr} AS nombre_cuenta,
            SUM(COALESCE(ad.debe, 0)) AS total_debe,
            SUM(COALESCE(ad.haber, 0)) AS total_haber,
            SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0)) AS saldo
        FROM asientos_detalle ad
        INNER JOIN asientos_contables ac
            ON ac.id = ad.asiento_id
        INNER JOIN fin.plan_cuenta pc
            ON pc.codigo = {code_expr}
        WHERE pc.tipo IN ('INGRESO', 'COSTO', 'GASTO')
        {extra}
        GROUP BY pc.tipo, pc.clasificacion, {code_expr}, {name_expr}
        ORDER BY {code_expr}
        """
    )

    rows = [dict(r) for r in db.execute(query, params).mappings().all()]

    ingresos = []
    costos = []
    gastos = []

    total_ingresos = Decimal("0")
    total_costos = Decimal("0")
    total_gastos = Decimal("0")

    for row in rows:
        tipo = str(row["tipo"] or "").upper()
        saldo = Decimal(str(row["saldo"] or 0))

        if tipo == "INGRESO":
            monto = saldo * Decimal("-1")
            total_ingresos += monto
            row["monto"] = monto
            ingresos.append(row)
        elif tipo == "COSTO":
            monto = saldo
            total_costos += monto
            row["monto"] = monto
            costos.append(row)
        elif tipo == "GASTO":
            monto = saldo
            total_gastos += monto
            row["monto"] = monto
            gastos.append(row)

    utilidad_bruta = total_ingresos - total_costos
    resultado_operacional = utilidad_bruta - total_gastos

    return {
        "ingresos": ingresos,
        "costos": costos,
        "gastos": gastos,
        "total_ingresos": total_ingresos,
        "total_costos": total_costos,
        "total_gastos": total_gastos,
        "utilidad_bruta": utilidad_bruta,
        "resultado_operacional": resultado_operacional,
    }


def obtener_balance_general(
    db: Session,
    *,
    fecha_hasta: str | None = None,
) -> dict:
    params: dict[str, Any] = {}
    extra = ""

    if fecha_hasta:
        extra = "AND ac.fecha <= :fecha_hasta"
        params["fecha_hasta"] = fecha_hasta

    code_expr, name_expr = _detalle_exprs(db)
    query = text(
        f"""
        SELECT
            pc.tipo,
            pc.clasificacion,
            {code_expr} AS codigo_cuenta,
            {name_expr} AS nombre_cuenta,
            SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0)) AS saldo
        FROM asientos_detalle ad
        INNER JOIN asientos_contables ac
            ON ac.id = ad.asiento_id
        INNER JOIN fin.plan_cuenta pc
            ON pc.codigo = {code_expr}
        WHERE pc.tipo IN ('ACTIVO', 'PASIVO', 'PATRIMONIO')
        {extra}
        GROUP BY pc.tipo, pc.clasificacion, {code_expr}, {name_expr}
        ORDER BY {code_expr}
        """
    )

    rows = [dict(r) for r in db.execute(query, params).mappings().all()]

    # Resultado acumulado (INGRESO/COSTO/GASTO) incorporado al patrimonio
    # para cuadrar correctamente la ecuación del balance cuando aún no se ha
    # hecho cierre de resultados contra cuentas patrimoniales.
    query_resultado = text(
        f"""
        SELECT
            COALESCE(SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0)), 0) AS saldo_resultado
        FROM asientos_detalle ad
        INNER JOIN asientos_contables ac
            ON ac.id = ad.asiento_id
        INNER JOIN fin.plan_cuenta pc
            ON pc.codigo = {code_expr}
        WHERE pc.tipo IN ('INGRESO', 'COSTO', 'GASTO')
        {extra}
        """
    )
    saldo_resultado = Decimal(
        str(db.execute(query_resultado, params).scalar() or 0)
    )
    resultado_acumulado = saldo_resultado * Decimal("-1")

    activos = []
    pasivos = []
    patrimonio = []

    total_activos = Decimal("0")
    total_pasivos = Decimal("0")
    total_patrimonio = Decimal("0")

    for row in rows:
        tipo = str(row["tipo"] or "").upper()
        saldo = Decimal(str(row["saldo"] or 0))

        if tipo == "ACTIVO":
            monto = saldo
            total_activos += monto
            row["monto"] = monto
            activos.append(row)
        elif tipo == "PASIVO":
            monto = saldo * Decimal("-1")
            total_pasivos += monto
            row["monto"] = monto
            pasivos.append(row)
        elif tipo == "PATRIMONIO":
            monto = saldo * Decimal("-1")
            total_patrimonio += monto
            row["monto"] = monto
            patrimonio.append(row)

    if resultado_acumulado != Decimal("0"):
        patrimonio.append(
            {
                "tipo": "PATRIMONIO",
                "clasificacion": "RESULTADO",
                "codigo_cuenta": "RESULTADO_EJERCICIO",
                "nombre_cuenta": "Resultado acumulado del ejercicio",
                "saldo": resultado_acumulado,
                "monto": resultado_acumulado,
            }
        )
        total_patrimonio += resultado_acumulado

    return {
        "activos": activos,
        "pasivos": pasivos,
        "patrimonio": patrimonio,
        "resultado_acumulado": resultado_acumulado,
        "total_activos": total_activos,
        "total_pasivos": total_pasivos,
        "total_patrimonio": total_patrimonio,
        "cuadra": total_activos == (total_pasivos + total_patrimonio),
    }


def obtener_balance_8_columnas(
    db: Session,
    *,
    fecha_desde: str,
    fecha_hasta: str,
) -> dict:
    params_ini: dict[str, Any] = {"fecha_desde": fecha_desde}
    params_mov: dict[str, Any] = {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta}

    code_expr, _name_expr = _detalle_exprs(db)
    query_saldo_inicial = text(
        """
        SELECT
            pc.codigo AS codigo_cuenta,
            pc.nombre AS nombre_cuenta,
            COALESCE(SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0)), 0) AS saldo
        FROM fin.plan_cuenta pc
        LEFT JOIN asientos_detalle ad
            ON """
        + code_expr
        + """ = pc.codigo
        LEFT JOIN asientos_contables ac
            ON ac.id = ad.asiento_id
           AND ac.fecha < :fecha_desde
        WHERE pc.estado = 'ACTIVO'
          AND pc.acepta_movimiento = TRUE
        GROUP BY pc.codigo, pc.nombre
        """
    )

    query_movimientos = text(
        """
        SELECT
            pc.codigo AS codigo_cuenta,
            pc.nombre AS nombre_cuenta,
            COALESCE(SUM(COALESCE(ad.debe, 0)), 0) AS debe,
            COALESCE(SUM(COALESCE(ad.haber, 0)), 0) AS haber
        FROM fin.plan_cuenta pc
        LEFT JOIN asientos_detalle ad
            ON """
        + code_expr
        + """ = pc.codigo
        LEFT JOIN asientos_contables ac
            ON ac.id = ad.asiento_id
           AND ac.fecha >= :fecha_desde
           AND ac.fecha <= :fecha_hasta
        WHERE pc.estado = 'ACTIVO'
          AND pc.acepta_movimiento = TRUE
        GROUP BY pc.codigo, pc.nombre
        """
    )

    ini_rows = [dict(r) for r in db.execute(query_saldo_inicial, params_ini).mappings().all()]
    mov_rows = [dict(r) for r in db.execute(query_movimientos, params_mov).mappings().all()]

    by_code: dict[str, dict] = {}
    for row in ini_rows:
        code = str(row.get("codigo_cuenta") or "").strip()
        if not code:
            continue
        by_code[code] = {
            "codigo_cuenta": code,
            "nombre_cuenta": row.get("nombre_cuenta") or "",
            "saldo_inicial": Decimal(str(row.get("saldo") or 0)),
            "debe": Decimal("0"),
            "haber": Decimal("0"),
        }

    for row in mov_rows:
        code = str(row.get("codigo_cuenta") or "").strip()
        if not code:
            continue
        if code not in by_code:
            by_code[code] = {
                "codigo_cuenta": code,
                "nombre_cuenta": row.get("nombre_cuenta") or "",
                "saldo_inicial": Decimal("0"),
                "debe": Decimal("0"),
                "haber": Decimal("0"),
            }
        by_code[code]["debe"] = Decimal(str(row.get("debe") or 0))
        by_code[code]["haber"] = Decimal(str(row.get("haber") or 0))

    rows: list[dict] = []
    total_sd_ini = Decimal("0")
    total_sa_ini = Decimal("0")
    total_debe = Decimal("0")
    total_haber = Decimal("0")
    total_sd_fin = Decimal("0")
    total_sa_fin = Decimal("0")

    for code in sorted(by_code.keys()):
        item = by_code[code]
        saldo_inicial = item["saldo_inicial"]
        debe = item["debe"]
        haber = item["haber"]
        saldo_final = saldo_inicial + debe - haber

        sd_ini = saldo_inicial if saldo_inicial > 0 else Decimal("0")
        sa_ini = (saldo_inicial * Decimal("-1")) if saldo_inicial < 0 else Decimal("0")
        sd_fin = saldo_final if saldo_final > 0 else Decimal("0")
        sa_fin = (saldo_final * Decimal("-1")) if saldo_final < 0 else Decimal("0")

        if sd_ini == 0 and sa_ini == 0 and debe == 0 and haber == 0 and sd_fin == 0 and sa_fin == 0:
            continue

        total_sd_ini += sd_ini
        total_sa_ini += sa_ini
        total_debe += debe
        total_haber += haber
        total_sd_fin += sd_fin
        total_sa_fin += sa_fin

        rows.append(
            {
                "codigo_cuenta": code,
                "nombre_cuenta": item["nombre_cuenta"],
                "saldo_inicial_deudor": sd_ini,
                "saldo_inicial_acreedor": sa_ini,
                "movimiento_debe": debe,
                "movimiento_haber": haber,
                "saldo_final_deudor": sd_fin,
                "saldo_final_acreedor": sa_fin,
            }
        )

    return {
        "rows": rows,
        "totales": {
            "saldo_inicial_deudor": total_sd_ini,
            "saldo_inicial_acreedor": total_sa_ini,
            "movimiento_debe": total_debe,
            "movimiento_haber": total_haber,
            "saldo_final_deudor": total_sd_fin,
            "saldo_final_acreedor": total_sa_fin,
        },
    }


def obtener_libro_mayor_cuenta(
    db: Session,
    *,
    codigo_cuenta: str,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> dict:
    code = (codigo_cuenta or "").strip()
    if not code:
        raise ValueError("Debe indicar código de cuenta para el libro mayor.")

    params_si: dict[str, Any] = {"codigo_cuenta": code}
    where_si = ["ad.codigo_cuenta = :codigo_cuenta"]
    if fecha_desde:
        where_si.append("ac.fecha < :fecha_desde")
        params_si["fecha_desde"] = fecha_desde

    query_saldo_inicial = text(
        f"""
        SELECT COALESCE(SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0)), 0) AS saldo_inicial
        FROM asientos_detalle ad
        INNER JOIN asientos_contables ac ON ac.id = ad.asiento_id
        WHERE {' AND '.join(where_si)}
        """
    )
    saldo_inicial = Decimal(str(db.execute(query_saldo_inicial, params_si).scalar() or 0))

    params_mv: dict[str, Any] = {"codigo_cuenta": code}
    where_mv = ["ad.codigo_cuenta = :codigo_cuenta"]
    if fecha_desde:
        where_mv.append("ac.fecha >= :fecha_desde")
        params_mv["fecha_desde"] = fecha_desde
    if fecha_hasta:
        where_mv.append("ac.fecha <= :fecha_hasta")
        params_mv["fecha_hasta"] = fecha_hasta

    query_movs = text(
        f"""
        SELECT
            ac.id AS asiento_id,
            ac.fecha AS fecha,
            COALESCE(ac.glosa, '') AS glosa,
            COALESCE(ad.descripcion, '') AS detalle,
            COALESCE(ad.debe, 0) AS debe,
            COALESCE(ad.haber, 0) AS haber
        FROM asientos_detalle ad
        INNER JOIN asientos_contables ac ON ac.id = ad.asiento_id
        WHERE {' AND '.join(where_mv)}
        ORDER BY ac.fecha ASC, ac.id ASC, ad.id ASC
        """
    )
    movs = [dict(r) for r in db.execute(query_movs, params_mv).mappings().all()]

    cuenta = obtener_plan_cuenta_por_codigo(db, code)
    nombre_cuenta = cuenta.nombre if cuenta else ""

    running = saldo_inicial
    total_debe = Decimal("0")
    total_haber = Decimal("0")
    out_rows: list[dict] = []
    for row in movs:
        debe = Decimal(str(row.get("debe") or 0))
        haber = Decimal(str(row.get("haber") or 0))
        total_debe += debe
        total_haber += haber
        running = running + debe - haber
        out_rows.append(
            {
                **row,
                "debe": debe,
                "haber": haber,
                "saldo": running,
            }
        )

    return {
        "codigo_cuenta": code,
        "nombre_cuenta": nombre_cuenta,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "saldo_inicial": saldo_inicial,
        "rows": out_rows,
        "total_debe": total_debe,
        "total_haber": total_haber,
        "saldo_final": running,
    }