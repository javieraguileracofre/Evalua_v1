# modules/comercial/customers.py
from __future__ import annotations

from sqlalchemy.orm import Session

from crud.maestros import cliente as crud_cliente


def get_cliente(db: Session, cliente_id: int):
    return crud_cliente.get_cliente(db, cliente_id)


def listar_clientes(db: Session, **kwargs):
    return crud_cliente.listar_clientes(db, **kwargs)


def crear_cliente(db: Session, data, *, usuario: str = "sistema"):
    return crud_cliente.crear_cliente(db, data, usuario=usuario)
