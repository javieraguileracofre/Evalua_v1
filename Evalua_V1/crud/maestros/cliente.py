# crud/maestros/cliente.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from models.maestros.cliente import Cliente as ModelCliente
    from schemas.maestros.cliente import (
        ClienteCreate as SchemaClienteCreate,
        ClienteUpdate as SchemaClienteUpdate,
    )
else:
    ModelCliente = Any
    SchemaClienteCreate = Any
    SchemaClienteUpdate = Any

from models.maestros.cliente import Cliente
from schemas.maestros.cliente import ClienteCreate, ClienteUpdate


@dataclass(frozen=True)
class ClienteDeleteResult:
    accion: Literal["eliminado", "desactivado"]
    mensaje: str


def _norm_str(value: str | None) -> str:
    return (value or "").strip()


def _norm_upper(value: str | None) -> str:
    return _norm_str(value).upper()


def get_cliente(db: Session, cliente_id: int) -> "ModelCliente | None":
    return db.get(Cliente, cliente_id)


def get_cliente_por_rut(db: Session, rut: str) -> "ModelCliente | None":
    rut_norm = _norm_upper(rut)
    if not rut_norm:
        return None

    stmt = select(Cliente).where(Cliente.rut == rut_norm)
    return db.scalar(stmt)


def listar_clientes(
    db: Session,
    *,
    activos_solo: bool = False,
    busqueda: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list["ModelCliente"], bool]:
    """
    Lista clientes con paginación.

    Devuelve (filas, hay_mas) usando ``limit + 1`` filas.
    """
    lim = max(1, min(int(limit), 500))
    sk = max(0, int(skip))
    stmt = select(Cliente)

    if activos_solo:
        stmt = stmt.where(Cliente.activo.is_(True))

    if busqueda:
        pattern = f"%{_norm_str(busqueda)}%"
        stmt = stmt.where(
            (Cliente.razon_social.ilike(pattern))
            | (Cliente.rut.ilike(pattern))
            | (Cliente.nombre_fantasia.ilike(pattern))
        )

    stmt = stmt.order_by(Cliente.razon_social.asc()).offset(sk).limit(lim + 1)
    rows = list(db.scalars(stmt))
    hay_mas = len(rows) > lim
    return rows[:lim], hay_mas


def crear_cliente(db: Session, data: "SchemaClienteCreate") -> "ModelCliente":
    payload = data.model_dump()

    payload["rut"] = _norm_upper(payload.get("rut"))
    payload["razon_social"] = _norm_str(payload.get("razon_social"))
    payload["nombre_fantasia"] = _norm_str(payload.get("nombre_fantasia")) or None
    payload["giro"] = _norm_str(payload.get("giro")) or None
    payload["direccion"] = _norm_str(payload.get("direccion")) or None
    payload["comuna"] = _norm_str(payload.get("comuna")) or None
    payload["ciudad"] = _norm_str(payload.get("ciudad")) or None
    payload["telefono"] = _norm_str(payload.get("telefono")) or None
    payload["email"] = _norm_str(payload.get("email")) or None

    if not payload["rut"]:
        raise ValueError("El RUT es obligatorio.")

    if not payload["razon_social"]:
        raise ValueError("La razón social es obligatoria.")

    existente = get_cliente_por_rut(db, payload["rut"])
    if existente:
        raise ValueError(f"Ya existe un cliente con el RUT '{payload['rut']}'.")

    db_cliente = Cliente(**payload)
    db.add(db_cliente)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("No fue posible crear el cliente por una restricción de base de datos.")

    db.refresh(db_cliente)
    return db_cliente


def actualizar_cliente(
    db: Session,
    cliente: "ModelCliente",
    data: "SchemaClienteUpdate",
) -> "ModelCliente":
    cambios = data.model_dump(exclude_unset=True)

    for field, value in cambios.items():
        if field in {
            "razon_social",
            "nombre_fantasia",
            "giro",
            "direccion",
            "comuna",
            "ciudad",
            "telefono",
        }:
            setattr(cliente, field, _norm_str(value) or None)
        elif field == "email":
            setattr(cliente, field, _norm_str(value) or None)
        else:
            setattr(cliente, field, value)

    if not _norm_str(cliente.razon_social):
        raise ValueError("La razón social es obligatoria.")

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("No fue posible actualizar el cliente por una restricción de base de datos.")

    db.refresh(cliente)
    return cliente


def desactivar_cliente(db: Session, cliente: "ModelCliente") -> "ModelCliente":
    if cliente.activo:
        cliente.activo = False
        db.commit()
        db.refresh(cliente)
    return cliente


def _count_cxc_por_cliente(db: Session, cliente_id: int) -> int:
    try:
        from models.cobranza.cuentas_por_cobrar import CuentaPorCobrar

        stmt = (
            select(func.count())
            .select_from(CuentaPorCobrar)
            .where(CuentaPorCobrar.cliente_id == cliente_id)
        )
        return int(db.execute(stmt).scalar() or 0)
    except Exception:
        stmt = text(
            "SELECT COUNT(1) FROM cuentas_por_cobrar WHERE cliente_id = :cliente_id"
        )
        return int(db.execute(stmt, {"cliente_id": cliente_id}).scalar() or 0)


def eliminar_cliente(db: Session, cliente: "ModelCliente") -> ClienteDeleteResult:
    cxc_count = _count_cxc_por_cliente(db, cliente.id)

    if cxc_count > 0:
        desactivar_cliente(db, cliente)
        return ClienteDeleteResult(
            accion="desactivado",
            mensaje=(
                f"No se puede eliminar el cliente porque tiene {cxc_count} documento(s) asociado(s). "
                "Se desactivó automáticamente."
            ),
        )

    try:
        db.delete(cliente)
        db.commit()
        return ClienteDeleteResult(
            accion="eliminado",
            mensaje="Cliente eliminado correctamente.",
        )
    except IntegrityError:
        db.rollback()
        desactivar_cliente(db, cliente)
        return ClienteDeleteResult(
            accion="desactivado",
            mensaje=(
                "No se puede eliminar el cliente porque tiene información relacionada en el sistema. "
                "Se desactivó automáticamente."
            ),
        )