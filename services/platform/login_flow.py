# services/platform/login_flow.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crud.auth.usuarios import verify_password
from models.identity.models import IdentityUser
from services.platform.access import active_memberships, post_login_destination
from services.platform.audit import write_audit


def authenticate_identity(db: Session, email: str, password: str) -> IdentityUser | None:
    found = db.execute(
        select(IdentityUser).where(IdentityUser.email == (email or "").strip().lower())
    ).scalar_one_or_none()
    if found is None or not found.activo:
        return None
    if not verify_password(password, found.password_hash):
        return None
    return found


def begin_session(db: Session, user: IdentityUser) -> dict:
    rows = active_memberships(db, int(user.id))
    destination = post_login_destination(db, user)
    choices = []
    for membership in rows:
        company = membership.company
        choices.append(
            {
                "id": int(company.id),
                "legal_name": company.legal_name,
                "trade_name": company.trade_name or "",
                "rut": company.rut,
            }
        )
    payload = {
        "uid": int(user.id),
        "identity_user_id": int(user.id),
        "email": user.email,
        "nombre": user.nombre_completo,
        "roles": [],
        "sv": int(user.session_version or 1),
        "visibleModules": [],
        "is_platform_admin": bool(user.is_platform_admin),
        "company_choices": choices,
    }
    if destination == "enter" and rows:
        company = rows[0].company
        payload.update(
            {
                "roles": list(rows[0].role_codes or []),
                "visibleModules": list(rows[0].module_keys or []),
                "active_company_id": int(company.id),
                "company_code": company.code,
                "company_legal_name": company.legal_name,
                "company_trade_name": company.trade_name or "",
                "company_rut": company.rut,
            }
        )
    write_audit(db, actor_id=int(user.id), action="LOGIN", result="ok", module="auth")
    return {"destination": destination, "auth": payload}
