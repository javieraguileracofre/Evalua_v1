# tests/test_database_per_company.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from core.company_context import CompanyContext, document_footer_text, document_header_text, set_company_context
from core.validators import calcular_dv_rut
from crud.auth.usuarios import hash_password
from db.company_engine import CompanyDatabaseUnavailable, get_company_engine
from db.identity_base import IdentityBase
from models.identity.models import Company, CompanyDatabase, IdentityUser, Membership
from services.platform.access import authorize_company, post_login_destination
from services.platform.db_credentials import decrypt_db_secret, encrypt_db_secret
from services.platform.messages import MSG_CREATE_DB, MSG_NO_COMPANY
from services.platform.provisioning import (
    CompanyDraft,
    CompanyProvisioningService,
    ProvisioningError,
)
from services.platform.schema_version import ERP_SCHEMA_REVISION, schema_is_current


def _rut(body: str) -> str:
    return f"{body}-{calcular_dv_rut(body)}"


class MemProvisioner:
    engine_name = "sqlite"

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.created: list[str] = []
        self.fail = False

    def provision(self, *, database_name: str, database_user: str, password: str, host: str, port: int) -> str:
        del database_user, password, host, port
        if self.fail:
            raise ProvisioningError(MSG_CREATE_DB)
        if database_name not in self.created:
            self.created.append(database_name)
        path = self.folder / f"{database_name}.db"
        engine = create_engine(f"sqlite:///{path}")
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return f"sqlite:///{path}"

    def open_existing(self, **kwargs) -> str:
        return self.provision(**kwargs)

    def apply_schema(self, url: str) -> str:
        del url
        return ERP_SCHEMA_REVISION

    def healthcheck(self, url: str) -> None:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()

    def write_legal_profile(self, url: str, company: Company) -> None:
        del url, company


@pytest.fixture
def identity_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DB_CREDENTIALS_KEY", "k" * 32)
    engine = create_engine(f"sqlite:///{tmp_path / 'identity.db'}")
    IdentityBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = Session()
    try:
        yield db, tmp_path
    finally:
        db.close()


