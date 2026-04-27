# crud/finanzas/plan_cuentas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re

from sqlalchemy import func, inspect, or_, select, text
from sqlalchemy.orm import Session, selectinload

from models.finanzas.plan_cuentas import PlanCuenta
from schemas.finanzas.plan_cuentas import PlanCuentaCreate, PlanCuentaUpdate


TIPOS_PLAN_CUENTA = {"ACTIVO", "PASIVO", "PATRIMONIO", "INGRESO", "COSTO", "GASTO", "ORDEN"}
NATURALEZAS_PLAN_CUENTA = {"DEUDORA", "ACREEDORA"}
ESTADOS_PLAN_CUENTA = {"ACTIVO", "INACTIVO"}
CODIGO_CUENTA_REGEX = re.compile(r"^\d{6}$")
CODIGO_CUENTA_ERROR = "El código de cuenta debe tener 6 dígitos y no debe incluir puntos."


def _validar_catalogos_plan_cuenta(*, tipo: str, naturaleza: str, estado: str) -> None:
    if tipo not in TIPOS_PLAN_CUENTA:
        raise ValueError(f"Tipo de cuenta no permitido: {tipo}")
    if naturaleza not in NATURALEZAS_PLAN_CUENTA:
        raise ValueError(f"Naturaleza de cuenta no permitida: {naturaleza}")
    if estado not in ESTADOS_PLAN_CUENTA:
        raise ValueError(f"Estado de cuenta no permitido: {estado}")


def _tiene_hijos(db: Session, *, cuenta_id: int) -> bool:
    stmt = select(func.count()).select_from(PlanCuenta).where(PlanCuenta.cuenta_padre_id == cuenta_id)
    return bool(db.execute(stmt).scalar_one())


def _normalizar_codigo_payload(codigo: str) -> str:
    normalized = (codigo or "").strip()
    if not CODIGO_CUENTA_REGEX.fullmatch(normalized):
        raise ValueError(CODIGO_CUENTA_ERROR)
    return normalized


def _has_column(inspector, *, schema: str, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table, schema=schema))


