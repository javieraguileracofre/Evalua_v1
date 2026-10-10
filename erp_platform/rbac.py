# erp_platform/rbac.py — reexporta RBAC legacy + permisos progresivos.
from core.rbac import (  # noqa: F401
    auth_roles,
    usuario_es_admin,
    usuario_tiene_rol,
    usuario_tiene_modulo_asignado,
    usuario_puede_consultar_modulos_finanzas,
    usuario_puede_mutar_modulos_finanzas,
    usuario_puede_consultar_modulos_operacion,
    usuario_puede_mutar_modulos_operacion,
)
from erp_platform.permissions import (  # noqa: F401
    permissions_for_auth,
    usuario_tiene_permiso,
    usuario_puede_modulo_accion,
)
