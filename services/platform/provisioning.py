# services/platform/provisioning.py
# -*- coding: utf-8 -*-
"""Alta de compañías. Si un paso falla, la compañía queda FAILED y no usa otra base."""
from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.config import settings
from core.module_catalog import ALL_ASSIGNABLE_KEYS
from core.paths import PROJECT_ROOT
from core.validators import formatear_rut, validar_rut_chileno
from models.identity.models import Company, CompanyDatabase, Holding, IdentityUser, Membership
from services.platform.audit import write_audit
from services.platform.db_credentials import encrypt_db_secret
from services.platform.messages import MSG_CREATE_DB, MSG_PROVISION_REVIEW

logger = logging.getLogger("evalua.provisioning")

COMPANY_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class ProvisioningError(RuntimeError):
    pass


@dataclass
class CompanyDraft:
    code: str
    legal_name: str
    trade_name: str
    rut: str
    legal_representative_name: str
    legal_representative_rut: str
    address: str
    region: str
    commune: str
    phone: str
    email: str
    holding_name: str
    database_name: str
    database_user: str
    host: str
    port: int


def validate_company_code(code: str) -> str:
    value = (code or "").strip().lower()
    if not value or not COMPANY_CODE_RE.match(value) or len(value) > 40:
        raise ProvisioningError(
            "El código interno debe empezar con una letra minúscula y usar solo letras, números y guion bajo."
        )
    return value


def validate_company_rut(rut: str, *, required: bool = True) -> str:
    raw = (rut or "").strip()
    if not raw:
        if required:
            raise ProvisioningError("El RUT es obligatorio.")
        return ""
    if not validar_rut_chileno(raw):
        raise ProvisioningError("El RUT no es válido. Verifique el número y el dígito verificador.")
    return formatear_rut(raw)


def propose_database_name(code: str) -> str:
    return f"erp_{code}"[:63]


def propose_database_user(code: str) -> str:
    return f"erp_{code}_app"[:63]