def _admin(db) -> IdentityUser:
    user = IdentityUser(
        email="admin@evaluaerp.local",
        password_hash=hash_password("clave-segura-123"),
        nombre_completo="Admin Plataforma",
        activo=True,
        is_platform_admin=True,
        session_version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _draft(code: str, body: str, legal: str) -> CompanyDraft:
    return CompanyDraft(
        code=code,
        legal_name=legal,
        trade_name=legal,
        rut=_rut(body),
        legal_representative_name="",
        legal_representative_rut="",
        address="Calle 1",
        region="Region",
        commune="Comuna",
        phone="",
        email="",
        holding_name="holding_demo",
        database_name=f"erp_{code}",
        database_user=f"erp_{code}_app",
        host="localhost",
        port=5432,
    )


def test_instalacion_nueva_no_tiene_compania_por_defecto(identity_db) -> None:
    db, _tmp = identity_db
    total = db.execute(select(func.count()).select_from(Company)).scalar_one()
    assert total == 0
    config = Path("core/config.py").read_text(encoding="utf-8")
    assert "athletic" not in config
    assert 'DEFAULT_TENANT_CODE", "athletic"' not in config


def test_crear_compania_a_y_b_en_bases_distintas(identity_db) -> None:
    db, tmp = identity_db
    admin = _admin(db)
    service = CompanyProvisioningService(MemProvisioner(tmp))
    company_a = service.create_company(db, _draft("empresa_a", "76086428", "Compania A"), actor=admin)
    company_b = service.create_company(db, _draft("empresa_b", "76086429", "Compania B"), actor=admin)
    db.refresh(company_a)
    db.refresh(company_b)
    assert company_a.status == "ACTIVE"
    assert company_b.status == "ACTIVE"
    assert company_a.database.database_name != company_b.database.database_name
    assert company_a.schema_version == ERP_SCHEMA_REVISION
    memberships = db.execute(select(Membership)).scalars().all()
    assert len(memberships) == 2


def test_usuario_solo_de_a_no_entra_a_b(identity_db) -> None:
    db, tmp = identity_db
    admin = _admin(db)
    service = CompanyProvisioningService(MemProvisioner(tmp))
    company_a = service.create_company(db, _draft("empresa_a", "76086428", "Compania A"), actor=admin)
    company_b = service.create_company(db, _draft("empresa_b", "76086429", "Compania B"), actor=admin)
    person = IdentityUser(
        email="solo.a@evaluaerp.local",
        password_hash=hash_password("clave-segura-123"),
        nombre_completo="Solo A",
        activo=True,
        is_platform_admin=False,
        session_version=1,
    )
    db.add(person)
    db.flush()
    db.add(
        Membership(
            identity_user_id=person.id,
            company_id=company_a.id,
            access_scope="COMPANY",
            role_codes=["CONSULTA"],
            module_keys=["PRINCIPAL"],
            status="ACTIVE",
        )
    )
    db.commit()
    assert authorize_company(db, person.id, company_a.id) is not None
    assert authorize_company(db, person.id, company_b.id) is None
    assert authorize_company(db, person.id, 99999) is None


def test_usuario_con_dos_companias_puede_cambiar(identity_db) -> None:
    db, tmp = identity_db
    admin = _admin(db)
    service = CompanyProvisioningService(MemProvisioner(tmp))
    company_a = service.create_company(db, _draft("empresa_a", "76086428", "Compania A"), actor=admin)
    company_b = service.create_company(db, _draft("empresa_b", "76086429", "Compania B"), actor=admin)
    assert authorize_company(db, admin.id, company_a.id) is not None
    assert authorize_company(db, admin.id, company_b.id) is not None
    assert post_login_destination(db, admin) == "selector"


def test_company_id_manipulado_se_niega(identity_db) -> None:
    db, tmp = identity_db
    admin = _admin(db)
    company_a = CompanyProvisioningService(MemProvisioner(tmp)).create_company(
        db, _draft("empresa_a", "76086428", "Compania A"), actor=admin
    )
    assert authorize_company(db, admin.id, company_a.id + 50) is None


def test_base_caida_no_abre_otra_compania(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[int] = []

    def _load(company_id: int):
        opened.append(company_id)
        if company_id != 1:
            raise AssertionError("abrió otra compañía")
        return {
            "database_name": "erp_caida",
            "host": "127.0.0.1",
            "port": 1,
            "database_user": "nadie",
            "database_engine": "postgresql+psycopg",
            "encrypted_secret": encrypt_db_secret("secreto-no-log"),
            "status": "ACTIVE",
        }

    monkeypatch.setenv("DB_CREDENTIALS_KEY", "k" * 32)
    monkeypatch.setattr("db.company_engine._load_record", _load)
    with pytest.raises(CompanyDatabaseUnavailable):
        get_company_engine(1)
    assert opened == [1]


def test_pdf_usa_datos_de_la_compania_activa() -> None:
    from core.company_context import reset_company_context

    token_a = set_company_context(
        CompanyContext(
            company_id=1,
            company_code="empresa_a",
            legal_name="Compania A SpA",
            trade_name="A",
            rut="76086428-5",
            database_id=1,
            schema_version=ERP_SCHEMA_REVISION,
            authorized=True,
        )
    )
    try:
        header_a = document_header_text()
    finally:
        reset_company_context(token_a)
    token_b = set_company_context(
        CompanyContext(
            company_id=2,
            company_code="empresa_b",
            legal_name="Compania B SpA",
            trade_name="B",
            rut="76086429-3",
            database_id=2,
            schema_version=ERP_SCHEMA_REVISION,
            authorized=True,
        )
    )
    try:
        header_b = document_header_text()
        footer = document_footer_text()
    finally:
        reset_company_context(token_b)
    assert "Compania A SpA" in header_a
    assert "76086428-5" in header_a
    assert "Compania B" not in header_a
    assert "Compania B SpA" in header_b
    assert "76086429-3" in header_b
    assert "Compania A" not in header_b
    assert footer == "Documento generado por EvaluaERP"


def test_provisionamiento_fallido_queda_failed_y_reintento_no_duplica(identity_db) -> None:
    db, tmp = identity_db
    admin = _admin(db)
    provisioner = MemProvisioner(tmp)
    provisioner.fail = True
    service = CompanyProvisioningService(provisioner)
    failed = service.create_company(db, _draft("empresa_a", "76086428", "Compania A"), actor=admin)
    db.refresh(failed)
    assert failed.status == "FAILED"
    assert provisioner.created == []
    provisioner.fail = False
    retried = service.retry(db, failed.id, actor=admin)
    db.refresh(retried)
    assert retried.status == "ACTIVE"
    assert provisioner.created == ["erp_empresa_a"]
    again = service.retry(db, retried.id, actor=admin)
    assert again.status == "ACTIVE"
    assert provisioner.created == ["erp_empresa_a"]
    total = db.execute(
        select(func.count()).select_from(Membership).where(Membership.company_id == retried.id)
    ).scalar_one()
    databases = db.execute(
        select(func.count()).select_from(CompanyDatabase).where(CompanyDatabase.company_id == retried.id)
    ).scalar_one()
    assert total == 1
    assert databases == 1


def test_inactive_niega_acceso_y_conserva_la_base(identity_db) -> None:
    db, tmp = identity_db
    admin = _admin(db)
    company = CompanyProvisioningService(MemProvisioner(tmp)).create_company(
        db, _draft("empresa_a", "76086428", "Compania A"), actor=admin
    )
    company.status = "INACTIVE"
    db.commit()
    assert authorize_company(db, admin.id, company.id) is None
    assert company.database.database_name == "erp_empresa_a"
    person = IdentityUser(
        email="operador@evaluaerp.local",
        password_hash=hash_password("clave-segura-123"),
        nombre_completo="Operador",
        activo=True,
        is_platform_admin=False,
        session_version=1,
    )
    db.add(person)
    db.flush()
    db.add(
        Membership(
            identity_user_id=person.id,
            company_id=company.id,
            access_scope="COMPANY",
            role_codes=["CONSULTA"],
            module_keys=["PRINCIPAL"],
            status="ACTIVE",
        )
    )
    db.commit()
    assert authorize_company(db, person.id, company.id) is None
    assert post_login_destination(db, person) == "no_company"


def test_secreto_no_sale_en_respuesta_ni_en_log(identity_db, caplog: pytest.LogCaptureFixture) -> None:
    db, tmp = identity_db
    admin = _admin(db)
    plain = "clave-de-base-que-no-debe-verse"
    stored = encrypt_db_secret(plain)
    assert plain not in stored
    assert decrypt_db_secret(stored) == plain
    company = CompanyProvisioningService(MemProvisioner(tmp)).create_company(
        db, _draft("empresa_a", "76086428", "Compania A"), actor=admin
    )
    payload = {
        "code": company.code,
        "legal_name": company.legal_name,
        "rut": company.rut,
        "status": company.status,
        "schema_version": company.schema_version,
    }
    blob = json.dumps(payload)
    assert company.database.encrypted_secret not in blob
    assert "password" not in blob.lower()
    assert plain not in caplog.text
    assert "://" not in repr(company.database)


def test_esquema_antiguo_no_es_compatible() -> None:
    assert schema_is_current(ERP_SCHEMA_REVISION)
    assert not schema_is_current("0000_viejo")
    assert not schema_is_current(None)


def test_sin_compania_el_mensaje_no_elige_un_cliente() -> None:
    assert "athletic" not in MSG_NO_COMPANY.lower()
    assert "gaval" not in MSG_NO_COMPANY.lower()


def test_database_url_no_es_fallback_en_modo_compania(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.config import Settings

    monkeypatch.setenv("TENANCY_MODE", "database_per_company")
    monkeypatch.setenv("IDENTITY_DATABASE_URL", "sqlite:///identity-prueba.db")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secreto@127.0.0.1:5432/operacional")
    monkeypatch.setenv("PLATFORM_DATABASE_URL", "postgresql+psycopg://user:secreto@127.0.0.1:5432/operacional")
    loaded = Settings.load()
    assert loaded.database_per_company
    assert loaded.database_url == ""
    assert "operacional" not in loaded.platform_database_url
    assert loaded.platform_database_url.startswith("sqlite:")
    assert loaded.default_tenant_code == ""


def test_registro_failed_no_abre_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    from db.company_engine import CompanyAccessDenied

    monkeypatch.setattr(
        "db.company_engine._load_record",
        lambda company_id: {
            "database_name": "erp_failed",
            "host": "127.0.0.1",
            "port": 5432,
            "database_user": "nadie",
            "database_engine": "postgresql+psycopg",
            "encrypted_secret": "evdb1:no",
            "status": "FAILED",
        },
    )
    with pytest.raises(CompanyAccessDenied):
        get_company_engine(7)


def test_engines_de_dos_companias_no_se_comparten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from db.company_engine import invalidate_company_engine

    files = {1: tmp_path / "a.db", 2: tmp_path / "b.db"}

    def _load(company_id: int):
        return {
            "database_name": str(files[int(company_id)]),
            "host": "localhost",
            "port": 5432,
            "database_user": "app",
            "database_engine": "sqlite",
            "encrypted_secret": "",
            "status": "ACTIVE",
        }

    monkeypatch.setattr("db.company_engine._load_record", _load)
    try:
        engine_a = get_company_engine(1)
        engine_b = get_company_engine(2)
        again_a = get_company_engine(1)
        assert engine_a is again_a
        assert engine_a is not engine_b
        assert str(engine_a.url) != str(engine_b.url)
        maker_a = __import__("db.company_engine", fromlist=["get_company_sessionmaker"]).get_company_sessionmaker(1)
        maker_b = __import__("db.company_engine", fromlist=["get_company_sessionmaker"]).get_company_sessionmaker(2)
        session_a = maker_a()
        session_b = maker_b()
        try:
            assert session_a.get_bind() is not session_b.get_bind()
        finally:
            session_a.close()
            session_b.close()
    finally:
        invalidate_company_engine(1)
        invalidate_company_engine(2)


def test_membresia_suspendida_niega_acceso(identity_db) -> None:
    db, tmp = identity_db
    admin = _admin(db)
    company = CompanyProvisioningService(MemProvisioner(tmp)).create_company(
        db, _draft("empresa_a", "76086428", "Compania A"), actor=admin
    )
    membership = db.execute(
        select(Membership).where(Membership.company_id == company.id)
    ).scalar_one()
    membership.status = "SUSPENDED"
    db.commit()
    assert authorize_company(db, admin.id, company.id) is None


def test_password_reset_en_modo_compania_usa_identidad(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from services.auth import password_reset as reset

    monkeypatch.setattr(reset, "settings", SimpleNamespace(database_per_company=True))
    assert reset._code_model().__name__ == "IdentityPasswordResetCode"


def test_almacenamiento_operacional_separa_companias(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.company_context import reset_company_context
    from core.config import settings as cfg
    from core.paths import operational_storage

    monkeypatch.setattr(type(cfg), "database_per_company", property(lambda self: True))

    token = set_company_context(
        CompanyContext(
            company_id=1,
            company_code="empresa_a",
            legal_name="Compania A",
            trade_name="",
            rut="76086428-5",
            database_id=1,
            schema_version=ERP_SCHEMA_REVISION,
            authorized=True,
        )
    )
    try:
        path_a = operational_storage("leasing_credito", "1")
    finally:
        reset_company_context(token)
    token_b = set_company_context(
        CompanyContext(
            company_id=2,
            company_code="empresa_b",
            legal_name="Compania B",
            trade_name="",
            rut="76086429-3",
            database_id=2,
            schema_version=ERP_SCHEMA_REVISION,
            authorized=True,
        )
    )
    try:
        path_b = operational_storage("leasing_credito", "1")
    finally:
        reset_company_context(token_b)
    assert "empresa_a" in path_a.parts
    assert "empresa_b" in path_b.parts
    assert path_a != path_b


def test_cobranza_sin_cuenta_no_usa_otro_buzon() -> None:
    from services.comunicaciones.email_service import EmailService
    from services.comunicaciones.mail_account_service import MailConfigError

    service = EmailService(
        host="smtp.ejemplo.cl",
        port=587,
        username="otra-empresa@ejemplo.cl",
        password="no-enviar",
        from_name="Evalua ERP",
    )
    with pytest.raises(MailConfigError):
        service._config_for_send(db=None, channel_code="COBRANZA")


def test_log_redacta_url_y_password() -> None:
    from core.logging import redact_secrets

    raw = "could not connect to postgresql://user:clave@127.0.0.1:5432/erp password=clave"
    cleaned = redact_secrets(raw)
    assert "clave" not in cleaned
    assert "postgresql://***" in cleaned


def test_alembic_de_la_libreria_no_usa_la_carpeta_de_migraciones() -> None:
    from services.platform.alembic_support import load_alembic

    command, config_cls = load_alembic()
    assert callable(command.stamp)
    assert callable(command.upgrade)
    assert config_cls.__name__ == "Config"


def test_alta_de_base_usa_el_servidor_administrativo(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from services.platform.provisioning import database_endpoint

    monkeypatch.setattr(
        "services.platform.provisioning.settings",
        SimpleNamespace(
            admin_postgres_url="postgresql+psycopg://postgres:secreto@127.0.0.1:5432/postgres"
        ),
    )
    host, port = database_endpoint("localhost", 5432)
    assert host == "127.0.0.1"
    assert port == 5432
    remote_host, remote_port = database_endpoint("db.interno.cl", 5433)
    assert remote_host == "db.interno.cl"
    assert remote_port == 5433
