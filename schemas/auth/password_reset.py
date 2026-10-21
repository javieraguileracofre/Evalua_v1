# schemas/auth/password_reset.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


def _normalizar_email(v: object) -> str:
    return str(v or "").strip().lower()


class ForgotPasswordIn(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, v: object) -> str:
        return _normalizar_email(v)


class VerifyResetCodeIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=32)

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, v: object) -> str:
        return _normalizar_email(v)

    @field_validator("code", mode="before")
    @classmethod
    def normalizar_codigo(cls, v: object) -> str:
        return "".join(ch for ch in str(v or "") if ch.isalnum())


class ResetPasswordIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=32)
    new_password: str = Field(min_length=1, max_length=200)
    confirm_password: str = Field(min_length=1, max_length=200)

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, v: object) -> str:
        return _normalizar_email(v)

    @field_validator("code", mode="before")
    @classmethod
    def normalizar_codigo(cls, v: object) -> str:
        return "".join(ch for ch in str(v or "") if ch.isalnum())
