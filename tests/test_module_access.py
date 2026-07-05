# tests/test_module_access.py
# -*- coding: utf-8 -*-
"""Módulos visibles del menú lateral y compatibilidad con RBAC existente."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.module_catalog import (
    ALL_ASSIGNABLE_KEYS,
    ALL_MODULE_KEYS,
    default_visible_modules_for_roles,
    normalize_module_keys,
)
from core.nav_visibility import (
    modulos_visibles_en_sesion,
    usuario_puede_ver_modulo_nav,
    usuario_puede_ver_submodulo_nav,
)
from core.rbac import (
    usuario_puede_consultar_modulos_finanzas,
    usuario_puede_mutar_modulos_finanzas,
)
from crud.auth.modulos_visibles import (
    backfill_visible_modules_from_roles,
    resolve_visible_modules_for_user,
    set_user_visible_modules,
    user_visible_modules_list,
    visible_module_keys,
)
from crud.auth.usuarios import hash_password, listar_roles_codigos, serializar_sesion_usuario
from models.auth.modulo_visible import UsuarioModuloVisible
from models.auth.usuario import Rol, Usuario, usuario_rol


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Rol.__table__.create(engine, checkfirst=True)
    Usuario.__table__.create(engine, checkfirst=True)
    usuario_rol.create(engine, checkfirst=True)
    UsuarioModuloVisible.__table__.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    for i, (codigo, nombre) in enumerate(
        (
            ("ADMIN", "Administrador"),
            ("FINANZAS", "Finanzas"),
            ("RRHH", "Recursos humanos"),
            ("OPERACIONES", "Operaciones"),
            ("CONSULTA", "Consulta"),
        ),
        start=1,
    ):
        session.add(Rol(id=i, codigo=codigo, nombre=nombre))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _crear_usuario_test(
    db: Session,
    *,
    uid: int,
    email: str,
    rol_codigos: list[str],
    modulo_keys: list[str] | None = None,
) -> Usuario:
    roles = [db.scalars(select(Rol).where(Rol.codigo == c)).first() for c in rol_codigos]
    u = Usuario(
        id=uid,
        email=email,
        password_hash=hash_password("1234567890"),
        nombre_completo=email.split("@")[0],
        activo=True,
    )
    for r in roles:
        if r:
            u.roles.append(r)
    db.add(u)
    db.flush()
    resolve_visible_modules_for_user(db, u, modulo_keys)
    return u


def test_defaults_por_rol() -> None:
    fin = default_visible_modules_for_roles(["FINANZAS"])
    assert "PRINCIPAL" in fin
    assert "FINANZAS" in fin
    assert "CONTABILIDAD" in fin
    assert "OPERACIONES" not in fin

    rrhh = default_visible_modules_for_roles(["RRHH"])
    assert rrhh == frozenset({"PRINCIPAL", "RRHH"})

    admin = default_visible_modules_for_roles(["ADMIN"])
    assert admin == frozenset(ALL_ASSIGNABLE_KEYS)


def test_normalize_module_keys_descarta_desconocidos() -> None:
    assert normalize_module_keys(["INVALIDO", "PRINCIPAL", "PRINCIPAL"]) == ["PRINCIPAL"]
    assert normalize_module_keys(["finanzas"]) == ["FINANZAS"]


def test_usuario_sin_modulos_explicitos_recibe_defaults_al_crear(db: Session) -> None:
    u = _crear_usuario_test(db, uid=1, email="fin@test.cl", rol_codigos=["FINANZAS"], modulo_keys=None)
    db.commit()
    keys = user_visible_modules_list(u, db)
    assert "FINANZAS" in keys
    assert "PRINCIPAL" in keys
    assert "OPERACIONES" not in keys


def test_admin_ve_todos_los_modulos_en_nav(db: Session) -> None:
    u = _crear_usuario_test(
        db,
        uid=1,
        email="admin@test.cl",
        rol_codigos=["ADMIN"],
        modulo_keys=["PRINCIPAL"],
    )
    db.commit()
    auth = serializar_sesion_usuario(u, visible_modules=user_visible_modules_list(u, db))
    assert usuario_puede_ver_modulo_nav(auth, "FINANZAS") is True
    assert usuario_puede_ver_modulo_nav(auth, "ADMINISTRACION") is True


def test_filtrado_menu_por_modulos_visibles() -> None:
    auth = {"roles": ["FINANZAS"], "visibleModules": ["PRINCIPAL", "FINANZAS"]}
    visible = modulos_visibles_en_sesion(auth)
    assert visible == frozenset({"PRINCIPAL", "FINANZAS"})
    assert usuario_puede_ver_modulo_nav(auth, "FINANZAS") is True
    assert usuario_puede_ver_modulo_nav(auth, "OPERACIONES") is False


def test_rrhh_solo_ve_secciones_configuradas(db: Session) -> None:
    u = _crear_usuario_test(db, uid=1, email="rrhh@test.cl", rol_codigos=["RRHH"], modulo_keys=None)
    db.commit()
    auth = serializar_sesion_usuario(u, visible_modules=user_visible_modules_list(u, db))
    assert usuario_puede_ver_modulo_nav(auth, "RRHH") is True
    assert usuario_puede_ver_modulo_nav(auth, "FINANZAS") is False


def test_backfill_usuarios_existentes_sin_filas(db: Session) -> None:
    rol = db.scalars(select(Rol).where(Rol.codigo == "OPERACIONES")).first()
    u = Usuario(
        id=1,
        email="legacy@test.cl",
        password_hash="x",
        nombre_completo="Legacy",
        activo=True,
    )
    u.roles.append(rol)
    db.add(u)
    db.commit()

    n = backfill_visible_modules_from_roles(db)
    db.commit()
    assert n == 1
    keys = visible_module_keys(u, db)
    assert "OPERACIONES" in keys
    assert "PRINCIPAL" in keys


def test_admin_puede_asignar_modulos_explicitos(db: Session) -> None:
    u = _crear_usuario_test(
        db,
        uid=1,
        email="custom@test.cl",
        rol_codigos=["FINANZAS"],
        modulo_keys=["PRINCIPAL", "COMERCIAL"],
    )
    db.commit()
    keys = user_visible_modules_list(u, db)
    assert keys == ["PRINCIPAL", "COMERCIAL"]
    assert "FINANZAS" not in keys


def test_guards_finanzas_siguen_basados_en_roles_no_en_menu() -> None:
    auth_menu_restringido = {"roles": ["FINANZAS"], "visibleModules": ["PRINCIPAL"]}
    assert usuario_puede_ver_modulo_nav(auth_menu_restringido, "FINANZAS") is False
    assert usuario_puede_consultar_modulos_finanzas(auth_menu_restringido) is True
    assert usuario_puede_mutar_modulos_finanzas(auth_menu_restringido) is True


def test_resolve_visible_modules_explicitos(db: Session) -> None:
    u = _crear_usuario_test(db, uid=1, email="resolve@test.cl", rol_codigos=["CONSULTA"])
    db.commit()
    resolved = resolve_visible_modules_for_user(db, u, ["PRINCIPAL", "CONTABILIDAD"])
    db.commit()
    assert resolved == ["PRINCIPAL", "CONTABILIDAD"]
    rows = db.scalars(select(UsuarioModuloVisible).where(UsuarioModuloVisible.usuario_id == u.id)).all()
    assert len(rows) == 2


def test_sesion_legacy_usa_defaults_por_rol() -> None:
    auth = {"roles": ["RRHH"], "uid": 1, "email": "x@test.cl", "nombre": "X"}
    visible = modulos_visibles_en_sesion(auth)
    assert "RRHH" in visible
    assert "FINANZAS" not in visible


def test_submodulo_nav_retrocompat_comercial_sin_subs() -> None:
    auth = {"roles": ["FINANZAS"], "visibleModules": ["PRINCIPAL", "COMERCIAL"]}
    assert usuario_puede_ver_submodulo_nav(auth, "LEASING_FINANCIERO") is True
    assert usuario_puede_ver_submodulo_nav(auth, "LEASING_OPERATIVO") is True


def test_submodulo_nav_filtrado_explicito() -> None:
    auth = {"roles": ["FINANZAS"], "visibleModules": ["PRINCIPAL", "COMERCIAL", "LEASING_FINANCIERO"]}
    assert usuario_puede_ver_submodulo_nav(auth, "LEASING_FINANCIERO") is True
    assert usuario_puede_ver_submodulo_nav(auth, "LEASING_OPERATIVO") is False
