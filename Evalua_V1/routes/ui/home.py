# routes/ui/home.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["Home"])


@router.get("/home", name="home")
def home() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)