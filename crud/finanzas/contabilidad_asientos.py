# crud/finanzas/contabilidad_asientos.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

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
    rows = db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table_name
            """
        ),
        {"schema": schema, "table_name": table_name},
    ).scalars().all()
    return set(rows)


def _pick_first_existing(columns: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


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
    table_name = "asientos_contables"
    cols = _table_columns(db, table_name)

    if not cols:
        raise ValueError("No existe la tabla 'asientos_contables' o no es accesible.")

    payload: dict[str, Any] = {}
    now = datetime.utcnow()

    if "fecha" in cols:
        payload["fecha"] = fecha

    origen_tipo_col = _pick_first_existing(cols, ["origen_tipo", "origen"])
    if origen_tipo_col:
        payload[origen_tipo_col] = origen_tipo

    if "origen_id" in cols:
        payload["origen_id"] = origen_id

    texto_col = _pick_first_existing(cols, ["glosa", "descripcion", "detalle", "concepto", "observacion"])
    if texto_col:
        payload[texto_col] = (glosa or "")[:255]

    if "moneda" in cols:
        payload["moneda"] = moneda

    if "estado" in cols:
        payload["estado"] = "PUBLICADO"

    usuario_col = _pick_first_existing(cols, ["usuario", "creado_por", "user_email"])
    if usuario_col:
        payload[usuario_col] = usuario

    if "fecha_creacion" in cols:
        payload["fecha_creacion"] = now
    if "fecha_actualizacion" in cols:
        payload["fecha_actualizacion"] = now
    if "created_at" in cols:
        payload["created_at"] = now
    if "updated_at" in cols:
        payload["updated_at"] = now

    if not payload:
        raise ValueError("No fue posible determinar columnas válidas para insertar el asiento contable.")

    columns_sql = ", ".join(payload.keys())
    values_sql = ", ".join(f":{key}" for key in payload.keys())

    query = text(
        f"""
        INSERT INTO {table_name} ({columns_sql})
        VALUES ({values_sql})
        RETURNING id
        """
    )

    asiento_id = db.execute(query, payload).scalar_one()
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
    table_name = "asientos_detalle"
    cols = _table_columns(db, table_name)

    if not cols:
        raise ValueError("No existe la tabla 'asientos_detalle' o no es accesible.")

    required = {"asiento_id", "debe", "haber"}
    if not required.issubset(cols):
        faltantes = sorted(required - cols)
        raise ValueError(
            f"La tabla 'asientos_detalle' no tiene las columnas mínimas requeridas: {', '.join(faltantes)}"
        )

    payload: dict[str, Any] = {
        "asiento_id": asiento_id,
        "debe": debe,
        "haber": haber,
    }

    if "codigo_cuenta" in cols:
        payload["codigo_cuenta"] = codigo_cuenta
    elif "cuenta_contable" in cols:
        payload["cuenta_contable"] = codigo_cuenta
    else:
        raise ValueError("La tabla 'asientos_detalle' no tiene columna de cuenta.")

    if "nombre_cuenta" in cols:
        payload["nombre_cuenta"] = nombre_cuenta

    if "descripcion" in cols:
        payload["descripcion"] = descripcion

    now = datetime.utcnow()
    if "fecha_creacion" in cols:
        payload["fecha_creacion"] = now
    if "fecha_actualizacion" in cols:
        payload["fecha_actualizacion"] = now
    if "created_at" in cols:
        payload["created_at"] = now
    if "updated_at" in cols:
        payload["updated_at"] = now

    columns_sql = ", ".join(payload.keys())
    values_sql = ", ".join(f":{key}" for key in payload.keys())

    query = text(
        f"""
        INSERT INTO {table_name} ({columns_sql})
        VALUES ({values_sql})
        """
    )
    db.execute(query, payload)


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
) -> int:
    if not detalles:
        raise ValueError("El asiento debe tener al menos un detalle.")

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
        raise ValueError(f"Asiento no cuadra (Debe {total_debe} != Haber {total_haber})")

    try:
        # Bloqueo de período lo más cerca posible del INSERT para no retener
        # fin.periodo FOR UPDATE durante toda la validación de líneas.
        crud_periodos.assert_periodo_abierto_para_fecha(db, fecha_asiento)

        asiento_id = _insert_header_dynamic(
            db,
            fecha=fecha_asiento,
            origen_tipo=origen_tipo,
            origen_id=origen_id,
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

        if do_commit:
            db.commit()
        return asiento_id

    except Exception:
        if do_commit:
            db.rollback()
        raise


def eliminar_asiento_contable(db: Session, asiento_id: int) -> None:
    """Elimina detalle y cabecera del asiento (uso interno, p. ej. reversión al borrar documento AP)."""
    if asiento_id <= 0:
        return
    det_cols = _table_columns(db, "asientos_detalle")
    cab_cols = _table_columns(db, "asientos_contables")
    if not det_cols or not cab_cols:
        return
    db.execute(text("DELETE FROM asientos_detalle WHERE asiento_id = :id"), {"id": asiento_id})
    db.execute(text("DELETE FROM asientos_contables WHERE id = :id"), {"id": asiento_id})


ORIGENES_MANUALES_REVERSIBLES = frozenset({"MANUAL_AJUSTE", "MANUAL_APERTURA"})


def crear_reversion_asiento_manual(
    db: Session,
    *,
    asiento_original_id: int,
    glosa: str | None,
    usuario: str | None = None,
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
    )


def listar_asientos(
    db: Session,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    origen_tipo: str | None = None,
    limit: int = 200,
) -> list[dict]:
    cols = _table_columns(db, "asientos_contables")
    if not cols:
        return []

    fecha_col = "fecha" if "fecha" in cols else "fecha_creacion"
    glosa_col = _pick_first_existing(cols, ["glosa", "descripcion", "detalle", "concepto", "observacion"])
    origen_tipo_col = _pick_first_existing(cols, ["origen_tipo", "origen"])
    usuario_col = _pick_first_existing(cols, ["usuario", "creado_por", "user_email"])
    moneda_col = "moneda" if "moneda" in cols else None
    estado_col = "estado" if "estado" in cols else None

    select_parts = [
        "id",
        f"{fecha_col} AS fecha",
        f"{glosa_col} AS glosa" if glosa_col else "NULL::text AS glosa",
        f"{origen_tipo_col} AS origen_tipo" if origen_tipo_col else "NULL::text AS origen_tipo",
        "origen_id" if "origen_id" in cols else "NULL::bigint AS origen_id",
        f"{moneda_col} AS moneda" if moneda_col else "'CLP'::text AS moneda",
        f"{estado_col} AS estado" if estado_col else "'PUBLICADO'::text AS estado",
        f"{usuario_col} AS usuario" if usuario_col else "NULL::text AS usuario",
    ]

    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": limit}

    if fecha_desde:
        where_parts.append(f"{fecha_col} >= :fecha_desde")
        params["fecha_desde"] = fecha_desde

    if fecha_hasta:
        where_parts.append(f"{fecha_col} <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta

    if origen_tipo and origen_tipo_col:
        where_parts.append(f"{origen_tipo_col} = :origen_tipo")
        params["origen_tipo"] = origen_tipo

    query = text(
        f"""
        SELECT {", ".join(select_parts)}
        FROM asientos_contables
        WHERE {" AND ".join(where_parts)}
        ORDER BY id DESC
        LIMIT :limit
        """
    )

    rows = db.execute(query, params).mappings().all()
    return [dict(r) for r in rows]


def obtener_asiento_detalle(db: Session, asiento_id: int) -> dict | None:
    cab_cols = _table_columns(db, "asientos_contables")
    det_cols = _table_columns(db, "asientos_detalle")

    if not cab_cols or not det_cols:
        return None

    fecha_col = "fecha" if "fecha" in cab_cols else "fecha_creacion"
    glosa_col = _pick_first_existing(cab_cols, ["glosa", "descripcion", "detalle", "concepto", "observacion"])
    origen_tipo_col = _pick_first_existing(cab_cols, ["origen_tipo", "origen"])
    usuario_col = _pick_first_existing(cab_cols, ["usuario", "creado_por", "user_email"])
    moneda_col = "moneda" if "moneda" in cab_cols else None
    estado_col = "estado" if "estado" in cab_cols else None

    cab_query = text(
        f"""
        SELECT
            id,
            {fecha_col} AS fecha,
            {glosa_col if glosa_col else "NULL::text"} AS glosa,
            {origen_tipo_col if origen_tipo_col else "NULL::text"} AS origen_tipo,
            {"origen_id" if "origen_id" in cab_cols else "NULL::bigint"} AS origen_id,
            {moneda_col if moneda_col else "'CLP'::text"} AS moneda,
            {estado_col if estado_col else "'PUBLICADO'::text"} AS estado,
            {usuario_col if usuario_col else "NULL::text"} AS usuario
        FROM asientos_contables
        WHERE id = :asiento_id
        """
    )

    cab = db.execute(cab_query, {"asiento_id": asiento_id}).mappings().first()
    if not cab:
        return None

    codigo_col = "codigo_cuenta" if "codigo_cuenta" in det_cols else "cuenta_contable"
    nombre_col = "nombre_cuenta" if "nombre_cuenta" in det_cols else None
    descripcion_col = "descripcion" if "descripcion" in det_cols else None

    det_query = text(
        f"""
        SELECT
            id,
            asiento_id,
            {codigo_col} AS codigo_cuenta,
            {nombre_col if nombre_col else "NULL::text"} AS nombre_cuenta,
            {descripcion_col if descripcion_col else "NULL::text"} AS descripcion,
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

    query = text(
        f"""
        SELECT
            pc.tipo,
            pc.clasificacion,
            COALESCE(ad.codigo_cuenta, ad.cuenta_contable) AS codigo_cuenta,
            COALESCE(ad.nombre_cuenta, pc.nombre) AS nombre_cuenta,
            SUM(COALESCE(ad.debe, 0)) AS total_debe,
            SUM(COALESCE(ad.haber, 0)) AS total_haber,
            SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0)) AS saldo
        FROM asientos_detalle ad
        INNER JOIN asientos_contables ac
            ON ac.id = ad.asiento_id
        INNER JOIN fin.plan_cuenta pc
            ON pc.codigo = COALESCE(ad.codigo_cuenta, ad.cuenta_contable)
        WHERE pc.tipo IN ('INGRESO', 'COSTO', 'GASTO')
        {extra}
        GROUP BY pc.tipo, pc.clasificacion, COALESCE(ad.codigo_cuenta, ad.cuenta_contable), COALESCE(ad.nombre_cuenta, pc.nombre)
        ORDER BY COALESCE(ad.codigo_cuenta, ad.cuenta_contable)
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

    query = text(
        f"""
        SELECT
            pc.tipo,
            pc.clasificacion,
            COALESCE(ad.codigo_cuenta, ad.cuenta_contable) AS codigo_cuenta,
            COALESCE(ad.nombre_cuenta, pc.nombre) AS nombre_cuenta,
            SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0)) AS saldo
        FROM asientos_detalle ad
        INNER JOIN asientos_contables ac
            ON ac.id = ad.asiento_id
        INNER JOIN fin.plan_cuenta pc
            ON pc.codigo = COALESCE(ad.codigo_cuenta, ad.cuenta_contable)
        WHERE pc.tipo IN ('ACTIVO', 'PASIVO', 'PATRIMONIO')
        {extra}
        GROUP BY pc.tipo, pc.clasificacion, COALESCE(ad.codigo_cuenta, ad.cuenta_contable), COALESCE(ad.nombre_cuenta, pc.nombre)
        ORDER BY COALESCE(ad.codigo_cuenta, ad.cuenta_contable)
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
            ON pc.codigo = COALESCE(ad.codigo_cuenta, ad.cuenta_contable)
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

    query_saldo_inicial = text(
        """
        SELECT
            pc.codigo AS codigo_cuenta,
            pc.nombre AS nombre_cuenta,
            COALESCE(SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0)), 0) AS saldo
        FROM fin.plan_cuenta pc
        LEFT JOIN asientos_detalle ad
            ON COALESCE(ad.codigo_cuenta, ad.cuenta_contable) = pc.codigo
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
            ON COALESCE(ad.codigo_cuenta, ad.cuenta_contable) = pc.codigo
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
    where_si = ["COALESCE(ad.codigo_cuenta, ad.cuenta_contable) = :codigo_cuenta"]
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
    where_mv = ["COALESCE(ad.codigo_cuenta, ad.cuenta_contable) = :codigo_cuenta"]
    if fecha_desde:
        where_mv.append("ac.fecha >= :fecha_desde")
        params_mv["fecha_desde"] = fecha_desde
    if fecha_hasta:
        where_mv.append("ac.fecha <= :fecha_hasta")
        params_mv["fecha_hasta"] = fecha_hasta

    cab_cols = _table_columns(db, "asientos_contables")
    det_cols = _table_columns(db, "asientos_detalle")
    if not cab_cols or not det_cols:
        raise ValueError("No se pudieron detectar columnas contables para el libro mayor.")

    fecha_col = "fecha" if "fecha" in cab_cols else _pick_first_existing(cab_cols, ["fecha_creacion", "created_at"])
    if not fecha_col:
        raise ValueError("La tabla asientos_contables no tiene columna de fecha utilizable.")

    glosa_col = _pick_first_existing(cab_cols, ["glosa", "descripcion", "detalle", "concepto", "observacion"])
    glosa_sql = f"COALESCE(ac.{glosa_col}, '')" if glosa_col else "''"

    det_desc_col = "descripcion" if "descripcion" in det_cols else None
    det_desc_sql = f"COALESCE(ad.{det_desc_col}, '')" if det_desc_col else "''"

    query_movs = text(
        f"""
        SELECT
            ac.id AS asiento_id,
            ac.{fecha_col} AS fecha,
            {glosa_sql} AS glosa,
            {det_desc_sql} AS detalle,
            COALESCE(ad.debe, 0) AS debe,
            COALESCE(ad.haber, 0) AS haber
        FROM asientos_detalle ad
        INNER JOIN asientos_contables ac ON ac.id = ad.asiento_id
        WHERE {' AND '.join(where_mv)}
        ORDER BY ac.{fecha_col} ASC, ac.id ASC, ad.id ASC
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