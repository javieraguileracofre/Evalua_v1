# crud/finanzas/cuentas_por_pagar.py
# -*- coding: utf-8 -*-
"""
Cuentas por pagar (AP) — módulo reescrito.

Regla única de montos:
  total_documento = Σ (neto_linea + iva_linea) + Σ otros_impuestos (no se confía en total_linea en BD).
  Cabecera neto/exento/iva se deriva de las líneas (no se suma dos veces la misma base).

Tablas ORM existentes: fin.ap_documento, ap_documento_detalle, ap_documento_impuesto, ap_pago, ap_pago_aplicacion.
(El esquema public puede tener otras tablas legacy; CxP solo lee/escribe fin.* — no se suman dos tablas.)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Optional

from sqlalchemy import delete, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from models import Proveedor, ProveedorBanco
from models.finanzas.compras_finanzas import (
    APDocumento,
    APDocumentoDetalle,
    APDocumentoImpuesto,
    APPago,
    APPagoAplicacion,
    CategoriaGasto,
    CentroCosto,
    Periodo,
)
from models.finanzas.plan_cuentas import PlanCuenta
from schemas.finanzas.cuentas_por_pagar import DocumentoCreate, DocumentoUpdate, PagoCreate
from crud.finanzas.contabilidad_asientos import crear_asiento, eliminar_asiento_contable
from crud.finanzas.cxp_montos_sql import cxp_sql_saldo_desde_lineas, cxp_sql_total_desde_lineas

logger = logging.getLogger(__name__)

def _cxp_tablas_ap_listas(db: Session) -> bool:
    """True si existen las 5 tablas AP en fin (evita 500 tras reset parcial o create_all incompleto)."""
    n = db.execute(
        text(
            """
            SELECT COUNT(*)::int
            FROM information_schema.tables
            WHERE table_schema = 'fin'
              AND table_name IN (
                'ap_documento',
                'ap_documento_detalle',
                'ap_documento_impuesto',
                'ap_pago',
                'ap_pago_aplicacion'
              )
            """
        )
    ).scalar()
    return int(n or 0) >= 5


Z = Decimal("0.00")
Q2 = Decimal("0.01")
IVA_RATE = Decimal("0.19")
TOL = Decimal("0.02")


def Q(v: Any) -> Decimal:
    if v in (None, "", "null", "None"):
        return Z
    return Decimal(str(v)).quantize(Q2, rounding=ROUND_HALF_UP)


def _es_si(val: Any) -> bool:
    s = str(val or "NO").strip().upper()
    return s in ("SI", "SÍ", "TRUE", "1", "YES", "ON")


def _decimal_str(value: Any) -> str:
    if value is None:
        return "0"
    return str(value)


def _kwargs_ap_detalle_orm(row: Mapping[str, Any]) -> dict[str, Any]:
    """Columnas persistibles para insert/update ORM. total_linea es GENERATED en BD."""
    keys = (
        "linea",
        "descripcion",
        "cantidad",
        "precio_unitario",
        "descuento",
        "neto_linea",
        "iva_linea",
        "otros_impuestos",
        "categoria_gasto_id",
        "centro_costo_id",
    )
    return {k: row[k] for k in keys}


def calcular_desde_payload(payload: DocumentoCreate | DocumentoUpdate) -> dict[str, Any]:
    """Una sola pasada: líneas + impuestos + cabecera coherente con es_exento."""
    exento = _es_si(getattr(payload, "es_exento", "NO"))
    detalles_rows: list[dict[str, Any]] = []
    suma_neto_lineas = Z
    suma_iva_lineas = Z
    suma_total_lineas = Z

    for idx, det in enumerate(payload.detalles, start=1):
        bruto = Q(det.cantidad * det.precio_unitario)
        neto_linea = Q(bruto - det.descuento)
        iva_linea = Z if exento else Q(neto_linea * IVA_RATE)
        total_linea = Q(neto_linea + iva_linea)
        suma_neto_lineas += neto_linea
        suma_iva_lineas += iva_linea
        suma_total_lineas += total_linea
        detalles_rows.append(
            {
                "linea": idx,
                "descripcion": det.descripcion.strip(),
                "cantidad": det.cantidad,
                "precio_unitario": det.precio_unitario,
                "descuento": det.descuento,
                "neto_linea": neto_linea,
                "iva_linea": iva_linea,
                "otros_impuestos": Z,
                "categoria_gasto_id": det.categoria_gasto_id,
                "centro_costo_id": det.centro_costo_id,
            }
        )

    impuestos_rows: list[dict[str, Any]] = []
    total_otros = Z
    for imp in payload.impuestos:
        monto = Q(imp.monto)
        if monto <= Z:
            continue
        impuestos_rows.append(
            {
                "tipo": imp.tipo,
                "codigo": imp.codigo,
                "nombre": imp.nombre,
                "monto": monto,
            }
        )
        total_otros += monto

    total = Q(suma_total_lineas + total_otros)
    if exento:
        neto_h, exento_h, iva_h = Z, suma_neto_lineas, Z
    else:
        neto_h, exento_h, iva_h = suma_neto_lineas, Z, suma_iva_lineas

    return {
        "neto": neto_h,
        "exento": exento_h,
        "iva": iva_h,
        "otros_impuestos": Q(total_otros),
        "total": total,
        "detalles_rows": detalles_rows,
        "impuestos_rows": impuestos_rows,
        "es_exento": exento,
    }


def vista_totales_orm(doc: APDocumento, *, aplicado: Decimal) -> dict[str, Any]:
    """Totales de pantalla y negocio: siempre desde líneas + impuestos del documento."""
    dets = list(doc.detalles or [])
    imps = list(doc.impuestos or [])
    # neto_linea + iva_linea (no confiar en total_linea por si quedó corrupto en BD)
    sum_tl = sum((Q(Q(d.neto_linea) + Q(d.iva_linea)) for d in dets), Z)
    sum_nl = sum((Q(d.neto_linea) for d in dets), Z)
    sum_il = sum((Q(d.iva_linea) for d in dets), Z)
    sum_oi = sum((Q(i.monto) for i in imps), Z)
    if sum_oi == Z and Q(doc.otros_impuestos) > Z:
        sum_oi = Q(doc.otros_impuestos)
    total = Q(sum_tl + sum_oi)
    if sum_il > Z:
        neto, exento, iva = sum_nl, Z, sum_il
    else:
        neto, exento, iva = Z, sum_nl, Z
    saldo = Q(max(Z, total - Q(aplicado)))
    desinc = bool(dets) and abs(Q(doc.total) - total) > TOL
    return {
        "neto": neto,
        "exento": exento,
        "iva": iva,
        "otros_impuestos": sum_oi,
        "total": total,
        "saldo_pendiente": saldo,
        "cabecera_desincronizada": desinc,
    }


def _aplicado_a_documento(db: Session, documento_id: int) -> Decimal:
    r = (
        db.query(func.coalesce(func.sum(APPagoAplicacion.monto_aplicado), Z))
        .filter(APPagoAplicacion.documento_id == documento_id)
        .scalar()
    )
    return Q(r)


def _enum_label_pg(db: Session, *, schema: str, typname: str, preferred: str) -> str:
    row = db.execute(
        text(
            """
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = :schema
              AND t.typname = :typname
              AND upper(e.enumlabel) = upper(:pref)
            LIMIT 1
            """
        ),
        {"schema": schema, "typname": typname, "pref": preferred},
    ).scalar()
    return str(row or preferred)


def _ap_doc_estado_labels_columna(db: Session) -> list[str]:
    """
    Etiquetas del enum usado por fin.ap_documento.estado (mismo OID que la columna).
    Evita leer otro tipo homónimo o un enum desincronizado.
    """
    rows = db.execute(
        text(
            """
            SELECT e.enumlabel::text AS lbl
            FROM pg_enum e
            WHERE e.enumtypid = (
                SELECT a.atttypid
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'fin'
                  AND c.relname = 'ap_documento'
                  AND a.attname = 'estado'
                  AND NOT a.attisdropped
                LIMIT 1
            )
            ORDER BY e.enumsortorder
            """
        )
    ).all()
    out: list[str] = []
    for row in rows:
        lbl = row[0] if row is not None else None
        if lbl is not None:
            out.append(str(lbl))
    if out:
        return out
    # Fallback: tipo por nombre en schema fin (p. ej. tabla aún no visible en la sesión)
    rows2 = db.execute(
        text(
            """
            SELECT e.enumlabel::text AS lbl
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'fin'
              AND t.typname = 'ap_doc_estado'
            ORDER BY e.enumsortorder
            """
        )
    ).all()
    for row in rows2:
        lbl = row[0] if row is not None else None
        if lbl is not None:
            out.append(str(lbl))
    return out


def _ap_doc_estado_resolver(db: Session, preferencias: tuple[str, ...]) -> str:
    """Primera etiqueta de `preferencias` que exista en el enum real de la columna estado."""
    rows = _ap_doc_estado_labels_columna(db)
    if not rows:
        return preferencias[0] if preferencias else "BORRADOR"
    by_upper = {r.upper(): r for r in rows}
    for pref in preferencias:
        u = pref.upper()
        if u in by_upper:
            return by_upper[u]
    return rows[0]


def _ap_pago_estado_labels_columna(db: Session) -> list[str]:
    """
    Etiquetas del enum usado por fin.ap_pago.estado (OID real de la columna).
    Evita suposiciones cuando el enum fue cambiado en BD (ej. CONFIRMADO vs APLICADO).
    """
    rows = db.execute(
        text(
            """
            SELECT e.enumlabel::text AS lbl
            FROM pg_enum e
            WHERE e.enumtypid = (
                SELECT a.atttypid
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'fin'
                  AND c.relname = 'ap_pago'
                  AND a.attname = 'estado'
                  AND NOT a.attisdropped
                LIMIT 1
            )
            ORDER BY e.enumsortorder
            """
        )
    ).all()
    out: list[str] = []
    for row in rows:
        lbl = row[0] if row is not None else None
        if lbl is not None:
            out.append(str(lbl))
    if out:
        return out
    rows2 = db.execute(
        text(
            """
            SELECT e.enumlabel::text AS lbl
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'fin'
              AND t.typname = 'ap_pago_estado'
            ORDER BY e.enumsortorder
            """
        )
    ).all()
    for row in rows2:
        lbl = row[0] if row is not None else None
        if lbl is not None:
            out.append(str(lbl))
    return out


def _ap_pago_estado_resolver(db: Session, preferencias: tuple[str, ...]) -> str:
    rows = _ap_pago_estado_labels_columna(db)
    if not rows:
        return preferencias[0] if preferencias else "BORRADOR"
    by_upper = {r.upper(): r for r in rows}
    for pref in preferencias:
        if pref.upper() in by_upper:
            return by_upper[pref.upper()]
    return rows[0]


class CuentasPorPagarCRUD:
    def ap_tablas_operativas(self, db: Session) -> bool:
        """True si las 5 tablas fin.ap_* existen (tras reset parcial la app puede arrancar sin ellas)."""
        return _cxp_tablas_ap_listas(db)

    # --- enums en BD -------------------------------------------------
    def _estado_documento_abierto(self, db: Session) -> str:
        return _ap_doc_estado_resolver(db, ("BORRADOR", "INGRESADO", "ABIERTO"))

    def _estado_documento_pagado(self, db: Session) -> str:
        return _ap_doc_estado_resolver(db, ("PAGADO",))

    def _estado_pago_aplicado(self, db: Session) -> str:
        # Compatibilidad con esquemas antiguos/nuevos:
        # algunos tenants usan APLICADO y otros CONFIRMADO.
        return _ap_pago_estado_resolver(db, ("APLICADO", "CONFIRMADO"))

    def _estado_columna_por_saldo(
        self, db: Session, saldo: Decimal, fecha_vencimiento: date
    ) -> str:
        """Valor persistible: solo etiquetas del enum de la columna (BORRADOR suele existir aunque falte INGRESADO)."""
        if Q(saldo) <= Z:
            return self._estado_documento_pagado(db)
        if fecha_vencimiento < date.today():
            return _ap_doc_estado_resolver(
                db,
                ("VENCIDO", "BORRADOR", "INGRESADO", "ABIERTO", "PENDIENTE"),
            )
        return _ap_doc_estado_resolver(db, ("BORRADOR", "INGRESADO", "ABIERTO"))

    def _estado_visual_por_saldo(self, saldo: Decimal, fecha_vencimiento: date) -> str:
        """Etiquetas para listados/UI: PAGADO | VENCIDO | ABIERTO (independiente del enum en BD)."""
        if Q(saldo) <= Z:
            return "PAGADO"
        if fecha_vencimiento < date.today():
            return "VENCIDO"
        return "ABIERTO"

    def _aging_bucket(self, fecha_vencimiento: date, saldo_pendiente: Decimal) -> str:
        if Q(saldo_pendiente) <= Z:
            return "PAGADO"
        hoy = date.today()
        dias = (hoy - fecha_vencimiento).days
        if dias < 0:
            return "POR_VENCER"
        if dias == 0:
            return "VENCE_HOY"
        if dias <= 30:
            return "1_30"
        if dias <= 60:
            return "31_60"
        if dias <= 90:
            return "61_90"
        return "90_PLUS"

    def _log_evento(
        self,
        db: Session,
        *,
        entidad: str,
        entidad_id: int,
        evento: str,
        detalle: Optional[str] = None,
        user_email: Optional[str] = None,
        ip_origen: Optional[str] = None,
    ) -> None:
        try:
            db.execute(
                text(
                    """
                    INSERT INTO fin.evento (entidad, entidad_id, evento, detalle, user_email, ip_origen)
                    VALUES (:entidad, :entidad_id, :evento, :detalle, :user_email, :ip_origen)
                    """
                ),
                {
                    "entidad": entidad,
                    "entidad_id": entidad_id,
                    "evento": evento,
                    "detalle": detalle,
                    "user_email": user_email,
                    "ip_origen": ip_origen,
                },
            )
        except Exception:
            pass

    def _validar_periodo_abierto(self, db: Session, fecha_obj: date) -> None:
        periodo = (
            db.query(Periodo)
            .filter(Periodo.anio == fecha_obj.year, Periodo.mes == fecha_obj.month)
            .first()
        )
        if periodo and str(periodo.estado) == "CERRADO":
            raise ValueError(
                f"El período {fecha_obj.month:02d}/{fecha_obj.year} está cerrado."
            )

    def _tipo_compra_normalizado(self, raw: str | None) -> str:
        t = (raw or "GASTO").strip().upper()
        return t if t in ("INVENTARIO", "GASTO") else "GASTO"

    def _codigo_evento_ap(self, tipo_compra: str, afecto_iva: bool) -> str:
        inv = tipo_compra == "INVENTARIO"
        if inv:
            return "COMPRA_AFECTA" if afecto_iva else "COMPRA_INVENTARIO_EXENTO"
        return "COMPRA_GASTO_AFECTA" if afecto_iva else "COMPRA_GASTO_EXENTO"

    def _detalles_asiento_ap_desde_documento(
        self,
        db: Session,
        documento: APDocumento,
        payload: DocumentoCreate | DocumentoUpdate,
    ) -> list[dict[str, Any]]:
        vt = vista_totales_orm(documento, aplicado=Z)
        total = Q(vt["total"])
        iva = Q(vt["iva"])
        afecto = iva > Z
        tipo = self._tipo_compra_normalizado(
            getattr(documento, "tipo_compra_contable", None)
            or getattr(payload, "tipo_compra_contable", None)
        )
        evento = self._codigo_evento_ap(tipo, afecto)
        rows = (
            db.execute(
                text(
                    """
                    SELECT lado, codigo_cuenta, orden
                    FROM fin.config_contable
                    WHERE UPPER(TRIM(codigo_evento)) = UPPER(TRIM(:e))
                      AND UPPER(TRIM(estado)) = 'ACTIVO'
                    ORDER BY CASE WHEN UPPER(TRIM(lado)) = 'DEBE' THEN 0 ELSE 1 END, orden ASC
                    """
                ),
                {"e": evento},
            )
            .mappings()
            .all()
        )
        if not rows:
            raise ValueError(f"No hay configuración contable para el evento {evento}.")

        debe_rows = [r for r in rows if str(r["lado"]).strip().upper() == "DEBE"]
        haber_rows = [r for r in rows if str(r["lado"]).strip().upper() == "HABER"]
        if not debe_rows or not haber_rows:
            raise ValueError(f"Config contable incompleta para {evento}.")

        cuenta_gasto = (getattr(payload, "cuenta_gasto_codigo", None) or "").strip() or None
        cuenta_prov = (getattr(payload, "cuenta_proveedores_codigo", None) or "").strip() or None

        monto_principal = Q(total - iva)
        out: list[dict[str, Any]] = []

        cod1 = cuenta_gasto or str(debe_rows[0]["codigo_cuenta"]).strip()
        out.append(
            {
                "codigo_cuenta": cod1,
                "descripcion": f"Compra AP ({tipo})",
                "debe": monto_principal,
                "haber": Z,
            }
        )

        if afecto:
            if len(debe_rows) < 2:
                raise ValueError(
                    "Falta segunda cuenta DEBE (IVA crédito) en fin.config_contable para el evento configurado."
                )
            cod_iva = str(debe_rows[1]["codigo_cuenta"]).strip()
            out.append(
                {
                    "codigo_cuenta": cod_iva,
                    "descripcion": "IVA crédito fiscal",
                    "debe": iva,
                    "haber": Z,
                }
            )

        cod_h = cuenta_prov or str(haber_rows[0]["codigo_cuenta"]).strip()
        out.append(
            {
                "codigo_cuenta": cod_h,
                "descripcion": "Proveedores por pagar",
                "debe": Z,
                "haber": total,
            }
        )

        td = sum((Q(x["debe"]) for x in out), Z)
        th = sum((Q(x["haber"]) for x in out), Z)
        if td != th:
            raise ValueError(f"El asiento del documento no cuadra ({td} vs {th}).")

        return out

    def _detalles_asiento_pago_proveedor(
        self,
        db: Session,
        *,
        total_pago: Decimal,
        cuenta_proveedores_codigo: str | None = None,
    ) -> list[dict[str, Any]]:
        monto = Q(total_pago)
        if monto <= Z:
            raise ValueError("El monto total del pago debe ser mayor a 0 para generar asiento.")

        rows = (
            db.execute(
                text(
                    """
                    SELECT lado, codigo_cuenta, orden
                    FROM fin.config_contable
                    WHERE UPPER(TRIM(codigo_evento)) = 'PAGO_PROVEEDOR'
                      AND UPPER(TRIM(estado)) = 'ACTIVO'
                    ORDER BY CASE WHEN UPPER(TRIM(lado)) = 'DEBE' THEN 0 ELSE 1 END, orden ASC
                    """
                )
            )
            .mappings()
            .all()
        )
        if not rows:
            raise ValueError("No hay configuración contable activa para el evento PAGO_PROVEEDOR.")

        debe_rows = [r for r in rows if str(r["lado"]).strip().upper() == "DEBE"]
        haber_rows = [r for r in rows if str(r["lado"]).strip().upper() == "HABER"]
        if not debe_rows or not haber_rows:
            raise ValueError("Config contable incompleta para PAGO_PROVEEDOR.")

        cuenta_cxp = (cuenta_proveedores_codigo or "").strip() or str(debe_rows[0]["codigo_cuenta"]).strip()
        cuenta_banco = str(haber_rows[0]["codigo_cuenta"]).strip()

        detalles = [
            {
                "codigo_cuenta": cuenta_cxp,
                "descripcion": "Pago a proveedor",
                "debe": monto,
                "haber": Z,
            },
            {
                "codigo_cuenta": cuenta_banco,
                "descripcion": "Salida bancaria por pago a proveedor",
                "debe": Z,
                "haber": monto,
            },
        ]
        return detalles

    def _validar_banco_proveedor(
        self,
        db: Session,
        *,
        proveedor_id: int,
        banco_proveedor_id: Optional[int],
    ) -> Optional[int]:
        if not banco_proveedor_id:
            return None
        banco = (
            db.query(ProveedorBanco)
            .filter(
                ProveedorBanco.id == banco_proveedor_id,
                ProveedorBanco.proveedor_id == proveedor_id,
            )
            .first()
        )
        if not banco:
            raise ValueError("La cuenta bancaria seleccionada no pertenece al proveedor.")
        if hasattr(banco, "activo") and getattr(banco, "activo", True) is False:
            raise ValueError("La cuenta bancaria seleccionada está inactiva.")
        return banco.id

    def _sincronizar_cabecera_desde_lineas_si_seguro(self, db: Session, doc: APDocumento) -> None:
        aplicado = _aplicado_a_documento(db, int(doc.id))
        if aplicado > Z:
            return
        if getattr(doc, "asiento_id", None):
            return
        vt = vista_totales_orm(doc, aplicado=aplicado)
        if not vt["cabecera_desincronizada"]:
            return
        doc.neto = vt["neto"]
        doc.exento = vt["exento"]
        doc.iva = vt["iva"]
        doc.otros_impuestos = vt["otros_impuestos"]
        doc.total = vt["total"]
        doc.saldo_pendiente = vt["saldo_pendiente"]
        doc.estado = self._estado_columna_por_saldo(
            db, doc.saldo_pendiente, doc.fecha_vencimiento
        )
        try:
            db.commit()
            db.refresh(doc)
        except SQLAlchemyError as exc:
            logger.warning("CxP: no se pudo sincronizar cabecera doc=%s: %s", doc.id, exc)
            db.rollback()

    # --- catálogos ---------------------------------------------------
    def get_catalogos(self, db: Session) -> dict[str, list[dict[str, Any]]]:
        proveedores = (
            db.query(Proveedor)
            .filter(func.coalesce(getattr(Proveedor, "activo", True), True) == True)  # noqa: E712
            .order_by(Proveedor.razon_social.asc())
            .all()
        )
        categorias = (
            db.query(CategoriaGasto)
            .filter(CategoriaGasto.estado == "ACTIVO")
            .order_by(CategoriaGasto.codigo.asc(), CategoriaGasto.nombre.asc())
            .all()
        )
        centros = (
            db.query(CentroCosto)
            .filter(CentroCosto.estado == "ACTIVO")
            .order_by(CentroCosto.codigo.asc(), CentroCosto.nombre.asc())
            .all()
        )
        cuentas_mv = (
            db.query(PlanCuenta)
            .filter(
                PlanCuenta.estado == "ACTIVO",
                PlanCuenta.acepta_movimiento.is_(True),
            )
            .order_by(PlanCuenta.codigo.asc())
            .limit(800)
            .all()
        )
        return {
            "proveedores": [
                {"id": p.id, "rut": getattr(p, "rut", None), "razon_social": getattr(p, "razon_social", "")}
                for p in proveedores
            ],
            "categorias": [{"id": c.id, "codigo": c.codigo, "nombre": c.nombre} for c in categorias],
            "centros": [{"id": c.id, "codigo": c.codigo, "nombre": c.nombre} for c in centros],
            "cuentas_movimiento": [
                {"codigo": c.codigo, "nombre": getattr(c, "nombre", "") or ""} for c in cuentas_mv
            ],
        }

    def get_bancos_proveedor(self, db: Session, proveedor_id: int) -> list[dict[str, Any]]:
        rows = (
            db.query(ProveedorBanco)
            .filter(ProveedorBanco.proveedor_id == proveedor_id)
            .order_by(
                getattr(ProveedorBanco, "es_principal", False).desc(),
                ProveedorBanco.banco.asc(),
                ProveedorBanco.numero_cuenta.asc(),
            )
            .all()
        )
        return [
            {
                "id": x.id,
                "banco": getattr(x, "banco", ""),
                "tipo_cuenta": getattr(x, "tipo_cuenta", ""),
                "numero_cuenta": getattr(x, "numero_cuenta", ""),
                "titular": getattr(x, "titular", ""),
                "email_pago": getattr(x, "email_pago", ""),
                "es_principal": getattr(x, "es_principal", False),
            }
            for x in rows
        ]

    def get_resumen(self, db: Session) -> dict[str, Decimal | int]:
        if not _cxp_tablas_ap_listas(db):
            logger.warning("CxP: tablas AP incompletas en fin; KPI en cero hasta completar DDL (GRANT + create_all o tools/create_fin_ap_tables.py).")
            return {
                "documentos": 0,
                "total_documentado": Z,
                "saldo_pendiente": Z,
                "saldo_vencido": Z,
                "saldo_por_vencer": Z,
                "facturacion_liquidada": Z,
                "total_aplicado_hist": Z,
                "docs_vencidos": 0,
                "docs_por_vencer": 0,
            }
        hoy = date.today()
        proximo_7 = hoy + timedelta(days=7)
        # KPI desde líneas + impuestos + pagos aplicados (no desde cabecera duplicada en BD).
        row = db.execute(
            text(
                """
                WITH doc AS (
                    SELECT
                        d.id,
                        d.fecha_vencimiento,
                        (
                            SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
                            FROM fin.ap_documento_detalle det
                            WHERE det.documento_id = d.id
                        ) + (
                            SELECT COALESCE(SUM(imp.monto), 0)::numeric
                            FROM fin.ap_documento_impuesto imp
                            WHERE imp.documento_id = d.id
                        ) AS t_lineas,
                        (
                            SELECT COALESCE(SUM(a.monto_aplicado), 0)::numeric
                            FROM fin.ap_pago_aplicacion a
                            WHERE a.documento_id = d.id
                        ) AS t_aplicado
                    FROM fin.ap_documento d
                ),
                doc2 AS (
                    SELECT
                        id,
                        fecha_vencimiento,
                        t_lineas,
                        t_aplicado,
                        GREATEST(t_lineas - t_aplicado, 0)::numeric AS saldo_coherente
                    FROM doc
                )
                SELECT
                    COUNT(*)::bigint AS documentos,
                    COALESCE(SUM(t_lineas), 0) AS total_documentado,
                    COALESCE(SUM(saldo_coherente), 0) AS saldo_pendiente,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN saldo_coherente > 0 AND fecha_vencimiento < CURRENT_DATE
                                THEN saldo_coherente
                                ELSE 0
                            END
                        ),
                        0
                    ) AS saldo_vencido,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN saldo_coherente > 0
                                 AND fecha_vencimiento >= CURRENT_DATE
                                 AND fecha_vencimiento <= CAST(:proximo AS date)
                                THEN saldo_coherente
                                ELSE 0
                            END
                        ),
                        0
                    ) AS saldo_por_vencer,
                    COALESCE(SUM(t_aplicado), 0) AS total_aplicado_hist,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN saldo_coherente <= 0 THEN t_lineas
                                ELSE 0
                            END
                        ),
                        0
                    ) AS facturacion_liquidada
                FROM doc2
                """
            ),
            {"proximo": proximo_7},
        ).mappings().first()

        docs_vencidos = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*)::bigint
                    FROM fin.ap_documento d
                    WHERE d.fecha_vencimiento < CURRENT_DATE
                      AND (
                        (
                            SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
                            FROM fin.ap_documento_detalle det
                            WHERE det.documento_id = d.id
                        ) + (
                            SELECT COALESCE(SUM(imp.monto), 0)::numeric
                            FROM fin.ap_documento_impuesto imp
                            WHERE imp.documento_id = d.id
                        ) - (
                            SELECT COALESCE(SUM(a.monto_aplicado), 0)::numeric
                            FROM fin.ap_pago_aplicacion a
                            WHERE a.documento_id = d.id
                        )
                      ) > 0
                    """
                )
            ).scalar()
            or 0
        )
        docs_por_vencer = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*)::bigint
                    FROM fin.ap_documento d
                    WHERE d.fecha_vencimiento >= CURRENT_DATE
                      AND d.fecha_vencimiento <= CAST(:proximo AS date)
                      AND (
                        (
                            SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
                            FROM fin.ap_documento_detalle det
                            WHERE det.documento_id = d.id
                        ) + (
                            SELECT COALESCE(SUM(imp.monto), 0)::numeric
                            FROM fin.ap_documento_impuesto imp
                            WHERE imp.documento_id = d.id
                        ) - (
                            SELECT COALESCE(SUM(a.monto_aplicado), 0)::numeric
                            FROM fin.ap_pago_aplicacion a
                            WHERE a.documento_id = d.id
                        )
                      ) > 0
                    """
                ),
                {"proximo": proximo_7},
            ).scalar()
            or 0
        )

        return {
            "documentos": int(row["documentos"] if row else 0),
            "total_documentado": Q(row["total_documentado"] if row else 0),
            "saldo_pendiente": Q(row["saldo_pendiente"] if row else 0),
            "saldo_vencido": Q(row["saldo_vencido"] if row else 0),
            "saldo_por_vencer": Q(row["saldo_por_vencer"] if row else 0),
            "facturacion_liquidada": Q(row["facturacion_liquidada"] if row else 0),
            "total_aplicado_hist": Q(row["total_aplicado_hist"] if row else 0),
            "docs_vencidos": int(docs_vencidos),
            "docs_por_vencer": int(docs_por_vencer),
        }

    def list_documentos(
        self,
        db: Session,
        *,
        q: Optional[str] = None,
        proveedor_id: Optional[int] = None,
        estado: Optional[str] = None,
        solo_abiertos: bool = False,
    ) -> list[dict[str, Any]]:
        """Lista desde SQL: totales = Σ(neto_linea+iva_linea)+impuestos; saldo = total − aplicado."""
        if not _cxp_tablas_ap_listas(db):
            return []
        wheres: list[str] = ["TRUE"]
        params: dict[str, Any] = {}
        if q:
            wheres.append(
                "(p.razon_social ILIKE :cxp_q OR d.folio ILIKE :cxp_q OR COALESCE(d.referencia, '') ILIKE :cxp_q)"
            )
            params["cxp_q"] = f"%{q.strip()}%"
        if proveedor_id is not None:
            wheres.append("d.proveedor_id = :cxp_pid")
            params["cxp_pid"] = proveedor_id
        if estado:
            wheres.append("d.estado::text = :cxp_est")
            params["cxp_est"] = str(estado).strip()
        if solo_abiertos:
            wheres.append(
                "GREATEST("
                "(ln.sum_tl + COALESCE(im.sum_imp, 0::numeric) - COALESCE(ap.sum_app, 0::numeric)),"
                " 0::numeric"
                ") > 0::numeric"
            )

        where_sql = " AND ".join(wheres)
        sql = f"""
        SELECT
            d.id,
            d.tipo::text AS tipo,
            d.estado::text AS estado,
            d.folio,
            d.fecha_emision,
            d.fecha_recepcion,
            d.fecha_vencimiento,
            d.referencia,
            d.moneda::text AS moneda,
            d.asiento_id,
            p.id AS proveedor_id,
            p.rut AS rut,
            p.razon_social AS razon_social,
            ln.sum_tl,
            ln.sum_nl,
            ln.sum_il,
            COALESCE(im.sum_imp, 0::numeric) AS otros_impuestos,
            COALESCE(ap.sum_app, 0::numeric) AS aplicado,
            (ln.sum_tl + COALESCE(im.sum_imp, 0::numeric)) AS total_calculado,
            GREATEST(
                (ln.sum_tl + COALESCE(im.sum_imp, 0::numeric) - COALESCE(ap.sum_app, 0::numeric)),
                0::numeric
            ) AS saldo_pendiente,
            CASE WHEN ln.sum_il > 0 THEN ln.sum_nl ELSE 0::numeric END AS neto_calc,
            CASE WHEN ln.sum_il > 0 THEN 0::numeric ELSE ln.sum_nl END AS exento_calc,
            CASE WHEN ln.sum_il > 0 THEN ln.sum_il ELSE 0::numeric END AS iva_calc
        FROM fin.ap_documento d
        INNER JOIN proveedor p ON p.id = d.proveedor_id
        INNER JOIN LATERAL (
            SELECT
                COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric AS sum_tl,
                COALESCE(SUM(det.neto_linea), 0)::numeric AS sum_nl,
                COALESCE(SUM(det.iva_linea), 0)::numeric AS sum_il
            FROM fin.ap_documento_detalle det
            WHERE det.documento_id = d.id
        ) ln ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(imp.monto), 0)::numeric AS sum_imp
            FROM fin.ap_documento_impuesto imp
            WHERE imp.documento_id = d.id
        ) im ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(a.monto_aplicado), 0)::numeric AS sum_app
            FROM fin.ap_pago_aplicacion a
            WHERE a.documento_id = d.id
        ) ap ON TRUE
        WHERE {where_sql}
        ORDER BY d.fecha_vencimiento ASC, d.id DESC
        """

        rows = db.execute(text(sql), params).mappings().all()
        salida: list[dict[str, Any]] = []
        for row in rows:
            sp = Q(row["saldo_pendiente"])
            total = Q(row["total_calculado"])
            aplicado = Q(row["aplicado"])
            fv_cell = row["fecha_vencimiento"]
            if isinstance(fv_cell, datetime):
                fv_eff = fv_cell.date()
            elif isinstance(fv_cell, date):
                fv_eff = fv_cell
            else:
                fv_eff = date.today()
            dias_mora = 0
            if sp > Z and fv_eff < date.today():
                dias_mora = max((date.today() - fv_eff).days, 0)
            estado_visual = self._estado_visual_por_saldo(sp, fv_eff)
            salida.append(
                {
                    "id": row["id"],
                    "tipo": str(row["tipo"] or ""),
                    "estado": str(row["estado"] or ""),
                    "estado_visual": estado_visual,
                    "folio": row["folio"],
                    "fecha_emision": row["fecha_emision"],
                    "fecha_recepcion": row["fecha_recepcion"],
                    "fecha_vencimiento": fv_cell,
                    "moneda": str(row["moneda"] or ""),
                    "neto": Q(row["neto_calc"]),
                    "exento": Q(row["exento_calc"]),
                    "iva": Q(row["iva_calc"]),
                    "otros_impuestos": Q(row["otros_impuestos"]),
                    "total": total,
                    "saldo_pendiente": sp,
                    "referencia": row["referencia"],
                    "proveedor_id": row["proveedor_id"],
                    "rut": row["rut"] or "",
                    "razon_social": row["razon_social"] or "",
                    "dias_mora": dias_mora,
                    "aging_bucket": self._aging_bucket(fv_eff, sp),
                    "puede_eliminar": aplicado == Z and sp == total,
                    "asiento_id": row["asiento_id"],
                }
            )
        return salida

    def get_documento(self, db: Session, documento_id: int) -> Optional[APDocumento]:
        if not _cxp_tablas_ap_listas(db):
            return None
        return (
            db.query(APDocumento)
            .options(
                joinedload(APDocumento.proveedor),
                joinedload(APDocumento.detalles).joinedload(APDocumentoDetalle.categoria_gasto),
                joinedload(APDocumento.detalles).joinedload(APDocumentoDetalle.centro_costo),
                joinedload(APDocumento.impuestos),
                joinedload(APDocumento.aplicaciones_pago).joinedload(APPagoAplicacion.pago),
            )
            .filter(APDocumento.id == documento_id)
            .first()
        )

    def get_documento_view(self, db: Session, documento_id: int) -> Optional[dict[str, Any]]:
        doc = self.get_documento(db, documento_id)
        if not doc:
            return None
        self._sincronizar_cabecera_desde_lineas_si_seguro(db, doc)
        doc = self.get_documento(db, documento_id)
        if not doc:
            return None

        proveedor = doc.proveedor
        bancos = self.get_bancos_proveedor(db, doc.proveedor_id)
        pagos = db.execute(
            text(
                """
                SELECT
                    p.id,
                    p.fecha_pago,
                    p.medio_pago::text AS medio_pago,
                    p.referencia,
                    p.moneda::text AS moneda,
                    p.monto_total,
                    p.banco_proveedor_id,
                    a.monto_aplicado
                FROM fin.ap_pago_aplicacion a
                JOIN fin.ap_pago p ON p.id = a.pago_id
                WHERE a.documento_id = :documento_id
                ORDER BY p.fecha_pago DESC, p.id DESC
                """
            ),
            {"documento_id": documento_id},
        ).mappings().all()

        aplicado = sum((Q(x["monto_aplicado"]) for x in pagos), Z)
        totales = vista_totales_orm(doc, aplicado=aplicado)
        puede_eliminar = aplicado == Z and Q(totales["saldo_pendiente"]) == Q(totales["total"])

        return {
            "documento": doc,
            "totales": totales,
            "proveedor": {
                "id": proveedor.id if proveedor else None,
                "rut": getattr(proveedor, "rut", None) if proveedor else None,
                "razon_social": getattr(proveedor, "razon_social", None) if proveedor else None,
                "email": getattr(proveedor, "email", None) if proveedor else None,
                "telefono": getattr(proveedor, "telefono", None) if proveedor else None,
                "condicion_pago_dias": getattr(proveedor, "condicion_pago_dias", None)
                if proveedor
                else None,
            }
            if proveedor
            else None,
            "pagos": [dict(x) for x in pagos],
            "bancos": bancos,
            "total_aplicado": Q(aplicado),
            "aging_bucket": self._aging_bucket(doc.fecha_vencimiento, Q(totales["saldo_pendiente"])),
            "puede_eliminar": puede_eliminar,
        }

    def create_documento(
        self,
        db: Session,
        payload: DocumentoCreate,
        *,
        user_email: Optional[str] = None,
        ip_origen: Optional[str] = None,
    ) -> APDocumento:
        if not _cxp_tablas_ap_listas(db):
            raise ValueError(
                "Las tablas de cuentas por pagar no están creadas en la base de datos. "
                "Ejecute como postgres db/psql/096_grant_evalua_user_ap_fk.sql y luego "
                "python tools/create_fin_ap_tables.py (o reinicie la app tras corregir permisos)."
            )
        proveedor = db.query(Proveedor).filter(Proveedor.id == payload.proveedor_id).first()
        if not proveedor:
            raise ValueError("El proveedor seleccionado no existe.")
        self._validar_periodo_abierto(db, payload.fecha_emision)

        calc = calcular_desde_payload(payload)
        tipo_compra = self._tipo_compra_normalizado(getattr(payload, "tipo_compra_contable", "GASTO"))

        documento = APDocumento(
            proveedor_id=payload.proveedor_id,
            tipo=payload.tipo,
            estado=self._estado_documento_abierto(db),
            folio=payload.folio.strip(),
            fecha_emision=payload.fecha_emision,
            fecha_recepcion=payload.fecha_recepcion,
            fecha_vencimiento=payload.fecha_vencimiento,
            moneda=payload.moneda,
            tipo_cambio=Q(payload.tipo_cambio),
            neto=calc["neto"],
            exento=calc["exento"],
            iva=calc["iva"],
            otros_impuestos=calc["otros_impuestos"],
            total=calc["total"],
            saldo_pendiente=calc["total"],
            referencia=payload.referencia.strip() if payload.referencia else None,
            observaciones=payload.observaciones,
            tipo_compra_contable=tipo_compra,
            cuenta_gasto_codigo=payload.cuenta_gasto_codigo,
            cuenta_proveedores_codigo=payload.cuenta_proveedores_codigo,
        )
        documento.estado = self._estado_columna_por_saldo(
            db, documento.saldo_pendiente, documento.fecha_vencimiento
        )
        db.add(documento)
        db.flush()
        for row in calc["detalles_rows"]:
            db.add(
                APDocumentoDetalle(
                    documento_id=documento.id, **_kwargs_ap_detalle_orm(row)
                )
            )
        for row in calc["impuestos_rows"]:
            db.add(APDocumentoImpuesto(documento_id=documento.id, **row))
        db.flush()

        self._log_evento(
            db,
            entidad="ap_documento",
            entidad_id=documento.id,
            evento="CREADO",
            detalle=f"Documento {documento.tipo} folio {documento.folio} creado.",
            user_email=user_email,
            ip_origen=ip_origen,
        )

        try:
            if payload.generar_asiento_contable:
                det_asiento = self._detalles_asiento_ap_desde_documento(db, documento, payload)
                glosa = f"AP {documento.tipo} {documento.folio} proveedor {documento.proveedor_id}"
                asiento_id = crear_asiento(
                    db,
                    fecha=documento.fecha_emision,
                    origen_tipo="AP_DOCUMENTO",
                    origen_id=int(documento.id),
                    glosa=glosa[:255],
                    detalles=det_asiento,
                    usuario=user_email,
                    moneda=str(documento.moneda),
                    do_commit=False,
                )
                documento.asiento_id = asiento_id
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(documento)
        return documento

    def update_documento(
        self,
        db: Session,
        documento_id: int,
        payload: DocumentoUpdate,
        *,
        user_email: Optional[str] = None,
        ip_origen: Optional[str] = None,
    ) -> APDocumento:
        if not _cxp_tablas_ap_listas(db):
            raise ValueError(
                "Las tablas de cuentas por pagar no están creadas en la base de datos. "
                "Ejecute db/psql/096_grant_evalua_user_ap_fk.sql y python tools/create_fin_ap_tables.py."
            )
        documento = self.get_documento(db, documento_id)
        if not documento:
            raise ValueError("Documento no encontrado.")
        if getattr(documento, "asiento_id", None):
            raise ValueError(
                "Este documento ya tiene asiento contable y no puede editarse desde esta pantalla."
            )
        if str(documento.estado) == self._estado_documento_pagado(db):
            raise ValueError("No puedes editar un documento ya pagado.")

        proveedor = db.query(Proveedor).filter(Proveedor.id == payload.proveedor_id).first()
        if not proveedor:
            raise ValueError("El proveedor seleccionado no existe.")
        self._validar_periodo_abierto(db, payload.fecha_emision)

        calc = calcular_desde_payload(payload)
        pagado = _aplicado_a_documento(db, documento_id)

        documento.proveedor_id = payload.proveedor_id
        documento.tipo = payload.tipo
        documento.folio = payload.folio.strip()
        documento.fecha_emision = payload.fecha_emision
        documento.fecha_recepcion = payload.fecha_recepcion
        documento.fecha_vencimiento = payload.fecha_vencimiento
        documento.moneda = payload.moneda
        documento.tipo_cambio = Q(payload.tipo_cambio)
        documento.neto = calc["neto"]
        documento.exento = calc["exento"]
        documento.iva = calc["iva"]
        documento.otros_impuestos = calc["otros_impuestos"]
        documento.total = calc["total"]
        documento.referencia = payload.referencia.strip() if payload.referencia else None
        documento.observaciones = payload.observaciones
        documento.tipo_compra_contable = self._tipo_compra_normalizado(
            getattr(payload, "tipo_compra_contable", "GASTO")
        )
        documento.cuenta_gasto_codigo = payload.cuenta_gasto_codigo
        documento.cuenta_proveedores_codigo = payload.cuenta_proveedores_codigo

        nuevo_saldo = Q(calc["total"] - pagado)
        documento.saldo_pendiente = Z if nuevo_saldo < Z else nuevo_saldo
        documento.estado = self._estado_columna_por_saldo(
            db, documento.saldo_pendiente, documento.fecha_vencimiento
        )

        db.execute(delete(APDocumentoDetalle).where(APDocumentoDetalle.documento_id == documento.id))
        db.execute(delete(APDocumentoImpuesto).where(APDocumentoImpuesto.documento_id == documento.id))
        db.flush()
        for row in calc["detalles_rows"]:
            db.add(
                APDocumentoDetalle(
                    documento_id=documento.id, **_kwargs_ap_detalle_orm(row)
                )
            )
        for row in calc["impuestos_rows"]:
            db.add(APDocumentoImpuesto(documento_id=documento.id, **row))

        self._log_evento(
            db,
            entidad="ap_documento",
            entidad_id=documento.id,
            evento="ACTUALIZADO",
            detalle=f"Documento {documento.tipo} folio {documento.folio} actualizado.",
            user_email=user_email,
            ip_origen=ip_origen,
        )
        db.commit()
        db.refresh(documento)
        return documento

    def documentos_abiertos_proveedor(
        self, db: Session, proveedor_id: int
    ) -> list[dict[str, Any]]:
        if not _cxp_tablas_ap_listas(db):
            return []
        estado_pagado = self._estado_documento_pagado(db)
        tot = cxp_sql_total_desde_lineas("d")
        sal = cxp_sql_saldo_desde_lineas("d")
        sql = f"""
        SELECT
            d.id,
            d.tipo::text AS tipo,
            d.folio,
            d.fecha_vencimiento,
            d.estado::text AS estado,
            {tot} AS total_calc,
            {sal} AS saldo_calc
        FROM fin.ap_documento d
        WHERE d.proveedor_id = :pid
          AND d.estado::text <> :est_pagado
          AND ({sal}) > 0::numeric
        ORDER BY d.fecha_vencimiento ASC, d.id ASC
        """
        rows = db.execute(
            text(sql),
            {"pid": proveedor_id, "est_pagado": estado_pagado},
        ).mappings().all()
        return [
            {
                "id": r["id"],
                "tipo": str(r["tipo"] or ""),
                "folio": r["folio"],
                "fecha_vencimiento": r["fecha_vencimiento"],
                "total": Q(r["total_calc"]),
                "saldo_pendiente": Q(r["saldo_calc"]),
                "estado": str(r["estado"] or ""),
            }
            for r in rows
        ]

    def registrar_pago(
        self,
        db: Session,
        payload: PagoCreate,
        *,
        user_email: Optional[str] = None,
        ip_origen: Optional[str] = None,
    ) -> APPago:
        if not _cxp_tablas_ap_listas(db):
            raise ValueError(
                "Las tablas de cuentas por pagar no están creadas en la base de datos. "
                "Ejecute db/psql/096_grant_evalua_user_ap_fk.sql y python tools/create_fin_ap_tables.py."
            )
        proveedor = db.query(Proveedor).filter(Proveedor.id == payload.proveedor_id).first()
        if not proveedor:
            raise ValueError("El proveedor seleccionado no existe.")
        self._validar_periodo_abierto(db, payload.fecha_pago)

        aplicaciones_validas = [a for a in payload.aplicaciones if Q(a.monto_aplicado) > Z]
        if not aplicaciones_validas:
            raise ValueError("No hay montos aplicados válidos.")

        banco_proveedor_id = self._validar_banco_proveedor(
            db,
            proveedor_id=payload.proveedor_id,
            banco_proveedor_id=payload.banco_proveedor_id,
        )
        total_pago = sum((Q(a.monto_aplicado) for a in aplicaciones_validas), Z)

        pago = APPago(
            proveedor_id=payload.proveedor_id,
            estado=self._estado_pago_aplicado(db),
            fecha_pago=payload.fecha_pago,
            medio_pago=payload.medio_pago,
            referencia=payload.referencia,
            banco_proveedor_id=banco_proveedor_id,
            moneda=payload.moneda,
            tipo_cambio=Q(payload.tipo_cambio),
            monto_total=Q(total_pago),
            observaciones=payload.observaciones,
        )
        db.add(pago)
        db.flush()

        documentos_aplicados: list[APDocumento] = []
        for app in aplicaciones_validas:
            documento = (
                db.query(APDocumento)
                .options(
                    joinedload(APDocumento.detalles),
                    joinedload(APDocumento.impuestos),
                    joinedload(APDocumento.aplicaciones_pago),
                )
                .filter(
                    APDocumento.id == app.documento_id,
                    APDocumento.proveedor_id == payload.proveedor_id,
                )
                .first()
            )
            if not documento:
                raise ValueError(f"Documento {app.documento_id} no encontrado para el proveedor.")
            documentos_aplicados.append(documento)

            aplicado_doc = sum(
                (Q(a.monto_aplicado) for a in (documento.aplicaciones_pago or [])), Z
            )
            vt = vista_totales_orm(documento, aplicado=aplicado_doc)
            monto = Q(app.monto_aplicado)
            if monto > Q(vt["saldo_pendiente"]):
                raise ValueError(f"El monto aplicado excede el saldo del documento {documento.folio}.")

            db.add(
                APPagoAplicacion(
                    pago_id=pago.id,
                    documento_id=documento.id,
                    monto_aplicado=monto,
                )
            )
            nuevo_aplicado = Q(aplicado_doc + monto)
            documento.saldo_pendiente = Q(max(Z, Q(vt["total"]) - nuevo_aplicado))
            documento.estado = self._estado_columna_por_saldo(
                db, documento.saldo_pendiente, documento.fecha_vencimiento
            )
            self._log_evento(
                db,
                entidad="ap_documento",
                entidad_id=documento.id,
                evento="PAGO_APLICADO",
                detalle=f"Pago {pago.referencia or pago.id} aplicado por {monto}.",
                user_email=user_email,
                ip_origen=ip_origen,
            )

        db.flush()
        self._log_evento(
            db,
            entidad="ap_pago",
            entidad_id=pago.id,
            evento="CREADO",
            detalle=f"Pago registrado por {Q(total_pago)}.",
            user_email=user_email,
            ip_origen=ip_origen,
        )

        # Asiento del pago:
        # Debe  : Proveedores por pagar
        # Haber : Banco / caja (según configuración PAGO_PROVEEDOR)
        cuenta_proveedores_codigo = next(
            (
                (getattr(d, "cuenta_proveedores_codigo", None) or "").strip()
                for d in documentos_aplicados
                if (getattr(d, "cuenta_proveedores_codigo", None) or "").strip()
            ),
            None,
        )
        detalles_asiento = self._detalles_asiento_pago_proveedor(
            db,
            total_pago=Q(total_pago),
            cuenta_proveedores_codigo=cuenta_proveedores_codigo,
        )
        glosa = f"Pago proveedor {pago.proveedor_id} ref {pago.referencia or pago.id}"
        crear_asiento(
            db,
            fecha=pago.fecha_pago,
            origen_tipo="AP_PAGO",
            origen_id=int(pago.id),
            glosa=glosa[:255],
            detalles=detalles_asiento,
            usuario=user_email,
            moneda=str(pago.moneda),
            do_commit=False,
        )

        db.commit()
        db.refresh(pago)
        return pago

    def eliminar_documento(
        self,
        db: Session,
        documento_id: int,
        *,
        user_email: Optional[str] = None,
        ip_origen: Optional[str] = None,
    ) -> None:
        if not _cxp_tablas_ap_listas(db):
            raise ValueError(
                "Las tablas de cuentas por pagar no están creadas en la base de datos. "
                "Ejecute db/psql/096_grant_evalua_user_ap_fk.sql y python tools/create_fin_ap_tables.py."
            )
        documento = self.get_documento(db, documento_id)
        if not documento:
            raise ValueError("Documento no encontrado.")

        n_app = (
            db.query(func.count(APPagoAplicacion.id))
            .filter(APPagoAplicacion.documento_id == documento_id)
            .scalar()
            or 0
        )
        if int(n_app) > 0:
            raise ValueError("No se puede eliminar: existen pagos aplicados a este documento.")

        aplicado = _aplicado_a_documento(db, documento_id)
        vt = vista_totales_orm(documento, aplicado=aplicado)
        if aplicado > Z or Q(vt["saldo_pendiente"]) != Q(vt["total"]):
            raise ValueError(
                "No se puede eliminar: el documento tiene abonos o el saldo ya no es el total original."
            )

        self._validar_periodo_abierto(db, documento.fecha_emision)
        asiento_id = getattr(documento, "asiento_id", None)
        if asiento_id:
            eliminar_asiento_contable(db, int(asiento_id))

        self._log_evento(
            db,
            entidad="ap_documento",
            entidad_id=documento.id,
            evento="ELIMINADO",
            detalle=f"Eliminado documento {documento.tipo} folio {documento.folio}.",
            user_email=user_email,
            ip_origen=ip_origen,
        )
        db.delete(documento)
        db.commit()

    def serialize_detalles(self, documento: Any) -> list[dict[str, Any]]:
        if not documento:
            return []
        return [
            {
                "descripcion": det.descripcion or "",
                "cantidad": _decimal_str(det.cantidad),
                "precio_unitario": _decimal_str(det.precio_unitario),
                "descuento": _decimal_str(det.descuento),
                "categoria_gasto_id": det.categoria_gasto_id,
                "centro_costo_id": det.centro_costo_id,
            }
            for det in (documento.detalles or [])
        ]

    def serialize_impuestos(self, documento: Any) -> list[dict[str, Any]]:
        if not documento:
            return []
        return [
            {
                "tipo": str(imp.tipo) if imp.tipo is not None else "OTRO",
                "codigo": imp.codigo,
                "nombre": imp.nombre,
                "monto": _decimal_str(imp.monto),
            }
            for imp in (documento.impuestos or [])
        ]

    def proveedor_publico_id_de_documento(self, documento: Any) -> Optional[int]:
        if not documento:
            return None
        return getattr(documento, "proveedor_id", None)


cuentas_por_pagar = CuentasPorPagarCRUD()