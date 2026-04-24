# crud/auth/__init__.py
# -*- coding: utf-8 -*-
from crud.auth.usuarios import (
    actualizar_ultimo_acceso,
    actualizar_usuario,
    autenticar,
    contar_admins_activos,
    contar_usuarios,
    crear_usuario,
    crear_usuario_admin,
    establecer_password,
    get_usuario_por_email,
    get_usuario_por_id,
    listar_roles,
    listar_roles_codigos,
    listar_usuarios,
    serializar_sesion_usuario,
)

__all__ = [
    "actualizar_ultimo_acceso",
    "actualizar_usuario",
    "autenticar",
    "contar_admins_activos",
    "contar_usuarios",
    "crear_usuario",
    "crear_usuario_admin",
    "establecer_password",
    "get_usuario_por_email",
    "get_usuario_por_id",
    "listar_roles",
    "listar_roles_codigos",
    "listar_usuarios",
    "serializar_sesion_usuario",
]
