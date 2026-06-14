# services/leasing_operativo_contabilidad.py
# -*- coding: utf-8 -*-
"""Contabilidad leasing operativo: activación, facturación mensual y depreciación."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from crud.finanzas.config_contable import obtener_configuracion_evento_modulo
from crud.finanzas.contabilidad_asientos import crear_asiento
from models.cobranza.cuentas_por_cobrar import CuentaPorCobrar
from models.leasing_operativo.models import LeasingOpContrato, LeasingOpCuota, LeasingOpGestionEvento, LeasingOpSimulacion


def resolver_monto_regla_evento(
    *,
    codigo_evento: str,
    regla: dict[str, Any],
    monto_base: Decimal,
    monto_iva: Decimal,
) -> Decimal:
    lado = str(regla.get("lado") or "").strip().upper()
    tipo = str(regla.get("tipo") or "").strip().upper()
    clasificacion = str(regla.get("clasificacion") or "").strip().upper()
    texto = " ".join(
        [
            str(regla.get("nombre_evento") or ""),
            str(regla.get("descripcion") or ""),
            str(regla.get("nombre_cuenta") or ""),
            str(regla.get("codigo_cuenta") or ""),
        ]
    ).upper()
    total = (monto_base + monto_iva).quantize(Decimal("0.01"))

    if codigo_evento == "LOP_FACTURACION":
        if lado == "DEBE":
            if tipo == "ACTIVO" or clasificacion.startswith("ACTIVO"):
                return total
            if any(token in texto for token in ("CLIENTE", "COBRAR", "CXC", "113801", "110301")):
                return total
            return monto_base
        if lado == "HABER":
            if "IVA" in texto or tipo == "PASIVO" or clasificacion.startswith("PASIVO"):
                return monto_iva
            return monto_base
        return Decimal("0")

    if codigo_evento in {"LOP_ACTIVACION", "LOP_DEPRECIACION"}:
        return monto_base

    orden = int(regla.get("orden") or 1)
    if orden == 2:
        return monto_iva
    return monto_base


def crear_asiento_desde_config_evento(
    db: Session,
    *,
    modulo: str,
    submodulo: str,
    tipo_documento: str,
    codigo_evento: str,
    monto_base: Decimal,
    monto_iva: Decimal = Decimal("0"),
    fecha: date | None = None,
    origen_tipo: str,
    origen_id: int,
    glosa: str,
    usuario: str | None = None,
) -> int | None:
    reglas = obtener_configuracion_evento_modulo(
        db,
        modulo=modulo,
        submodulo=submodulo,
        tipo_documento=tipo_documento,
        codigo_evento=codigo_evento,
    )
    if not reglas:
        return None
    detalles: list[dict[str, Any]] = []
    for r in reglas:
        lado = str(r.get("lado") or "").upper()
        if lado not in {"DEBE", "HABER"}:
            continue
        monto = resolver_monto_regla_evento(
            codigo_evento=codigo_evento,
            regla=r,
            monto_base=monto_base,
            monto_iva=monto_iva,
        )
        if monto <= 0:
            continue
        codigo_cuenta = str(r.get("codigo_cuenta") or "").strip()
        if not codigo_cuenta:
            continue
        detalles.append(
            {
                "codigo_cuenta": codigo_cuenta,
                "descripcion": glosa[:120],
                "debe": monto if lado == "DEBE" else Decimal("0"),
                "haber": monto if lado == "HABER" else Decimal("0"),
            }
        )
    if not detalles:
        return None
    return crear_asiento(
        db,
        fecha=fecha or datetime.now(timezone.utc).date(),
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        glosa=glosa[:255],
        detalles=detalles,
        usuario=usuario,
        moneda="CLP",
        do_commit=False,
    )


def registrar_asiento_activacion(
    db: Session,
    sim: LeasingOpSimulacion,
    *,
    contrato_id: int,
    factura_compra: dict[str, Any],
    usuario: str,
) -> int | None:
    """Asiento de activación del activo (sin CxC anticipada — facturación es mensual)."""
    total = Decimal(str(factura_compra.get("total") or 0))
    iva = Decimal(str(factura_compra.get("iva") or 0))
    base = total - iva if total > iva else total
    return crear_asiento_desde_config_evento(
        db,
        modulo="LEASING_OP",
        submodulo="ACTIVACION",
        tipo_documento="CONTRATO",
        codigo_evento="LOP_ACTIVACION",
        monto_base=base,
        monto_iva=Decimal("0"),
        fecha=datetime.now(timezone.utc).date(),
        origen_tipo="LOP_ACTIVACION",
        origen_id=int(contrato_id),
        glosa=f"Activación contable leasing operativo contrato {contrato_id}",
        usuario=usuario,
    )


def _ref_cxc_cuota(contrato_id: int, nro_cuota: int) -> str:
    return f"LOP_FACT:{int(contrato_id)}:CUOTA:{int(nro_cuota)}"


def facturar_cuota_individual(
    db: Session,
    *,
    contrato: LeasingOpContrato,
    cuota: LeasingOpCuota,
    sim: LeasingOpSimulacion,
    iva_pct: Decimal,
    usuario: str,
) -> dict[str, Any] | None:
    """Crea CxC + asiento de ingreso para una cuota. Idempotente por referencia."""
    if not sim.cliente_id:
        return None
    if str(cuota.estado or "").upper() == "PAGADA":
        return None
    ref = _ref_cxc_cuota(int(contrato.id), int(cuota.nro))
    exists = db.scalars(
        select(CuentaPorCobrar).where(
            CuentaPorCobrar.cliente_id == int(sim.cliente_id),
            CuentaPorCobrar.observacion == ref,
        ).limit(1)
    ).first()
    if exists:
        cuota.estado = "FACTURADA"
        cuota.cxc_id = int(exists.id)
        cuota.facturado_en = datetime.now(timezone.utc)
        db.add(cuota)
        return {"cuota_nro": int(cuota.nro), "cxc_id": int(exists.id), "asiento_id": None, "reused": True}

    iva_factor = iva_pct / Decimal("100")
    neto = Decimal(str(cuota.monto_renta or 0)).quantize(Decimal("0.01"))
    iva = (neto * iva_factor).quantize(Decimal("0.01"))
    bruto = (neto + iva).quantize(Decimal("0.01"))
    cxc = CuentaPorCobrar(
        cliente_id=int(sim.cliente_id),
        nota_venta_id=None,
        fecha_emision=cuota.fecha_vencimiento,
        fecha_vencimiento=cuota.fecha_vencimiento,
        monto_original=bruto,
        saldo_pendiente=bruto,
        estado="PENDIENTE",
        observacion=ref,
    )
    db.add(cxc)
    db.flush()
    aid = crear_asiento_desde_config_evento(
        db,
        modulo="LEASING_OP",
        submodulo="FACTURACION",
        tipo_documento="CUOTA",
        codigo_evento="LOP_FACTURACION",
        monto_base=neto,
        monto_iva=iva,
        fecha=cuota.fecha_vencimiento,
        origen_tipo="LOP_FACTURACION",
        origen_id=int(contrato.id),
        glosa=f"Facturación cuota {cuota.nro} contrato {contrato.codigo}",
        usuario=usuario,
    )
    cuota.estado = "FACTURADA"
    cuota.cxc_id = int(cxc.id)
    cuota.facturado_en = datetime.now(timezone.utc)
    db.add(cuota)
    return {"cuota_nro": int(cuota.nro), "cxc_id": int(cxc.id), "asiento_id": aid, "reused": False}


def marcar_cuota_pagada_por_cxc(db: Session, cxc_id: int, *, usuario: str = "cobranza") -> int:
    """Marca cuota LOP como PAGADA cuando la CxC queda saldada (hook cobranza)."""
    cxc = db.get(CuentaPorCobrar, cxc_id)
    if not cxc:
        return 0
    obs = str(cxc.observacion or "")
    if not obs.startswith("LOP_FACT:"):
        return 0
    if Decimal(str(cxc.saldo_pendiente or 0)) > 0:
        return 0
    parts = obs.split(":")
    if len(parts) < 4:
        return 0
    try:
        contrato_id = int(parts[1])
        nro = int(parts[3])
    except ValueError:
        return 0
    cuota = db.scalars(
        select(LeasingOpCuota).where(
            LeasingOpCuota.contrato_id == contrato_id,
            LeasingOpCuota.nro == nro,
        ).limit(1)
    ).first()
    if not cuota:
        return 0
    cuota.estado = "PAGADA"
    db.add(cuota)

    db.add(
        LeasingOpGestionEvento(
            contrato_id=contrato_id,
            cuota_id=int(cuota.id),
            tipo="PAGO_COBRANZA",
            estado="CERRADO",
            payload_json={"cxc_id": int(cxc_id), "cuota_nro": nro},
            usuario=usuario,
        )
    )

    contrato = db.get(LeasingOpContrato, contrato_id)
    if contrato and str(contrato.estado or "").upper() == "MORA":
        abiertas = db.scalars(
            select(LeasingOpCuota).where(
                LeasingOpCuota.contrato_id == contrato_id,
                LeasingOpCuota.estado.in_(("MORA", "FACTURADA")),
            )
        ).all()
        if not list(abiertas):
            contrato.estado = "VIGENTE"
            db.add(contrato)

    return 1


def sincronizar_cobranza_lop(db: Session, cxc_id: int, *, usuario: str = "cobranza") -> dict[str, int]:
    """Hook unificado post-pago cobranza para referencias LOP."""
    n = marcar_cuota_pagada_por_cxc(db, cxc_id, usuario=usuario)
    return {"cuotas_actualizadas": n}
