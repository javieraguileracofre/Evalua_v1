# schemas/maestros/__init__.py
# -*- coding: utf-8 -*-
from .cliente import ClienteBase, ClienteCreate, ClienteUpdate, ClienteOut
from .proveedor import (
    ProveedorBase,
    ProveedorBancoCreate,
    ProveedorBancoOut,
    ProveedorContactoCreate,
    ProveedorContactoOut,
    ProveedorCreate,
    ProveedorDireccionCreate,
    ProveedorDireccionOut,
    ProveedorOut,
    ProveedorUpdate,
)

__all__ = [
    "ClienteBase",
    "ClienteCreate",
    "ClienteUpdate",
    "ClienteOut",
    "ProveedorBase",
    "ProveedorBancoCreate",
    "ProveedorBancoOut",
    "ProveedorContactoCreate",
    "ProveedorContactoOut",
    "ProveedorDireccionCreate",
    "ProveedorDireccionOut",
    "ProveedorCreate",
    "ProveedorUpdate",
    "ProveedorOut",
]