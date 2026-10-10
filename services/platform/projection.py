# services/platform/projection.py
# -*- coding: utf-8 -*-
"""Proyecta la membresía en auth_* de la base de la compañía. No copia la clave."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.auth.modulo_visible import UsuarioModuloVisible
from models.auth.usuario import Rol, Usuario
from models.identity.models import IdentityUser, Membership

UNUSABLE_PASSWORD = "!not-a-local-login"


def project_membership(company_db: Session, user: IdentityUser, membership: Membership) -> Usuario:
    local = company_db.execute(
        select(Usuario).where(Usuario.identity_user_id == int(user.id))
    ).scalar_one_or_none()
    if local is None:
        local = company_db.execute(
            select(Usuario).where(Usuario.email == user.email)
        ).scalar_one_or_none()
    if local is None:
        local = Usuario(
            email=user.email,
            password_hash=UNUSABLE_PASSWORD,
            nombre_completo=user.nombre_completo,
            activo=True,
            session_version=int(user.session_version or 1),
            identity_user_id=int(user.id),
        )
        company_db.add(local)
        company_db.flush()
    local.email = user.email
    local.nombre_completo = user.nombre_completo
    local.activo = bool(user.activo) and membership.status == "ACTIVE"
    local.identity_user_id = int(user.id)
    local.password_hash = UNUSABLE_PASSWORD
    local.session_version = int(user.session_version or 1)

    wanted = {str(code).strip().upper() for code in (membership.role_codes or []) if str(code).strip()}
    roles = company_db.execute(select(Rol).where(Rol.codigo.in_(wanted))).scalars().all() if wanted else []
    local.roles = list(roles)

    company_db.query(UsuarioModuloVisible).filter(UsuarioModuloVisible.usuario_id == local.id).delete(
        synchronize_session=False
    )
    for key in membership.module_keys or []:
        code = str(key).strip().upper()
        if code:
            company_db.add(UsuarioModuloVisible(usuario_id=int(local.id), module_key=code))
    company_db.flush()
    return local