class DatabaseProvisioner:
    """Crea la base PostgreSQL y aplica el esquema. Los tests sustituyen esta clase."""

    def provision(self, *, database_name: str, database_user: str, password: str, host: str, port: int) -> str:
        if not settings.admin_postgres_url:
            raise ProvisioningError(MSG_CREATE_DB)
        for label, value in (("database_name", database_name), ("database_user", database_user)):
            if not IDENTIFIER_RE.match(value):
                raise ProvisioningError(f"El identificador de {label} no es válido.")
        from sqlalchemy import create_engine

        admin = create_engine(settings.admin_postgres_url, future=True, pool_pre_ping=True)
        try:
            with admin.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                exists_user = conn.execute(
                    text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
                    {"name": database_user},
                ).scalar()
                if not exists_user:
                    # PostgreSQL no acepta un parámetro enlazado en PASSWORD.
                    literal = password.replace("'", "''")
                    conn.execute(text(f"CREATE USER {database_user} WITH PASSWORD '{literal}'"))
                exists_db = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": database_name},
                ).scalar()
                if not exists_db:
                    conn.execute(text(f"CREATE DATABASE {database_name} OWNER {database_user}"))
        except ProvisioningError:
            raise
        except Exception as exc:
            logger.error("create database failed error=%s", type(exc).__name__)
            raise ProvisioningError(MSG_CREATE_DB) from exc
        finally:
            admin.dispose()
        from urllib.parse import quote_plus

        return self.open_existing(
            database_name=database_name,
            database_user=database_user,
            password=password,
            host=host,
            port=port,
        )

    def open_existing(self, *, database_name: str, database_user: str, password: str, host: str, port: int) -> str:
        from urllib.parse import quote_plus

        return (
            f"postgresql+psycopg://{quote_plus(database_user)}:{quote_plus(password)}"
            f"@{host}:{int(port)}/{database_name}"
        )

    def apply_schema(self, url: str) -> str:
        from sqlalchemy import create_engine

        from db.schema_bootstrap import apply_company_schema

        engine = create_engine(url, future=True, pool_pre_ping=True)
        try:
            revision = apply_company_schema(engine)
            _stamp(url)
            return revision
        except Exception as exc:
            logger.error("schema apply failed error=%s", type(exc).__name__)
            raise ProvisioningError(MSG_PROVISION_REVIEW) from exc
        finally:
            engine.dispose()

    def healthcheck(self, url: str) -> None:
        from sqlalchemy import create_engine

        engine = create_engine(url, future=True, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            logger.error("healthcheck failed error=%s", type(exc).__name__)
            raise ProvisioningError(MSG_PROVISION_REVIEW) from exc
        finally:
            engine.dispose()

    def write_legal_profile(self, url: str, company: Company) -> None:
        from sqlalchemy import create_engine

        engine = create_engine(url, future=True, pool_pre_ping=True)
        try:
            _upsert_empresa(engine, company)
        except Exception as exc:
            logger.error("legal profile failed error=%s", type(exc).__name__)
            raise ProvisioningError(MSG_PROVISION_REVIEW) from exc
        finally:
            engine.dispose()


def _stamp(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.stamp(cfg, "head")


def _upsert_empresa(engine: Engine, company: Company) -> None:
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id FROM public.empresa ORDER BY id LIMIT 1")).first()
        params = {
            "razon": company.legal_name,
            "fantasia": company.trade_name,
            "rut": company.rut,
            "direccion": company.address,
            "comuna": company.commune,
            "region": company.region,
            "telefono": company.phone,
            "email": company.email,
        }
        if row is None:
            conn.execute(
                text(
                    """
                    INSERT INTO public.empresa
                        (razon_social, nombre_fantasia, rut, direccion, comuna, region, telefono, email, activo)
                    VALUES
                        (:razon, :fantasia, :rut, :direccion, :comuna, :region, :telefono, :email, TRUE)
                    """
                ),
                params,
            )
        else:
            conn.execute(
                text(
                    """
                    UPDATE public.empresa
                    SET razon_social = :razon,
                        nombre_fantasia = :fantasia,
                        rut = :rut,
                        direccion = :direccion,
                        comuna = :comuna,
                        region = :region,
                        telefono = :telefono,
                        email = :email
                    WHERE id = :id
                    """
                ),
                {**params, "id": row[0]},
            )


class CompanyProvisioningService:
    def __init__(self, provisioner: DatabaseProvisioner | None = None) -> None:
        self.provisioner = provisioner or DatabaseProvisioner()

    def create_company(
        self,
        db: Session,
        draft: CompanyDraft,
        *,
        actor: IdentityUser,
        ip_hmac_value: str | None = None,
    ) -> Company:
        code = validate_company_code(draft.code)
        rut = validate_company_rut(draft.rut)
        rep_rut = validate_company_rut(draft.legal_representative_rut, required=False)
        if db.execute(select(Company).where(Company.code == code)).scalar_one_or_none():
            raise ProvisioningError("Ya existe una compañía con ese código.")
        if db.execute(select(Company).where(Company.rut == rut)).scalar_one_or_none():
            raise ProvisioningError("Ya existe una compañía con ese RUT.")
        holding = self._holding(db, draft.holding_name or draft.legal_name, code)
        company = Company(
            holding_id=holding.id,
            code=code,
            legal_name=draft.legal_name.strip(),
            trade_name=(draft.trade_name or "").strip() or None,
            rut=rut,
            legal_representative_name=(draft.legal_representative_name or "").strip() or None,
            legal_representative_rut=rep_rut or None,
            address=(draft.address or "").strip() or None,
            region=(draft.region or "").strip() or None,
            commune=(draft.commune or "").strip() or None,
            phone=(draft.phone or "").strip() or None,
            email=(draft.email or "").strip() or None,
            status="PROVISIONING",
        )
        db.add(company)
        db.flush()
        write_audit(
            db,
            actor_id=int(actor.id),
            company_id=int(company.id),
            action="COMPANY_CREATED",
            result="ok",
            resource=code,
            ip_hmac_value=ip_hmac_value,
        )
        db.commit()
        return self._run(
            db,
            company,
            draft,
            actor,
            ip_hmac_value=ip_hmac_value,
            retry=False,
            create_database=True,
            password_override=None,
        )

    def retry(self, db: Session, company_id: int, *, actor: IdentityUser, ip_hmac_value: str | None = None) -> Company:
        company = db.get(Company, int(company_id))
        if company is None:
            raise ProvisioningError("La compañía no existe.")
        if company.status == "ACTIVE":
            return company
        write_audit(
            db,
            actor_id=int(actor.id),
            company_id=int(company.id),
            action="COMPANY_PROVISIONING_RETRY",
            result="ok",
            resource=company.code,
            ip_hmac_value=ip_hmac_value,
        )
        record = company.database
        draft = CompanyDraft(
            code=company.code,
            legal_name=company.legal_name,
            trade_name=company.trade_name or "",
            rut=company.rut,
            legal_representative_name=company.legal_representative_name or "",
            legal_representative_rut=company.legal_representative_rut or "",
            address=company.address or "",
            region=company.region or "",
            commune=company.commune or "",
            phone=company.phone or "",
            email=company.email or "",
            holding_name="",
            database_name=record.database_name if record else propose_database_name(company.code),
            database_user=record.database_user if record else propose_database_user(company.code),
            host=record.host if record else "localhost",
            port=int(record.port) if record else 5432,
        )
        company.status = "PROVISIONING"
        db.commit()
        return self._run(
            db,
            company,
            draft,
            actor,
            ip_hmac_value=ip_hmac_value,
            retry=True,
            create_database=record is None or record.database_engine != "sqlite",
            password_override=None,
        )

    def register_existing(
        self,
        db: Session,
        draft: CompanyDraft,
        *,
        actor: IdentityUser,
        password: str,
        ip_hmac_value: str | None = None,
    ) -> Company:
        """Registra una base ya existente. No copia datos ni le inventa un nombre."""
        if not (password or "").strip():
            raise ProvisioningError("Indique la clave de la base existente. No se muestra de nuevo.")
        code = validate_company_code(draft.code)
        rut = validate_company_rut(draft.rut)
        if db.execute(select(Company).where(Company.code == code)).scalar_one_or_none():
            raise ProvisioningError("Ya existe una compañía con ese código.")
        holding = self._holding(db, draft.holding_name or draft.legal_name, code)
        company = Company(
            holding_id=holding.id,
            code=code,
            legal_name=draft.legal_name.strip(),
            trade_name=(draft.trade_name or "").strip() or None,
            rut=rut,
            address=(draft.address or "").strip() or None,
            region=(draft.region or "").strip() or None,
            commune=(draft.commune or "").strip() or None,
            phone=(draft.phone or "").strip() or None,
            email=(draft.email or "").strip() or None,
            status="PROVISIONING",
        )
        db.add(company)
        db.flush()
        db.add(
            CompanyDatabase(
                company_id=company.id,
                database_name=draft.database_name.strip(),
                host=(draft.host or "localhost").strip(),
                port=int(draft.port or 5432),
                database_user=draft.database_user.strip(),
                database_engine="postgresql+psycopg",
                encrypted_secret=encrypt_db_secret(password),
                status="PROVISIONING",
            )
        )
        write_audit(
            db,
            actor_id=int(actor.id),
            company_id=int(company.id),
            action="COMPANY_CREATED",
            result="ok",
            resource=code,
            ip_hmac_value=ip_hmac_value,
        )
        db.commit()
        db.refresh(company)
        return self._run(
            db,
            company,
            draft,
            actor,
            ip_hmac_value=ip_hmac_value,
            retry=True,
            create_database=False,
            password_override=password,
        )

    def _run(
        self,
        db: Session,
        company: Company,
        draft: CompanyDraft,
        actor: IdentityUser,
        *,
        ip_hmac_value: str | None,
        retry: bool,
        create_database: bool,
        password_override: str | None,
    ) -> Company:
        password = password_override or secrets.token_urlsafe(24)
        database_name = (draft.database_name or propose_database_name(company.code)).strip()
        database_user = (draft.database_user or propose_database_user(company.code)).strip()
        host = (draft.host or "localhost").strip() or "localhost"
        port = int(draft.port or 5432)
        record = db.execute(
            select(CompanyDatabase).where(CompanyDatabase.company_id == company.id)
        ).scalar_one_or_none()
        if record is None:
            record = CompanyDatabase(
                company_id=company.id,
                database_name=database_name,
                host=host,
                port=port,
                database_user=database_user,
                database_engine="postgresql+psycopg",
                encrypted_secret=encrypt_db_secret(password),
                status="PROVISIONING",
            )
            db.add(record)
            db.commit()
        else:
            password = _existing_or_new_secret(record, password)
            database_name = record.database_name
            database_user = record.database_user
            host = record.host
            port = int(record.port)
        try:
            write_audit(
                db,
                actor_id=int(actor.id),
                company_id=int(company.id),
                action="COMPANY_PROVISIONING",
                result="ok",
                resource=company.code,
                ip_hmac_value=ip_hmac_value,
            )
            db.commit()
            opener = self.provisioner.provision if create_database else self.provisioner.open_existing
            url = opener(
                database_name=database_name,
                database_user=database_user,
                password=password,
                host=host,
                port=port,
            )
            revision = self.provisioner.apply_schema(url)
            self.provisioner.healthcheck(url)
            db.refresh(company)
            self.provisioner.write_legal_profile(url, company)
            self._ensure_membership(db, company, actor)
            company.status = "ACTIVE"
            company.status_detail = None
            company.schema_version = revision
            record.status = "ACTIVE"
            record.schema_version = revision
            write_audit(
                db,
                actor_id=int(actor.id),
                company_id=int(company.id),
                action="COMPANY_ACTIVATED",
                result="ok",
                resource=company.code,
                ip_hmac_value=ip_hmac_value,
            )
            db.commit()
            return company
        except Exception as exc:
            db.rollback()
            company = db.get(Company, company.id)
            record = db.execute(
                select(CompanyDatabase).where(CompanyDatabase.company_id == company.id)
            ).scalar_one_or_none()
            message = exc.args[0] if isinstance(exc, ProvisioningError) and exc.args else MSG_PROVISION_REVIEW
            if not isinstance(message, str) or "://" in message or "password" in message.lower():
                message = MSG_PROVISION_REVIEW
            company.status = "FAILED"
            company.status_detail = message[:500]
            if record is not None:
                record.status = "FAILED"
            write_audit(
                db,
                actor_id=int(actor.id),
                company_id=int(company.id),
                action="COMPANY_PROVISIONING_FAILED",
                result="failed",
                resource=company.code,
                ip_hmac_value=ip_hmac_value,
            )
            db.commit()
            logger.error("provision failed company_id=%s retry=%s", company.id, retry)
            return company

    def _holding(self, db: Session, name: str, code: str) -> Holding:
        raw = re.sub(r"[^a-z0-9_]", "_", (name or "").strip().lower()).strip("_") or code
        try:
            holding_code = validate_company_code(raw)
        except ProvisioningError:
            holding_code = code
        found = db.execute(select(Holding).where(Holding.code == holding_code)).scalar_one_or_none()
        if found:
            return found
        holding = Holding(code=holding_code[:40], name=name.strip()[:200] or code, status="ACTIVE")
        db.add(holding)
        db.flush()
        return holding

    def _ensure_membership(self, db: Session, company: Company, actor: IdentityUser) -> None:
        existing = db.execute(
            select(Membership).where(
                Membership.identity_user_id == actor.id,
                Membership.company_id == company.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.status = "ACTIVE"
            return
        db.add(
            Membership(
                identity_user_id=int(actor.id),
                company_id=int(company.id),
                access_scope="COMPANY_ADMIN",
                role_codes=["ADMIN"],
                module_keys=list(ALL_ASSIGNABLE_KEYS),
                status="ACTIVE",
            )
        )
        db.flush()


def _existing_or_new_secret(record: CompanyDatabase, generated: str) -> str:
    from services.platform.db_credentials import decrypt_db_secret

    try:
        current = decrypt_db_secret(record.encrypted_secret)
        if current.strip():
            return current
    except Exception:
        pass
    record.encrypted_secret = encrypt_db_secret(generated)
    return generated


def save_company_logo(company_id: int, filename: str, content: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        ext = ".png"
    folder = PROJECT_ROOT / "storage" / "platform" / "companies" / str(int(company_id))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"logo{ext}"
    target.write_bytes(content)
    return f"platform/companies/{int(company_id)}/logo{ext}"
