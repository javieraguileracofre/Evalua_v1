# tests/test_architecture_boundaries.py
# -*- coding: utf-8 -*-
"""Guardrails del modular monolith."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _py_files(rel: str) -> list[Path]:
    base = ROOT / rel
    if not base.exists():
        return []
    return [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]


def _imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append(node.module)
    return out


def test_erp_platform_does_not_import_domain_modules():
    forbidden_prefixes = (
        "modules.leasing",
        "modules.rrhh",
        "modules.taller",
        "modules.inventario",
        "modules.cobranza",
        "services.leasing",
        "services.remuneraciones",
        "services.credito",
    )
    violations: list[str] = []
    for path in _py_files("erp_platform"):
        for mod in _imports(path):
            if any(mod == p or mod.startswith(p + ".") for p in forbidden_prefixes):
                violations.append(f"{path.relative_to(ROOT)} → {mod}")
    assert violations == [], "erp_platform no debe depender de dominios ERP:\n" + "\n".join(violations)


def test_registry_modules_have_codes():
    from erp_platform.registry import ERP_MODULES, allowed_dependency, get_module

    codes = {m.code for m in ERP_MODULES}
    assert "PLATFORM" in codes
    assert "CONTABILIDAD" in codes
    assert "LEASING_FINANCIERO" in codes
    assert "CREDITO_COBRANZAS" in codes
    assert get_module("contabilidad") is not None
    assert get_module("credito_cobranzas") is not None
    assert allowed_dependency("LEASING_FINANCIERO", "CONTABILIDAD")
    assert allowed_dependency("COBRANZA", "CREDITO_COBRANZAS")
    assert allowed_dependency("TALLER", "INVENTARIO")
    assert not allowed_dependency("CONTABILIDAD", "TALLER")


def test_permissions_union_of_roles():
    from erp_platform.permissions import permissions_for_auth, usuario_tiene_permiso

    auth = {"roles": ["RRHH", "FINANZAS"]}
    perms = permissions_for_auth(auth)
    assert "RRHH.PAYROLL" in perms
    assert "CONTABILIDAD.POST" in perms
    assert usuario_tiene_permiso({"roles": ["ADMIN"]}, "ADMIN.BACKUPS")
    assert not usuario_tiene_permiso({"roles": ["CONSULTA"]}, "ADMIN.USERS")


def test_event_bus_delivers_and_can_clear():
    from erp_platform.events import DomainEvent, clear_subscribers, emit, subscribe

    clear_subscribers()
    seen: list[str] = []

    def handler(ev: DomainEvent) -> None:
        seen.append(ev.name)

    subscribe("TestEvent", handler)
    emit(DomainEvent(name="TestEvent", payload={"x": 1}))
    assert seen == ["TestEvent"]
    clear_subscribers("TestEvent")


def test_accounting_service_is_importable():
    from modules.contabilidad import accounting_service

    assert hasattr(accounting_service, "post_entry")
    assert hasattr(accounting_service, "get_entry")


def test_bootstrap_handlers_idempotent():
    from modules.bootstrap import register_domain_handlers
    from erp_platform.events import clear_subscribers

    clear_subscribers()
    import modules.bootstrap as boot

    boot._REGISTERED = False
    register_domain_handlers()
    register_domain_handlers()
    assert boot._REGISTERED is True


def test_finanzas_integracion_uses_accounting_service():
    text = (ROOT / "services" / "finanzas" / "integracion_ventas.py").read_text(encoding="utf-8")
    assert "accounting_service" in text
    assert "from crud.finanzas.contabilidad_asientos import" not in text


def test_stdlib_platform_not_shadowed():
    import platform as std_platform

    assert hasattr(std_platform, "python_implementation")


def test_registry_nav_keys_align_with_module_catalog():
    """Cada nav_module_key del registry debe existir en el catálogo de menú/RBAC."""
    from core.module_catalog import ALL_ASSIGNABLE_KEYS
    from erp_platform.registry import ERP_MODULES

    catalog = set(ALL_ASSIGNABLE_KEYS)
    registry_nav = {m.nav_module_key for m in ERP_MODULES if m.nav_module_key}
    orphan_registry = sorted(registry_nav - catalog)
    assert orphan_registry == [], f"nav_module_key sin catálogo: {orphan_registry}"

    # Claves de menú deben estar cubiertas por al menos un módulo del registry.
    orphan_catalog = sorted(catalog - registry_nav)
    assert orphan_catalog == [], f"clave de catálogo sin registry: {orphan_catalog}"


@pytest.mark.parametrize(
    "pkg",
    ["erp_platform", "modules", "modules/contabilidad", "modules/comercial", "modules/leasing"],
)
def test_packages_exist(pkg: str):
    assert (ROOT / pkg).exists()
