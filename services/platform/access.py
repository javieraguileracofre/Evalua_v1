# services/platform/access.py
# -*- coding: utf-8 -*-
"""Autorización de compañía. Siempre fail-closed."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.identity.models import Company, IdentityUser, Membership
from services.platform.messages import MSG_NO_ACCESS, MSG_NO_COMPANY


def active_memberships(db: Session, user_id: int) -> list[Membership]:
    rows = db.execute(
        select(Membership).where(
            Membership.identity_user_id == int(user_id),
            Membership.status == "ACTIVE",
        )
    ).scalars().all()
    out: list[Membership] = []
    for row in rows:
        company = db.get(Company, row.company_id)
        if company is not None and company.status == "ACTIVE":
            out.append(row)
    return out


def authorize_company(db: Session, user_id: int, company_id: int) -> Membership | None:
    """None si no hay membresía activa sobre una compañía ACTIVE."""
    try:
        cid = int(company_id)
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    membership = db.execute(
        select(Membership).where(
            Membership.identity_user_id == uid,
            Membership.company_id == cid,
            Membership.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if membership is None:
        return None
    company = db.get(Company, cid)
    if company is None or company.status != "ACTIVE":
        return None
    return membership


def post_login_destination(db: Session, user: IdentityUser) -> str:
    """platform | no_company | enter | selector."""
    rows = active_memberships(db, int(user.id))
    if not rows:
        if user.is_platform_admin:
            return "platform"
        return "no_company"
    if len(rows) == 1:
        return "enter"
    return "selector"


def denial_message(db: Session, user_id: int, company_id: int | None) -> str:
    if company_id is None:
        return MSG_NO_COMPANY
    if authorize_company(db, user_id, company_id) is None:
        return MSG_NO_ACCESS
    return MSG_NO_ACCESS
