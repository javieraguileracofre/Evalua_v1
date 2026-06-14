# services/leasing_operativo/gestion_cartera.py
# -*- coding: utf-8 -*-
"""Mora, terminación anticipada, repossession y remarketing — leasing operativo."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.cobranza.cuentas_por_cobrar import CuentaPorCobrar
from models.leasing_operativo.models import (
    LeasingOpActivoFijo,
    LeasingOpContrato,
    LeasingOpCuota,
    LeasingOpGestionEvento,
    LeasingOpSimulacion,
)

def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _politica_mora(politica: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return politica.get("mora_v1") or {
        "tasa_mora_mensual_pct": 1.5,
        "tasa_mora_diaria_pct": 0.05,
        "dias_gracia": 5,
        "mora_sobre": "NETO",
        "generar_cxc_mora": True,
    }


def _politica_terminacion(politica: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return politica.get("terminacion_v1") or {
        "penalidad_pct_rentas_pendientes": 50,
        "penalidad_pct_capex_remanente": 8,
        "incluir_iva_penalidad": True,
        "requiere_repossession": False,
    }


def calcular_mora_cuota(
    *,
    cuota: LeasingOpCuota,
    dias_mora: int,
    politica_mora: dict[str, Any],
) -> Decimal:
    if dias_mora <= 0:
        return Decimal("0")
    base = Decimal(str(cuota.monto_renta or 0))
    if str(politica_mora.get("mora_sobre") or "NETO").upper() == "BRUTO":
        iva_pct = Decimal("0")  # caller may pass bruto separately
        base = base  # noqa: PLW0127 — placeholder for extension
    tasa_d = Decimal(str(politica_mora.get("tasa_mora_diaria_pct") or 0)) / Decimal("100")
    return _q2(base * tasa_d * Decimal(dias_mora))


def procesar_mora_cartera(
    db: Session,
    *,
    politica: dict[str, dict[str, Any]],
    fecha_corte: date | None = None,
    usuario: str = "sistema",
) -> dict[str, Any]:
    """Marca cuotas vencidas en mora y registra eventos / CxC de intereses moratorios."""
    hoy = fecha_corte or datetime.now(timezone.utc).date()
    pm = _politica_mora(politica)
    dias_gracia = int(pm.get("dias_gracia") or 0)
    generar_cxc = bool(pm.get("generar_cxc_mora", True))
    procesadas = 0
    monto_total = Decimal("0")

    cuotas = list(
        db.scalars(
            select(LeasingOpCuota)
            .join(LeasingOpContrato, LeasingOpContrato.id == LeasingOpCuota.contrato_id)
            .where(
                LeasingOpContrato.estado == "VIGENTE",
                LeasingOpCuota.estado.in_(("FACTURADA", "MORA")),
            )
        ).all()
    )

    for q in cuotas:
        if q.fecha_vencimiento >= hoy:
            continue
        dias = (hoy - q.fecha_vencimiento).days - dias_gracia
        if dias <= 0:
            continue
        if int(q.dias_mora or 0) >= dias and str(q.estado or "").upper() == "MORA":
            continue

        mora = calcular_mora_cuota(cuota=q, dias_mora=dias, politica_mora=pm)
        q.estado = "MORA"
        q.dias_mora = dias
        q.monto_mora = mora
        q.fecha_mora_aplicada = hoy
        db.add(q)

        ctr = db.get(LeasingOpContrato, int(q.contrato_id))
        if ctr and str(ctr.estado or "").upper() == "VIGENTE":
            ctr.estado = "MORA"
            db.add(ctr)

        db.add(
            LeasingOpGestionEvento(
                contrato_id=int(q.contrato_id),
                cuota_id=int(q.id),
                tipo="MORA",
                estado="VIGENTE",
                dias_mora=dias,
                monto_mora=mora,
                payload_json={"cuota_nro": int(q.nro), "fecha_vencimiento": str(q.fecha_vencimiento)},
                usuario=usuario,
            )
        )

        if generar_cxc and mora > 0 and q.cxc_id:
            cxc_base = db.get(CuentaPorCobrar, int(q.cxc_id))
            sim = db.get(LeasingOpSimulacion, int(ctr.simulacion_id)) if ctr else None
            if cxc_base and sim and sim.cliente_id:
                ref = f"LOP_MORA:{int(q.contrato_id)}:CUOTA:{int(q.nro)}"
                exists = db.scalars(
                    select(CuentaPorCobrar).where(
                        CuentaPorCobrar.cliente_id == int(sim.cliente_id),
                        CuentaPorCobrar.observacion == ref,
                    ).limit(1)
                ).first()
                if not exists:
                    db.add(
                        CuentaPorCobrar(
                            cliente_id=int(sim.cliente_id),
                            fecha_emision=hoy,
                            fecha_vencimiento=hoy,
                            monto_original=mora,
                            saldo_pendiente=mora,
                            estado="PENDIENTE",
                            observacion=ref,
                        )
                    )
        procesadas += 1
        monto_total += mora

    return {"cuotas_mora": procesadas, "monto_mora_total": float(monto_total), "fecha_corte": str(hoy)}


def calcular_penalidad_terminacion(
    *,
    contrato: LeasingOpContrato,
    sim: LeasingOpSimulacion,
    politica_term: dict[str, Any],
) -> Decimal:
    res = sim.result_json or {}
    capex = Decimal(str(res.get("capex_total") or 0))
    pendientes = [
        q for q in (contrato.cuotas or []) if str(q.estado or "").upper() in {"PENDIENTE", "FACTURADA", "MORA"}
    ]
    rentas_pend = sum((Decimal(str(q.monto_renta or 0)) for q in pendientes), Decimal("0"))
    pct_rentas = Decimal(str(politica_term.get("penalidad_pct_rentas_pendientes") or 50)) / Decimal("100")
    pct_capex = Decimal(str(politica_term.get("penalidad_pct_capex_remanente") or 8)) / Decimal("100")
    pagadas = [q for q in (contrato.cuotas or []) if str(q.estado or "").upper() == "PAGADA"]
    n_pag = len(pagadas)
    n_total = max(len(contrato.cuotas or []), 1)
    remanente_capex = capex * Decimal(n_total - n_pag) / Decimal(n_total)
    return _q2(rentas_pend * pct_rentas + remanente_capex * pct_capex)


def registrar_terminacion_anticipada(
    db: Session,
    *,
    contrato: LeasingOpContrato,
    sim: LeasingOpSimulacion,
    politica: dict[str, dict[str, Any]],
    motivo: str,
    fecha: date | None = None,
    usuario: str = "sistema",
) -> dict[str, Any]:
    if str(contrato.estado or "").upper() not in {"VIGENTE", "MORA"}:
        raise ValueError("Solo contratos vigentes o en mora admiten terminación anticipada.")
    pt = _politica_terminacion(politica)
    penalidad = calcular_penalidad_terminacion(contrato=contrato, sim=sim, politica_term=pt)
    f = fecha or datetime.now(timezone.utc).date()

    for q in contrato.cuotas or []:
        if str(q.estado or "").upper() in {"PENDIENTE", "FACTURADA", "MORA"}:
            q.estado = "CANCELADA"
            db.add(q)

    contrato.estado = "TERMINADO_ANTICIPADO"
    contrato.fecha_termino = f
    contrato.motivo_termino = (motivo or "").strip()[:2000]
    db.add(contrato)

    ev = LeasingOpGestionEvento(
        contrato_id=int(contrato.id),
        tipo="TERMINACION_ANTICIPADA",
        estado="CERRADO",
        monto_penalidad=penalidad,
        payload_json={"motivo": contrato.motivo_termino, "cuotas_canceladas": True},
        usuario=usuario,
    )
    db.add(ev)

    cxc_penalidad_id = None
    if penalidad > 0 and sim.cliente_id:
        ref = f"LOP_TERM:{int(contrato.id)}"
        db.add(
            CuentaPorCobrar(
                cliente_id=int(sim.cliente_id),
                fecha_emision=f,
                fecha_vencimiento=f,
                monto_original=penalidad,
                saldo_pendiente=penalidad,
                estado="PENDIENTE",
                observacion=ref,
            )
        )
        db.flush()
        cxc_penalidad_id = None  # refreshed below if needed

    if bool(pt.get("requiere_repossession")):
        registrar_repossession(
            db,
            contrato=contrato,
            sim=sim,
            motivo=f"Terminación anticipada: {motivo}",
            usuario=usuario,
        )

    return {
        "contrato_id": int(contrato.id),
        "penalidad": float(penalidad),
        "fecha_termino": str(f),
        "evento": "TERMINACION_ANTICIPADA",
        "cxc_penalidad_ref": f"LOP_TERM:{int(contrato.id)}",
    }


def registrar_repossession(
    db: Session,
    *,
    contrato: LeasingOpContrato,
    sim: LeasingOpSimulacion,
    motivo: str,
    activo_id: int | None = None,
    usuario: str = "sistema",
) -> LeasingOpGestionEvento:
    contrato.estado = "EN_REPOSSESSION"
    db.add(contrato)

    activos: list[LeasingOpActivoFijo] = []
    if activo_id:
        af = db.get(LeasingOpActivoFijo, activo_id)
        if af:
            activos.append(af)
    else:
        activos = list(
            db.scalars(
                select(LeasingOpActivoFijo).where(LeasingOpActivoFijo.contrato_id == int(contrato.id))
            ).all()
        )

    ids = []
    for af in activos:
        af.estado = "REPOSSESSION"
        db.add(af)
        ids.append(int(af.id))

    ev = LeasingOpGestionEvento(
        contrato_id=int(contrato.id),
        tipo="REPOSSESSION",
        estado="VIGENTE",
        payload_json={"motivo": motivo, "activos_ids": ids},
        usuario=usuario,
    )
    db.add(ev)
    return ev


def registrar_remarketing(
    db: Session,
    *,
    contrato: LeasingOpContrato,
    valor_venta: Decimal,
    comprador: str,
    activo_id: int | None = None,
    costos_remarketing: Decimal = Decimal("0"),
    usuario: str = "sistema",
) -> dict[str, Any]:
    if str(contrato.estado or "").upper() not in {"EN_REPOSSESSION", "TERMINADO_ANTICIPADO", "MORA"}:
        raise ValueError("Remarketing requiere contrato en repossession, mora o terminado.")

    neto = _q2(valor_venta - costos_remarketing)
    ev = LeasingOpGestionEvento(
        contrato_id=int(contrato.id),
        tipo="REMARKETING",
        estado="CERRADO",
        monto_recupero=neto,
        payload_json={
            "valor_venta": float(valor_venta),
            "costos_remarketing": float(costos_remarketing),
            "comprador": (comprador or "").strip()[:200],
            "activo_id": activo_id,
        },
        usuario=usuario,
    )
    db.add(ev)

    if activo_id:
        af = db.get(LeasingOpActivoFijo, activo_id)
        if af:
            af.estado = "VENDIDO"
            af.valor_libro = Decimal("0")
            db.add(af)

    contrato.estado = "LIQUIDADO_REMARKETING"
    contrato.fecha_termino = datetime.now(timezone.utc).date()
    db.add(contrato)

    return {"contrato_id": int(contrato.id), "recupero_neto": float(neto), "evento_id": None}
