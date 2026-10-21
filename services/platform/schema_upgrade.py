# services/platform/schema_upgrade.py
# -*- coding: utf-8 -*-
"""Upgrade canónico de esquema: Alembic head + sello identity/runtime."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from core.paths import PROJECT_ROOT
from db.schema_revision import ERP_SCHEMA_REVISION, runtime_schema_version, schema_is_current, stamp_schema_revision
from models.identity.models import Company, CompanyDatabase, IdentityUser
from services.platform.audit import write_audit
from services.platform.db_credentials import decrypt_db_secret
from services.platform.messages import MSG_PROVISION_REVIEW
from services.platform.provisioning import ProvisioningError

logger = logging.getLogger("evalua.schema_upgrade")


@dataclass(frozen=True)
class SchemaStatusRow:
    company_id: int
    code: str
    status: str
    identity_version: str
    database_version: str
    runtime_version: str
    is_current: bool
    needs_upgrade: bool
    detail: str = ""


@dataclass(frozen=True)
class UpgradeResult:
    company_id: int
    code: str
    ok: bool
    revision: str
    detail: str = ""


def _alembic_config(url: str):
    from services.platform.alembic_support import load_alembic

    command, config_cls = load_alembic()
    cfg = config_cls(str(PROJECT_ROOT / "alembic.ini"))
    # ConfigParser interpreta '%'; escapar sin loguear la URL.
    cfg.set_main_option("sqlalchemy.url", (url or "").replace("%", "%%"))
    return command, cfg


def _alembic_upgrade(url: str) -> None:
    command, cfg = _alembic_config(url)
    command.upgrade(cfg, "head")


def _alembic_stamp_head(url: str) -> None:
    command, cfg = _alembic_config(url)
    command.stamp(cfg, "head")


def upgrade_database_url(url: str, *, stamp_alembic: bool = True) -> str:
    """Aplica Alembic head, sella app_metadata y opcionalmente alembic_version."""
    if not (url or "").strip():
        raise ProvisioningError("No hay URL de base para migrar.")

    lock_engine = create_engine(url, future=True, pool_pre_ping=True)
    lock_conn = None
    try:
        if lock_engine.dialect.name == "postgresql":
            lock_conn = lock_engine.connect()
            locked = lock_conn.execute(
                text("SELECT pg_try_advisory_lock(hashtext('evalua_schema_upgrade'))")
            ).scalar()
            if not locked:
                raise ProvisioningError(
                    "Hay otra migración en curso sobre esta base. Reintente más tarde."
                )

        try:
            _alembic_upgrade(url)
        except Exception as exc:
            logger.error("alembic upgrade failed error=%s", type(exc).__name__)
            raise ProvisioningError(MSG_PROVISION_REVIEW) from exc

        stamp_engine = create_engine(url, future=True, pool_pre_ping=True)
        try:
            stamp_schema_revision(stamp_engine, ERP_SCHEMA_REVISION)
            runtime = runtime_schema_version(stamp_engine)
            if not schema_is_current(runtime):
                raise ProvisioningError(
                    f"Tras migrar, app_metadata quedó en '{runtime or '—'}' "
                    f"(esperado {ERP_SCHEMA_REVISION})."
                )
        finally:
            stamp_engine.dispose()

        if stamp_alembic:
            try:
                _alembic_stamp_head(url)
            except Exception as exc:
                logger.warning("alembic stamp head: %s", type(exc).__name__)
        return ERP_SCHEMA_REVISION
    except ProvisioningError:
        raise
    except Exception as exc:
        logger.error("schema upgrade failed error=%s", type(exc).__name__)
        raise ProvisioningError(MSG_PROVISION_REVIEW) from exc
    finally:
        if lock_conn is not None:
            try:
                lock_conn.execute(
                    text("SELECT pg_advisory_unlock(hashtext('evalua_schema_upgrade'))")
                )
                lock_conn.close()
            except Exception:
                logger.warning("No se pudo liberar advisory lock de migración")
        lock_engine.dispose()


def company_database_url(record: CompanyDatabase) -> str:
    from db.company_engine import build_company_url

    secret = ""
    if (record.database_engine or "") != "sqlite":
        secret = decrypt_db_secret(record.encrypted_secret or "")
    return build_company_url(
        engine_name=record.database_engine or "postgresql+psycopg",
        database_name=record.database_name,
        host=record.host,
        port=int(record.port),
        user=record.database_user,
        secret=secret,
    )


def inspect_company_schema(company: Company) -> SchemaStatusRow:
    record = company.database
    identity_v = (company.schema_version or "").strip()
    db_v = (record.schema_version or "").strip() if record is not None else ""
    runtime_v = ""
    detail = ""
    if record is None:
        detail = "Sin registro de base"
    elif record.status != "ACTIVE":
        detail = f"Base en estado {record.status}"
    else:
        try:
            url = company_database_url(record)
            engine = create_engine(url, future=True, pool_pre_ping=True)
            try:
                runtime_v = runtime_schema_version(engine)
            finally:
                engine.dispose()
        except Exception as exc:
            detail = f"No se pudo leer runtime: {type(exc).__name__}"
    is_current = (
        schema_is_current(identity_v)
        and schema_is_current(db_v)
        and (not runtime_v or schema_is_current(runtime_v))
        and detail == ""
    )
    needs = (not is_current) and record is not None and record.status == "ACTIVE"
    return SchemaStatusRow(
        company_id=int(company.id),
        code=company.code,
        status=company.status,
        identity_version=identity_v,
        database_version=db_v,
        runtime_version=runtime_v,
        is_current=is_current,
        needs_upgrade=needs,
        detail=detail,
    )


def list_schema_status(db: Session) -> list[SchemaStatusRow]:
    companies = db.execute(select(Company).order_by(Company.code)).scalars().all()
    return [inspect_company_schema(c) for c in companies]


def upgrade_company(
    db: Session,
    company_id: int,
    *,
    actor: IdentityUser | None = None,
    ip_hmac_value: str | None = None,
) -> UpgradeResult:
    company = db.get(Company, int(company_id))
    if company is None:
        return UpgradeResult(0, "", False, "", "Compañía no encontrada.")
    record = company.database
    if record is None or record.status != "ACTIVE":
        return UpgradeResult(
            int(company.id),
            company.code,
            False,
            (company.schema_version or "").strip(),
            "La compañía no tiene base ACTIVE.",
        )
    try:
        url = company_database_url(record)
        revision = upgrade_database_url(url)
        company.schema_version = revision
        record.schema_version = revision
        company.status_detail = None
        if actor is not None:
            write_audit(
                db,
                actor_id=int(actor.id),
                company_id=int(company.id),
                action="COMPANY_SCHEMA_UPGRADED",
                result="ok",
                resource=company.code,
                ip_hmac_value=ip_hmac_value,
            )
        db.commit()
        try:
            from db.company_engine import invalidate_company_engine

            invalidate_company_engine(int(company.id))
        except Exception:
            pass
        return UpgradeResult(int(company.id), company.code, True, revision, "Esquema actualizado.")
    except Exception as exc:
        db.rollback()
        message = exc.args[0] if isinstance(exc, ProvisioningError) and exc.args else MSG_PROVISION_REVIEW
        if not isinstance(message, str) or "://" in message or "password" in message.lower():
            message = MSG_PROVISION_REVIEW
        if actor is not None:
            try:
                write_audit(
                    db,
                    actor_id=int(actor.id),
                    company_id=int(company.id),
                    action="COMPANY_SCHEMA_UPGRADE_FAILED",
                    result="failed",
                    resource=company.code,
                    ip_hmac_value=ip_hmac_value,
                )
                db.commit()
            except Exception:
                db.rollback()
        logger.error("schema upgrade failed company_id=%s error=%s", company_id, type(exc).__name__)
        return UpgradeResult(int(company.id), company.code, False, "", str(message)[:500])


def upgrade_legacy_database(database_url: str) -> str:
    """Migración del modo TENANCY_MODE=legacy (una sola DATABASE_URL)."""
    return upgrade_database_url(database_url)
