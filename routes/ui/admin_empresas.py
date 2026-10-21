# routes/ui/admin_empresas.py
# -*- coding: utf-8 -*-
"""Administración de compañías. No muestra secretos de base de datos."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from core.ui_templates import EvaluaTemplates as Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.config import settings
from core.module_catalog import ALL_ASSIGNABLE_KEYS, MODULE_LABELS, SUBMODULE_LABELS
from core.paths import TEMPLATES_DIR
from core.rbac import usuario_tiene_modulo_asignado
from db.identity_session import get_identity_sessionmaker
from db.schema_revision import ERP_SCHEMA_REVISION
from models.identity.models import Company, IdentityUser, Membership
from services.platform.audit import write_audit
from services.platform.db_credentials import decrypt_db_secret
from services.platform.provisioning import (
    CompanyDraft,
    CompanyProvisioningService,
    DatabaseProvisioner,
    ProvisioningError,
    propose_database_name,
    propose_database_user,
    save_company_logo,
    validate_company_rut,
)
from services.platform.schema_upgrade import inspect_company_schema, upgrade_company

router = APIRouter(prefix="/plataforma", tags=["Plataforma"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
_LABELS = {**MODULE_LABELS, **SUBMODULE_LABELS}


def _guard(request: Request) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None) or request.session.get("auth")
    if not isinstance(auth, dict):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if auth.get("is_platform_admin") or usuario_tiene_modulo_asignado(auth, "EMPRESAS"):
        return None
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


def _tenancy_block_reason() -> str | None:
    missing: list[str] = []
    if not settings.database_per_company:
        missing.append("TENANCY_MODE=database_per_company")
    if not (settings.identity_database_url or "").strip():
        missing.append("IDENTITY_DATABASE_URL")
    if not (settings.admin_postgres_url or "").strip():
        missing.append("ADMIN_POSTGRES_URL")
    if not (settings.db_credentials_key or "").strip():
        missing.append("DB_CREDENTIALS_KEY")
    if not missing:
        return None
    return (
        "Esta instalación todavía no puede crear una base por cliente. Falta "
        + ", ".join(missing)
        + ". Prepare el entorno con python tools/enable_database_per_company.py y vuelva a iniciar sesión."
    )


def _render(request: Request, template: str, context: dict):
    payload = {"active_menu": "empresas", **context, "request": request}
    return templates.TemplateResponse(template, payload)


def _actor(db, request: Request) -> IdentityUser | None:
    auth = request.session.get("auth") or {}
    return db.get(IdentityUser, int(auth.get("identity_user_id") or 0))


def _public_company(company: Company, users: int, *, probe_runtime: bool = False) -> dict:
    record = company.database
    identity_v = (company.schema_version or "").strip()
    db_v = (record.schema_version or "").strip() if record is not None else ""
    if probe_runtime:
        schema = inspect_company_schema(company)
        is_current = schema.is_current
        needs = schema.needs_upgrade
        runtime_v = schema.runtime_version or ""
        detail = schema.detail or ""
    else:
        from db.schema_revision import schema_is_current

        is_current = schema_is_current(identity_v) and schema_is_current(db_v)
        needs = (not is_current) and record is not None and record.status == "ACTIVE"
        runtime_v = ""
        detail = ""
    return {
        "id": int(company.id),
        "code": company.code,
        "legal_name": company.legal_name,
        "trade_name": company.trade_name or "",
        "rut": company.rut,
        "status": company.status,
        "status_detail": company.status_detail or "",
        "schema_version": company.schema_version or "",
        "schema_runtime": runtime_v,
        "schema_expected": ERP_SCHEMA_REVISION,
        "schema_is_current": is_current,
        "schema_needs_upgrade": needs,
        "schema_detail": detail,
        "database_status": record.status if record is not None else "",
        "users": users,
        "email": company.email or "",
        "phone": company.phone or "",
        "address": company.address or "",
        "region": company.region or "",
        "commune": company.commune or "",
        "legal_representative_name": company.legal_representative_name or "",
        "legal_representative_rut": company.legal_representative_rut or "",
    }


@router.get("/empresas", response_class=HTMLResponse, name="plataforma_empresas")
def empresas_lista(request: Request):
    if (redir := _guard(request)) is not None:
        return redir
    blocked = _tenancy_block_reason()
    if blocked:
        return _render(
            request,
            "plataforma/empresas_lista.html",
            {
                "empresas": [],
                "puede_crear": False,
                "error": request.session.pop("empresa_error", None) or blocked,
            },
        )
    db = get_identity_sessionmaker()()
    try:
        companies = db.execute(select(Company).order_by(Company.legal_name)).scalars().all()
        counts = dict(
            db.execute(
                select(Membership.company_id, func.count()).group_by(Membership.company_id)
            ).all()
        )
        rows = [_public_company(company, int(counts.get(company.id, 0))) for company in companies]
    finally:
        db.close()
    return _render(
        request,
        "plataforma/empresas_lista.html",
        {"empresas": rows, "error": request.session.pop("empresa_error", None)},
    )


@router.get("/empresas/nueva", response_class=HTMLResponse, name="plataforma_empresa_nueva")
def empresa_nueva(request: Request):
    if (redir := _guard(request)) is not None:
        return redir
    error = request.session.pop("empresa_error", None)
    blocked = _tenancy_block_reason()
    if blocked and not error:
        error = blocked
    return _render(
        request,
        "plataforma/empresa_form.html",
        {
            "modo": "nueva",
            "empresa": {},
            "puede_crear": blocked is None,
            "error": error,
        },
    )


@router.post("/empresas/nueva", name="plataforma_empresa_crear")
def empresa_crear(
    request: Request,
    code: str = Form(...),
    legal_name: str = Form(...),
    rut: str = Form(...),
    trade_name: str = Form(""),
    holding_name: str = Form(""),
    legal_representative_name: str = Form(""),
    legal_representative_rut: str = Form(""),
    address: str = Form(""),
    region: str = Form(""),
    commune: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    database_name: str = Form(""),
    database_user: str = Form(""),
    host: str = Form("localhost"),
    port: int = Form(5432),
    logo: UploadFile | None = File(None),
):
    if (redir := _guard(request)) is not None:
        return redir
    blocked = _tenancy_block_reason()
    if blocked:
        request.session["empresa_error"] = blocked
        return RedirectResponse(url="/plataforma/empresas/nueva", status_code=status.HTTP_303_SEE_OTHER)
    draft = CompanyDraft(
        code=code,
        legal_name=legal_name,
        trade_name=trade_name,
        rut=rut,
        legal_representative_name=legal_representative_name,
        legal_representative_rut=legal_representative_rut,
        address=address,
        region=region,
        commune=commune,
        phone=phone,
        email=email,
        holding_name=holding_name,
        database_name=database_name or propose_database_name(code.strip().lower()),
        database_user=database_user or propose_database_user(code.strip().lower()),
        host=host,
        port=port,
    )
    db = get_identity_sessionmaker()()
    try:
        actor = _actor(db, request)
        if actor is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        company = CompanyProvisioningService().create_company(db, draft, actor=actor)
        if logo is not None and logo.filename:
            key = save_company_logo(int(company.id), logo.filename, logo.file.read())
            stored = db.get(Company, company.id)
            if stored is not None:
                stored.logo_storage_key = key
                db.commit()
        if company.status != "ACTIVE":
            request.session["empresa_error"] = company.status_detail or "La compañía quedó en revisión."
        return RedirectResponse(url=f"/plataforma/empresas/{company.id}", status_code=status.HTTP_303_SEE_OTHER)
    except ProvisioningError as exc:
        request.session["empresa_error"] = str(exc)
        return RedirectResponse(url="/plataforma/empresas/nueva", status_code=status.HTTP_303_SEE_OTHER)
    finally:
        db.close()


@router.post("/empresas/registrar-base", name="plataforma_registrar_base")
def registrar_base(
    request: Request,
    code: str = Form(...),
    legal_name: str = Form(...),
    rut: str = Form(...),
    trade_name: str = Form(""),
    database_name: str = Form(...),
    database_user: str = Form(...),
    database_password: str = Form(...),
    host: str = Form("localhost"),
    port: int = Form(5432),
):
    if (redir := _guard(request)) is not None:
        return redir
    blocked = _tenancy_block_reason()
    if blocked:
        request.session["empresa_error"] = blocked
        return RedirectResponse(url="/plataforma/empresas/nueva", status_code=status.HTTP_303_SEE_OTHER)
    draft = CompanyDraft(
        code=code,
        legal_name=legal_name,
        trade_name=trade_name,
        rut=rut,
        legal_representative_name="",
        legal_representative_rut="",
        address="",
        region="",
        commune="",
        phone="",
        email="",
        holding_name="",
        database_name=database_name,
        database_user=database_user,
        host=host,
        port=port,
    )
    db = get_identity_sessionmaker()()
    try:
        actor = _actor(db, request)
        if actor is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        company = CompanyProvisioningService().register_existing(
            db, draft, actor=actor, password=database_password
        )
        if company.status != "ACTIVE":
            request.session["empresa_error"] = company.status_detail or "La compañía quedó en revisión."
        return RedirectResponse(url=f"/plataforma/empresas/{company.id}", status_code=status.HTTP_303_SEE_OTHER)
    except ProvisioningError as exc:
        request.session["empresa_error"] = str(exc)
        return RedirectResponse(url="/plataforma/empresas/nueva", status_code=status.HTTP_303_SEE_OTHER)
    finally:
        db.close()


@router.post("/empresas/{company_id}/editar", name="plataforma_empresa_editar")
def editar_empresa(
    request: Request,
    company_id: int,
    legal_name: str = Form(""),
    trade_name: str = Form(""),
    rut: str = Form(""),
    legal_representative_name: str = Form(""),
    legal_representative_rut: str = Form(""),
    address: str = Form(""),
    region: str = Form(""),
    commune: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
):
    if (redir := _guard(request)) is not None:
        return redir
    db = get_identity_sessionmaker()()
    try:
        company = db.get(Company, company_id)
        actor = _actor(db, request)
        if company is None or actor is None:
            return RedirectResponse(url="/plataforma/empresas", status_code=status.HTTP_303_SEE_OTHER)
        try:
            company.legal_name = (legal_name or "").strip()
            if not company.legal_name:
                raise ProvisioningError("La razón social es obligatoria.")
            company.rut = validate_company_rut(rut)
            company.trade_name = (trade_name or "").strip() or None
            company.legal_representative_name = (legal_representative_name or "").strip() or None
            company.legal_representative_rut = validate_company_rut(legal_representative_rut, required=False) or None
            company.address = (address or "").strip() or None
            company.region = (region or "").strip() or None
            company.commune = (commune or "").strip() or None
            company.phone = (phone or "").strip() or None
            company.email = (email or "").strip() or None
        except ProvisioningError as exc:
            request.session["empresa_error"] = str(exc)
            return RedirectResponse(
                url=f"/plataforma/empresas/{company_id}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        write_audit(
            db,
            actor_id=int(actor.id),
            company_id=int(company.id),
            action="COMPANY_UPDATED",
            result="ok",
            resource=company.code,
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            request.session["empresa_error"] = "Ese RUT ya está registrado en otra compañía."
            return RedirectResponse(
                url=f"/plataforma/empresas/{company_id}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        record = company.database
        if record is not None and str(record.database_engine).startswith("postgresql"):
            try:
                url = DatabaseProvisioner().open_existing(
                    database_name=record.database_name,
                    database_user=record.database_user,
                    password=decrypt_db_secret(record.encrypted_secret),
                    host=record.host,
                    port=int(record.port),
                )
                DatabaseProvisioner().write_legal_profile(url, company)
            except Exception:
                request.session["empresa_error"] = (
                    "La ficha se guardó. No fue posible actualizar la compañía en su base de datos."
                )
    finally:
        db.close()
    return RedirectResponse(url=f"/plataforma/empresas/{company_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/empresas/{company_id}", response_class=HTMLResponse, name="plataforma_empresa_detalle")
def empresa_detalle(request: Request, company_id: int):
    if (redir := _guard(request)) is not None:
        return redir
    db = get_identity_sessionmaker()()
    try:
        company = db.get(Company, company_id)
        if company is None:
            return RedirectResponse(url="/plataforma/empresas", status_code=status.HTTP_303_SEE_OTHER)
        memberships = db.execute(select(Membership).where(Membership.company_id == company.id)).scalars().all()
        users = []
        for membership in memberships:
            person = db.get(IdentityUser, membership.identity_user_id)
            if person is None:
                continue
            users.append(
                {
                    "email": person.email,
                    "nombre": person.nombre_completo,
                    "scope": membership.access_scope,
                    "roles": list(membership.role_codes or []),
                    "modules": list(membership.module_keys or []),
                    "status": membership.status,
                    "membership_id": int(membership.id),
                }
            )
        payload = _public_company(company, len(users), probe_runtime=True)
    finally:
        db.close()
    return _render(
        request,
        "plataforma/empresa_detalle.html",
        {
            "empresa": payload,
            "usuarios": users,
            "modulos": [(key, _LABELS.get(key, key)) for key in ALL_ASSIGNABLE_KEYS],
            "error": request.session.pop("empresa_error", None),
            "ok": request.session.pop("empresa_ok", None),
        },
    )


def _set_status(request: Request, company_id: int, status_value: str, action: str) -> RedirectResponse:
    if (redir := _guard(request)) is not None:
        return redir
    db = get_identity_sessionmaker()()
    try:
        company = db.get(Company, company_id)
        actor = _actor(db, request)
        if company is None or actor is None:
            return RedirectResponse(url="/plataforma/empresas", status_code=status.HTTP_303_SEE_OTHER)
        if status_value == "ACTIVE" and company.status == "FAILED":
            CompanyProvisioningService().retry(db, company_id, actor=actor)
        else:
            company.status = status_value
            if company.database is not None and status_value in {"SUSPENDED", "INACTIVE", "ACTIVE"}:
                company.database.status = "ACTIVE" if status_value == "ACTIVE" else status_value
            write_audit(
                db,
                actor_id=int(actor.id),
                company_id=int(company.id),
                action=action,
                result="ok",
                resource=company.code,
            )
            db.commit()
    finally:
        db.close()
    return RedirectResponse(url=f"/plataforma/empresas/{company_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/empresas/{company_id}/suspender", name="plataforma_empresa_suspender")
def suspender(request: Request, company_id: int):
    return _set_status(request, company_id, "SUSPENDED", "COMPANY_SUSPENDED")


@router.post("/empresas/{company_id}/activar", name="plataforma_empresa_activar")
def activar(request: Request, company_id: int):
    return _set_status(request, company_id, "ACTIVE", "COMPANY_ACTIVATED")


@router.post("/empresas/{company_id}/inactivar", name="plataforma_empresa_inactivar")
def inactivar(request: Request, company_id: int):
    return _set_status(request, company_id, "INACTIVE", "COMPANY_DEACTIVATED")


@router.post("/empresas/{company_id}/reintentar", name="plataforma_empresa_reintentar")
def reintentar(request: Request, company_id: int):
    if (redir := _guard(request)) is not None:
        return redir
    db = get_identity_sessionmaker()()
    try:
        actor = _actor(db, request)
        if actor is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        company = CompanyProvisioningService().retry(db, company_id, actor=actor)
        if company.status != "ACTIVE":
            request.session["empresa_error"] = company.status_detail or "La compañía quedó en revisión."
    except ProvisioningError as exc:
        request.session["empresa_error"] = str(exc)
    finally:
        db.close()
    return RedirectResponse(url=f"/plataforma/empresas/{company_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/empresas/{company_id}/actualizar-esquema", name="plataforma_empresa_actualizar_esquema")
def actualizar_esquema(request: Request, company_id: int):
    """Alembic upgrade head + sello identity/runtime para una compañía."""
    if (redir := _guard(request)) is not None:
        return redir
    db = get_identity_sessionmaker()()
    try:
        actor = _actor(db, request)
        if actor is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        result = upgrade_company(db, company_id, actor=actor)
        if result.ok:
            request.session["empresa_ok"] = (
                f"Esquema actualizado a {result.revision} para {result.code}."
            )
        else:
            request.session["empresa_error"] = result.detail or "No se pudo actualizar el esquema."
    finally:
        db.close()
    return RedirectResponse(url=f"/plataforma/empresas/{company_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/empresas/{company_id}/usuarios", name="plataforma_empresa_usuario")
def asignar_usuario(
    request: Request,
    company_id: int,
    email: str = Form(...),
    nombre: str = Form(""),
    password: str = Form(""),
    roles: list[str] = Form(default=[]),
    modules: list[str] = Form(default=[]),
):
    if (redir := _guard(request)) is not None:
        return redir
    from crud.auth.usuarios import hash_password

    db = get_identity_sessionmaker()()
    try:
        actor = _actor(db, request)
        company = db.get(Company, company_id)
        if actor is None or company is None:
            return RedirectResponse(url="/plataforma/empresas", status_code=status.HTTP_303_SEE_OTHER)
        mail = email.strip().lower()
        person = db.execute(select(IdentityUser).where(IdentityUser.email == mail)).scalar_one_or_none()
        if person is None:
            if len(password or "") < 10:
                request.session["empresa_error"] = "La clave inicial debe tener al menos 10 caracteres."
                return RedirectResponse(
                    url=f"/plataforma/empresas/{company_id}",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            person = IdentityUser(
                email=mail,
                password_hash=hash_password(password),
                nombre_completo=(nombre or mail).strip(),
                activo=True,
                is_platform_admin=False,
            )
            db.add(person)
            db.flush()
        existing = db.execute(
            select(Membership).where(
                Membership.identity_user_id == person.id,
                Membership.company_id == company.id,
            )
        ).scalar_one_or_none()
        role_codes = [item.strip().upper() for item in roles if item.strip()]
        module_keys = [item.strip().upper() for item in modules if item.strip()]
        if existing is None:
            db.add(
                Membership(
                    identity_user_id=int(person.id),
                    company_id=int(company.id),
                    access_scope="COMPANY",
                    role_codes=role_codes or ["CONSULTA"],
                    module_keys=module_keys,
                    status="ACTIVE",
                )
            )
            action = "MEMBERSHIP_CREATED"
        else:
            existing.role_codes = role_codes or existing.role_codes
            existing.module_keys = module_keys or existing.module_keys
            existing.status = "ACTIVE"
            action = "MEMBERSHIP_UPDATED"
        write_audit(
            db,
            actor_id=int(actor.id),
            company_id=int(company.id),
            action=action,
            result="ok",
            resource=mail,
        )
        db.commit()
    finally:
        db.close()
    return RedirectResponse(url=f"/plataforma/empresas/{company_id}", status_code=status.HTTP_303_SEE_OTHER)