def _cuenta_esta_en_config_o_asientos(db: Session, *, codigo_cuenta: str) -> bool:
    inspector = inspect(db.bind)
    has_cfg = inspector.has_table("config_contable", schema="fin")
    has_cfg_mod = inspector.has_table("config_contable_detalle_modulo", schema="fin")
    has_asiento_det = inspector.has_table("asientos_detalle", schema="public")

    if has_cfg:
        used_cfg = db.execute(
            text(
                """
                SELECT 1
                FROM fin.config_contable
                WHERE codigo_cuenta = :codigo AND estado = 'ACTIVO'
                LIMIT 1
                """
            ),
            {"codigo": codigo_cuenta},
        ).scalar()
        if used_cfg:
            return True

    if has_cfg_mod:
        used_cfg_mod = db.execute(
            text(
                """
                SELECT 1
                FROM fin.config_contable_detalle_modulo
                WHERE codigo_cuenta = :codigo AND estado = 'ACTIVO'
                LIMIT 1
                """
            ),
            {"codigo": codigo_cuenta},
        ).scalar()
        if used_cfg_mod:
            return True

    if has_asiento_det:
        has_codigo_cuenta = _has_column(
            inspector, schema="public", table="asientos_detalle", column="codigo_cuenta"
        )
        has_cuenta_contable = _has_column(
            inspector, schema="public", table="asientos_detalle", column="cuenta_contable"
        )
        if has_codigo_cuenta:
            used_asientos = db.execute(
                text(
                    """
                    SELECT 1
                    FROM public.asientos_detalle
                    WHERE codigo_cuenta = :codigo
                    LIMIT 1
                    """
                ),
                {"codigo": codigo_cuenta},
            ).scalar()
            if used_asientos:
                return True
        if has_cuenta_contable:
            used_asientos_alt = db.execute(
                text(
                    """
                    SELECT 1
                    FROM public.asientos_detalle
                    WHERE cuenta_contable = :codigo
                    LIMIT 1
                    """
                ),
                {"codigo": codigo_cuenta},
            ).scalar()
            if used_asientos_alt:
                return True

    has_ap_documento = inspector.has_table("ap_documento", schema="fin")
    if has_ap_documento:
        has_gasto = _has_column(
            inspector, schema="fin", table="ap_documento", column="cuenta_gasto_codigo"
        )
        has_proveedor = _has_column(
            inspector, schema="fin", table="ap_documento", column="cuenta_proveedores_codigo"
        )
        if has_gasto:
            used_ap_gasto = db.execute(
                text(
                    """
                    SELECT 1
                    FROM fin.ap_documento
                    WHERE cuenta_gasto_codigo = :codigo
                    LIMIT 1
                    """
                ),
                {"codigo": codigo_cuenta},
            ).scalar()
            if used_ap_gasto:
                return True
        if has_proveedor:
            used_ap_prov = db.execute(
                text(
                    """
                    SELECT 1
                    FROM fin.ap_documento
                    WHERE cuenta_proveedores_codigo = :codigo
                    LIMIT 1
                    """
                ),
                {"codigo": codigo_cuenta},
            ).scalar()
            if used_ap_prov:
                return True

    return False


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
    codigo = _normalizar_codigo_payload(payload.codigo)
    existente = obtener_plan_cuenta_por_codigo(db, codigo)
    if existente:
        raise ValueError(f"Ya existe una cuenta con código {payload.codigo}.")

    cuenta = PlanCuenta(
        codigo=codigo,
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
    _validar_catalogos_plan_cuenta(tipo=cuenta.tipo, naturaleza=cuenta.naturaleza, estado=cuenta.estado)

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
        nuevo_codigo = _normalizar_codigo_payload(str(data["codigo"]))
        existente = obtener_plan_cuenta_por_codigo(db, nuevo_codigo)
        if existente and existente.id != cuenta.id:
            raise ValueError(f"Ya existe una cuenta con código {nuevo_codigo}.")
        if nuevo_codigo != cuenta.codigo and _cuenta_esta_en_config_o_asientos(db, codigo_cuenta=cuenta.codigo):
            raise ValueError(
                "No se puede cambiar el código de una cuenta con referencias en asientos o configuración. "
                "Debe ejecutar una migración explícita."
            )
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
        if data["acepta_movimiento"] and _tiene_hijos(db, cuenta_id=cuenta.id):
            raise ValueError("Una cuenta con hijos no puede aceptar movimiento.")
        cuenta.acepta_movimiento = data["acepta_movimiento"]

    if "requiere_centro_costo" in data and data["requiere_centro_costo"] is not None:
        cuenta.requiere_centro_costo = data["requiere_centro_costo"]

    if "estado" in data and data["estado"] is not None:
        nuevo_estado = data["estado"].strip().upper()
        if nuevo_estado == "INACTIVO" and _cuenta_esta_en_config_o_asientos(db, codigo_cuenta=cuenta.codigo):
            raise ValueError(
                "No se puede desactivar la cuenta: está en configuración contable activa o tiene asientos."
            )
        cuenta.estado = nuevo_estado

    if "descripcion" in data:
        cuenta.descripcion = (data["descripcion"] or "").strip() or None

    _validar_catalogos_plan_cuenta(tipo=cuenta.tipo, naturaleza=cuenta.naturaleza, estado=cuenta.estado)
    if cuenta.acepta_movimiento and _tiene_hijos(db, cuenta_id=cuenta.id):
        raise ValueError("Una cuenta con hijos no puede aceptar movimiento.")

    db.add(cuenta)
    db.commit()
    db.refresh(cuenta)
    return cuenta


def desactivar_plan_cuenta(db: Session, *, cuenta: PlanCuenta) -> PlanCuenta:
    if _cuenta_esta_en_config_o_asientos(db, codigo_cuenta=cuenta.codigo):
        raise ValueError(
            "No se puede desactivar la cuenta: está en configuración contable activa o tiene asientos."
        )
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