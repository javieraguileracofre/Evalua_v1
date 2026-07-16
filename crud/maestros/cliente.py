# crud/maestros/cliente.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import func, or_, select, text
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

from core.validators import normalizar_texto, rut_para_busqueda
from models.maestros.cliente import Cliente
from models.maestros.cliente_extendido import ClienteAuditoria, ClienteDireccion
from schemas.maestros.cliente import ClienteCreate, ClienteUpdate


@dataclass(frozen=True)
class ClienteDeleteResult:
    accion: Literal["eliminado", "desactivado"]
    mensaje: str


def _norm_str(value: str | None) -> str | None:
    return normalizar_texto(value)


def get_cliente(db: Session, cliente_id: int) -> "ModelCliente | None":
    return db.get(Cliente, cliente_id)


def get_cliente_por_rut(db: Session, rut: str) -> "ModelCliente | None":
    rut_norm = rut_para_busqueda(rut)
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
        q = _norm_str(busqueda) or ""
        pattern = f"%{q}%"
        condiciones = [
            Cliente.razon_social.ilike(pattern),
            Cliente.rut.ilike(pattern),
            Cliente.nombre_fantasia.ilike(pattern),
            Cliente.comuna.ilike(pattern),
            Cliente.ciudad.ilike(pattern),
        ]
        rut_q = rut_para_busqueda(busqueda)
        if rut_q:
            condiciones.append(Cliente.rut == rut_q)
        stmt = stmt.where(or_(*condiciones))

    stmt = stmt.order_by(Cliente.razon_social.asc()).offset(sk).limit(lim + 1)
    rows = list(db.scalars(stmt))
    hay_mas = len(rows) > lim
    return rows[:lim], hay_mas


def _registrar_auditoria(
    db: Session,
    *,
    cliente_id: int,
    campo: str,
    valor_anterior: object,
    valor_nuevo: object,
    usuario: str = "sistema",
) -> None:
    ant = "" if valor_anterior is None else str(valor_anterior)
    nue = "" if valor_nuevo is None else str(valor_nuevo)
    if ant == nue:
        return
    db.add(
        ClienteAuditoria(
            cliente_id=cliente_id,
            campo=campo,
            valor_anterior=ant or None,
            valor_nuevo=nue or None,
            usuario=usuario,
        )
    )


def _sync_direccion_principal(db: Session, cliente: Cliente) -> None:
    if not cliente.direccion:
        return
    principal = next((d for d in cliente.direcciones if d.es_principal and d.activo), None)
    if principal:
        principal.direccion = cliente.direccion
        principal.comuna = cliente.comuna
        principal.ciudad = cliente.ciudad
        principal.region = cliente.region
        return
    db.add(
        ClienteDireccion(
            cliente_id=int(cliente.id),
            tipo="COMERCIAL",
            direccion=cliente.direccion,
            comuna=cliente.comuna,
            ciudad=cliente.ciudad,
            region=cliente.region,
            es_principal=True,
            activo=True,
        )
    )


def crear_cliente(db: Session, data: "SchemaClienteCreate", *, usuario: str = "sistema") -> "ModelCliente":
    payload = data.model_dump()
    payload["rut"] = rut_para_busqueda(payload["rut"])

    existente = get_cliente_por_rut(db, payload["rut"])
    if existente:
        raise ValueError(f"Ya existe un cliente con el RUT '{payload['rut']}'.")

    db_cliente = Cliente(**payload)
    db.add(db_cliente)

    try:
        db.flush()
        _sync_direccion_principal(db, db_cliente)
        _registrar_auditoria(
            db,
            cliente_id=int(db_cliente.id),
            campo="CREACION",
            valor_anterior=None,
            valor_nuevo=db_cliente.razon_social,
            usuario=usuario,
        )
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
    *,
    usuario: str = "sistema",
) -> "ModelCliente":
    cambios = data.model_dump(exclude_unset=True)
    audit_fields = {
        "tipo_persona",
        "razon_social",
        "nombres",
        "apellido_paterno",
        "apellido_materno",
        "nombre_fantasia",
        "giro",
        "direccion",
        "comuna",
        "ciudad",
        "region",
        "representante_legal_nombre",
        "representante_legal_rut",
        "telefono",
        "email",
        "activo",
    }

    for field, value in cambios.items():
        if field in audit_fields:
            prev = getattr(cliente, field, None)
            if field in {
                "razon_social",
                "nombres",
                "apellido_paterno",
                "apellido_materno",
                "nombre_fantasia",
                "giro",
                "direccion",
                "comuna",
                "ciudad",
                "region",
                "representante_legal_nombre",
                "telefono",
            }:
                new_val = _norm_str(value) or None
            elif field == "email":
                new_val = _norm_str(value) or None
            else:
                new_val = value
            _registrar_auditoria(
                db,
                cliente_id=int(cliente.id),
                campo=field,
                valor_anterior=prev,
                valor_nuevo=new_val,
                usuario=usuario,
            )
            setattr(cliente, field, new_val)
        elif field == "email":
            setattr(cliente, field, _norm_str(value) or None)
        else:
            setattr(cliente, field, value)

    if not normalizar_texto(cliente.razon_social):
        raise ValueError("La razón social es obligatoria.")

    _sync_direccion_principal(db, cliente)

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