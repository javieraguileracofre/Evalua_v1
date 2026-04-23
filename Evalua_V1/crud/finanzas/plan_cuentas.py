# crud/finanzas/plan_cuentas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from models.finanzas.plan_cuentas import PlanCuenta
from schemas.finanzas.plan_cuentas import PlanCuentaCreate, PlanCuentaUpdate


def listar_plan_cuentas(
    db: Session,
    *,
    q: str | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    solo_movimiento: bool | None = None,
) -> list[PlanCuenta]:
    stmt = (
        select(PlanCuenta)
        .options(selectinload(PlanCuenta.padre))
        .order_by(PlanCuenta.codigo.asc())
    )

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                PlanCuenta.codigo.ilike(like),
                PlanCuenta.nombre.ilike(like),
                PlanCuenta.clasificacion.ilike(like),
            )
        )

    if tipo:
        stmt = stmt.where(func.upper(PlanCuenta.tipo) == tipo.strip().upper())

    if estado:
        stmt = stmt.where(func.upper(PlanCuenta.estado) == estado.strip().upper())

    if solo_movimiento is not None:
        stmt = stmt.where(PlanCuenta.acepta_movimiento.is_(solo_movimiento))

    return list(db.execute(stmt).scalars().all())


def obtener_plan_cuenta(db: Session, cuenta_id: int) -> PlanCuenta | None:
    stmt = (
        select(PlanCuenta)
        .options(selectinload(PlanCuenta.padre), selectinload(PlanCuenta.hijos))
        .where(PlanCuenta.id == cuenta_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def obtener_plan_cuenta_por_codigo(db: Session, codigo: str) -> PlanCuenta | None:
    stmt = select(PlanCuenta).where(PlanCuenta.codigo == codigo)
    return db.execute(stmt).scalar_one_or_none()


def crear_plan_cuenta(db: Session, payload: PlanCuentaCreate) -> PlanCuenta:
    existente = obtener_plan_cuenta_por_codigo(db, payload.codigo.strip())
    if existente:
        raise ValueError(f"Ya existe una cuenta con código {payload.codigo}.")

    cuenta = PlanCuenta(
        codigo=payload.codigo.strip(),
        nombre=payload.nombre.strip(),
        nivel=payload.nivel,
        cuenta_padre_id=payload.cuenta_padre_id,
        tipo=payload.tipo.strip().upper(),
        clasificacion=payload.clasificacion.strip().upper(),
        naturaleza=payload.naturaleza.strip().upper(),
        acepta_movimiento=payload.acepta_movimiento,
        requiere_centro_costo=payload.requiere_centro_costo,
        estado=payload.estado.strip().upper(),
        descripcion=(payload.descripcion or "").strip() or None,
    )

    db.add(cuenta)
    db.commit()
    db.refresh(cuenta)
    return cuenta


def actualizar_plan_cuenta(
    db: Session,
    *,
    cuenta: PlanCuenta,
    payload: PlanCuentaUpdate,
) -> PlanCuenta:
    data = payload.model_dump(exclude_unset=True)

    if "codigo" in data and data["codigo"]:
        nuevo_codigo = data["codigo"].strip()
        existente = obtener_plan_cuenta_por_codigo(db, nuevo_codigo)
        if existente and existente.id != cuenta.id:
            raise ValueError(f"Ya existe una cuenta con código {nuevo_codigo}.")
        cuenta.codigo = nuevo_codigo

    if "nombre" in data and data["nombre"] is not None:
        cuenta.nombre = data["nombre"].strip()

    if "nivel" in data and data["nivel"] is not None:
        cuenta.nivel = data["nivel"]

    if "cuenta_padre_id" in data:
        cuenta.cuenta_padre_id = data["cuenta_padre_id"]

    if "tipo" in data and data["tipo"] is not None:
        cuenta.tipo = data["tipo"].strip().upper()

    if "clasificacion" in data and data["clasificacion"] is not None:
        cuenta.clasificacion = data["clasificacion"].strip().upper()

    if "naturaleza" in data and data["naturaleza"] is not None:
        cuenta.naturaleza = data["naturaleza"].strip().upper()

    if "acepta_movimiento" in data and data["acepta_movimiento"] is not None:
        cuenta.acepta_movimiento = data["acepta_movimiento"]

    if "requiere_centro_costo" in data and data["requiere_centro_costo"] is not None:
        cuenta.requiere_centro_costo = data["requiere_centro_costo"]

    if "estado" in data and data["estado"] is not None:
        cuenta.estado = data["estado"].strip().upper()

    if "descripcion" in data:
        cuenta.descripcion = (data["descripcion"] or "").strip() or None

    db.add(cuenta)
    db.commit()
    db.refresh(cuenta)
    return cuenta


def desactivar_plan_cuenta(db: Session, *, cuenta: PlanCuenta) -> PlanCuenta:
    cuenta.estado = "INACTIVO"
    db.add(cuenta)
    db.commit()
    db.refresh(cuenta)
    return cuenta


def listar_cuentas_movimiento_activas(db: Session) -> list[PlanCuenta]:
    stmt = (
        select(PlanCuenta)
        .where(
            PlanCuenta.estado == "ACTIVO",
            PlanCuenta.acepta_movimiento.is_(True),
        )
        .order_by(PlanCuenta.codigo.asc())
    )
    return list(db.execute(stmt).scalars().all())