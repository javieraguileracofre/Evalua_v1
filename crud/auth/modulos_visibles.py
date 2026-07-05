# crud/auth/modulos_visibles.py
# -*- coding: utf-8 -*-
"""Persistencia de módulos visibles en el menú por usuario."""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from core.module_catalog import (
    ALL_MODULE_KEYS,
    default_visible_modules_for_roles,
    normalize_module_keys,
)
from core.rbac import usuario_es_admin
from models.auth.modulo_visible import UsuarioModuloVisible
from models.auth.usuario import Usuario


def _auth_dict_from_usuario(usuario: Usuario) -> dict:
    from crud.auth.usuarios import listar_roles_codigos

    return {"roles": listar_roles_codigos(usuario)}


def visible_module_keys(usuario: Usuario, db: Session) -> frozenset[str]:
    if usuario_es_admin(_auth_dict_from_usuario(usuario)):
        return frozenset(ALL_MODULE_KEYS)
    rows = db.execute(
        select(UsuarioModuloVisible.module_key).where(UsuarioModuloVisible.usuario_id == usuario.id)
    ).scalars().all()
    return frozenset(str(k).upper() for k in rows if k)


def user_visible_modules_list(usuario: Usuario, db: Session) -> list[str]:
    keys = visible_module_keys(usuario, db)
    order = {k: i for i, k in enumerate(ALL_MODULE_KEYS)}
    return sorted(keys, key=lambda k: order.get(k, 999))


def set_user_visible_modules(
    db: Session,
    usuario: Usuario,
    module_keys: list[str],
    *,
    assigned_by_id: int | None = None,
) -> list[str]:
    normalized = normalize_module_keys(module_keys)
    db.execute(delete(UsuarioModuloVisible).where(UsuarioModuloVisible.usuario_id == usuario.id))
    db.flush()
    for key in normalized:
        db.add(
            UsuarioModuloVisible(
                usuario_id=int(usuario.id),
                module_key=key,
                assigned_by_id=assigned_by_id,
            )
        )
    db.flush()
    db.expire(usuario, ["modulos_visibles"])
    return normalized


def resolve_visible_modules_for_user(
    db: Session,
    usuario: Usuario,
    explicit_modules: list[str] | None,
) -> list[str]:
    """Si hay módulos explícitos los guarda; si no, aplica defaults por rol."""
    if explicit_modules is not None:
        keys = explicit_modules if explicit_modules else []
        return set_user_visible_modules(db, usuario, keys)
    existing = visible_module_keys(usuario, db)
    if existing:
        return sorted(existing)
    from crud.auth.usuarios import listar_roles_codigos

    defaults = default_visible_modules_for_roles(listar_roles_codigos(usuario))
    return set_user_visible_modules(db, usuario, sorted(defaults))


def backfill_visible_modules_from_roles(db: Session) -> int:
    """Usuarios sin filas en auth_usuario_modulo_visible reciben defaults según roles."""
    users = (
        db.execute(select(Usuario).options(selectinload(Usuario.roles)))
        .unique()
        .scalars()
        .all()
    )
    updated = 0
    for user in users:
        count = db.execute(
            select(func.count())
            .select_from(UsuarioModuloVisible)
            .where(UsuarioModuloVisible.usuario_id == user.id)
        ).scalar_one()
        if int(count or 0) > 0:
            continue
        from crud.auth.usuarios import listar_roles_codigos

        defaults = default_visible_modules_for_roles(listar_roles_codigos(user))
        if defaults:
            set_user_visible_modules(db, user, sorted(defaults))
            updated += 1
    return updated
