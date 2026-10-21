# models/identity/models.py
# -*- coding: utf-8 -*-
"""Identidad de plataforma EvaluaERP. No contiene operación financiera."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from db.identity_base import IdentityBase


COMPANY_STATUSES = ("PROVISIONING", "ACTIVE", "FAILED", "SUSPENDED", "INACTIVE")
MEMBERSHIP_STATUSES = ("ACTIVE", "SUSPENDED", "INACTIVE")
ACCESS_SCOPES = ("COMPANY", "COMPANY_ADMIN", "HOLDING_CONSOLIDATION", "PLATFORM_ADMIN")


class Holding(IdentityBase):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    companies: Mapped[list["Company"]] = relationship(back_populates="holding")


class Company(IdentityBase):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("rut", name="uq_companies_rut"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    holding_id: Mapped[int] = mapped_column(ForeignKey("holdings.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rut: Mapped[str] = mapped_column(String(20), nullable=False)
    legal_representative_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    legal_representative_rut: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(250), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    commune: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    logo_storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROVISIONING")
    status_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    holding: Mapped[Holding] = relationship(back_populates="companies")
    database: Mapped["CompanyDatabase | None"] = relationship(back_populates="company", uselist=False)
    memberships: Mapped[list["Membership"]] = relationship(back_populates="company")


class IdentityUser(IdentityBase):
    __tablename__ = "identity_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class Membership(IdentityBase):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("identity_user_id", "company_id", name="uq_membership_user_company"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identity_user_id: Mapped[int] = mapped_column(ForeignKey("identity_users.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    access_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPANY")
    role_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    module_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[IdentityUser] = relationship(back_populates="memberships")
    company: Mapped[Company] = relationship(back_populates="memberships")


class CompanyDatabase(IdentityBase):
    __tablename__ = "company_databases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True, nullable=False)
    database_name: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str] = mapped_column(String(200), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    database_user: Mapped[str] = mapped_column(String(120), nullable=False)
    database_engine: Mapped[str] = mapped_column(String(40), nullable=False, default="postgresql+psycopg")
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROVISIONING")
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="database")

    def __repr__(self) -> str:
        return f"CompanyDatabase(company_id={self.company_id}, database_name={self.database_name})"


class IdentityPasswordResetCode(IdentityBase):
    """Códigos de recuperación de la identidad. No viven en la base operacional."""

    __tablename__ = "identity_password_reset_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email_hmac: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_ip_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class IdentityLoginAttempt(IdentityBase):
    """Cupo de login de la identidad. No vive en la base operacional."""

    __tablename__ = "identity_login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_hmac: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class PlatformAuditLog(IdentityBase):
    __tablename__ = "platform_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="platform")
    resource: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
