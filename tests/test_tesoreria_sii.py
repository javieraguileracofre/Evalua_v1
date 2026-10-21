# tests/test_tesoreria_sii.py
# -*- coding: utf-8 -*-
"""Fase 1 SII: parser, idempotencia, permisos y aislamiento de empresa."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from integrations.sii.auth_result import clasificar_resultado_login
from integrations.sii.errors import EstructuraInvalida, SiiEtapaError, scrub
from integrations.sii.normalizer import normalizar_tabla
from integrations.sii.parser import leer_tabla
from integrations.sii.rut import rut_es_valido
from services.tesoreria.actualizacion import Solicitud, correr_actualizacion
from services.tesoreria.crypto import decrypt_secret, encrypt_secret
from services.tesoreria.precondiciones import (
    parse_periodo,
    rut_de_empresa_activa,
    rut_para_consulta_sii,
    validar_precondiciones,
)

ROOT = Path(__file__).resolve().parents[1]
CLAVE = "SuperClaveSii-99"


def _rut(cuerpo: str) -> str:
    for dv in "0123456789K":
        candidato = f"{cuerpo}-{dv}"
        if rut_es_valido(candidato):
            return candidato
    raise AssertionError(cuerpo)


RUT_A = _rut("76000010")
RUT_B = _rut("76000020")
RUT_CLIENTE = _rut("15000010")


def _engine():
    engine = create_engine(
        "sqlite://",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _attach(dbapi_connection, _record):
        dbapi_connection.execute("ATTACH DATABASE ':memory:' AS fin")
        dbapi_connection.create_function("now", 0, lambda: "2026-10-12 21:00:00")

    ddl = """
    CREATE TABLE fin.documento_tributario (
        id integer primary key autoincrement,
        direccion varchar(12) not null,
        tipo varchar(20) not null,
        folio varchar(40) not null,
        rut_emisor varchar(20) not null,
        rut_receptor varchar(20) not null default '',
        razon_social varchar(180) not null default '',
        fecha_emision date not null,
        neto numeric not null,
        iva numeric not null,
        total numeric not null,
        moneda varchar(8) not null default 'CLP',
        asiento_id integer null,
        origen_tipo varchar(30) not null,
        origen_id integer not null,
        exento numeric not null default 0,
        otros numeric not null default 0,
        fecha_recepcion date null,
        estado_sii varchar(40) not null default '',
        periodo_anio integer null,
        periodo_mes integer null,
        ejecucion_sii_id integer null,
        unique (direccion, tipo, folio, rut_emisor)
    );
    CREATE TABLE fin.sii_credencial (
        id integer primary key,
        rut varchar(20) not null,
        usuario varchar(32) not null,
        secreto_cifrado text not null default '',
        estado varchar(32) not null default 'INCOMPLETA'
    );
    CREATE TABLE fin.sii_ejecucion (
        id integer primary key,
        company_id integer not null,
        actor_id integer null,
        actor_email varchar(254) not null default '',
        periodo_anio integer not null,
        periodo_mes integer not null,
        tipo_integracion varchar(16) not null default 'SII',
        estado varchar(40) not null,
        pasos text not null default '[]',
        inicio_at text null,
        fin_at text null,
        compras_encontrados integer not null default 0,
        compras_importados integer not null default 0,
        compras_omitidos integer not null default 0,
        compras_errores integer not null default 0,
        ventas_encontrados integer not null default 0,
        ventas_importados integer not null default 0,
        ventas_omitidos integer not null default 0,
        ventas_errores integer not null default 0,
        error_publico text null,
        error_tecnico text null
    );
    CREATE TABLE fin.sii_archivo (
        id integer primary key autoincrement,
        ejecucion_id integer not null,
        tipo varchar(16) not null,
        nombre_archivo varchar(255) not null,
        periodo_anio integer not null,
        periodo_mes integer not null,
        company_id integer not null,
        descargado_at text null,
        sha256 varchar(64) not null,
        tamano_bytes integer not null,
        ruta varchar(500) not null
    );
    """
    with engine.begin() as conn:
        for statement in ddl.split(";"):
            if statement.strip():
                conn.exec_driver_sql(statement)
    return engine


def _sesion(engine) -> Session:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _preparar(engine, company_id: int, rut: str, monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.setenv("SII_CREDENTIALS_KEY", "k" * 40)
    db = _sesion(engine)
    db.execute(
        text(
            """
            INSERT INTO fin.sii_credencial (id, rut, usuario, secreto_cifrado, estado)
            VALUES (1, :rut, :rut, :secreto, 'CONFIGURADA')
            """
        ),
        {"rut": rut, "secreto": encrypt_secret(CLAVE)},
    )
    db.execute(
        text(
            """
            INSERT INTO fin.sii_ejecucion (
                id, company_id, actor_email, periodo_anio, periodo_mes, estado, pasos
            ) VALUES (1, :company, 'fin@test.cl', 2026, 9, 'EN_PROCESO', '[]')
            """
        ),
        {"company": company_id},
    )
    db.commit()
    return db


def _csv(path: Path, encabezado: str, filas: list[str]) -> Path:
    path.write_text(encabezado + "\n" + "\n".join(filas) + ("\n" if filas else ""), encoding="latin-1")
    return path


def _compras(path: Path, *, folio: str = "1234", total: str = "11900") -> Path:
    return _csv(
        path,
        "Nro;Tipo Doc;Tipo Compra;RUT Proveedor;Razon Social;Folio;Fecha Docto;Fecha Recepcion;Monto Exento;Monto Neto;Monto IVA Recuperable;Monto Total",
        [f"1;33;Del Giro;76.000.030-9;Proveedor Demo;{folio};01/09/2026;02/09/2026;0;10000;1900;{total}"],
    )


def _ventas(path: Path, *, folio: str = "50") -> Path:
    return _csv(
        path,
        "Nro;Tipo Doc;Tipo Venta;Rut cliente;Razon Social;Folio;Fecha Docto;Monto Exento;Monto Neto;Monto IVA;Monto total",
        [f"1;33;Del Giro;{RUT_CLIENTE};Cliente Demo;{folio};05/09/2026;0;1000;190;1190"],
    )


def _descarga(tmp: Path, compras: Path | None, ventas: Path | None):
    def _bajar(_runtime, **kwargs):
        for codigo in ("conexion", "auth", "periodo", "compras", "ventas"):
            kwargs["on_step"](codigo)
        from integrations.sii.client import ResultadoDescarga

        return ResultadoDescarga(
            compras=compras,
            ventas=ventas,
            compras_vacio=compras is None,
            ventas_vacio=ventas is None,
        )

    return _bajar


def _correr(db: Session, company_id: int, rut: str, dest: Path, descargar) -> None:
    correr_actualizacion(
        db,
        Solicitud(
            company_id=company_id,
            company_name="Empresa de prueba",
            rut=rut,
            ejecucion_id=1,
            anio=2026,
            mes=9,
            actor_id=4,
            actor_email="fin@test.cl",
        ),
        destino=dest,
        descargar=descargar,
    )


def _estado(db: Session, company_id: int) -> dict:
    row = db.execute(
        text(
            """
            SELECT estado, error_publico, error_tecnico,
                   compras_importados, compras_omitidos, compras_errores,
                   ventas_importados, ventas_omitidos
            FROM fin.sii_ejecucion
            WHERE id = 1 AND company_id = :company
            """
        ),
        {"company": company_id},
    ).mappings().one()
    return dict(row)


def test_login_correcto_incorrecto_e_intervencion():
    from integrations.sii.auth_result import frase_login

    assert clasificar_resultado_login(url="https://www.sii.cl/", texto="", tiene_cookie_rut=True) == "ok"
    rechazo = "La Clave Tributaria ingresada no es correcta, verifique el teclado."
    assert (
        clasificar_resultado_login(
            url="https://zeusr.sii.cl/cgi_AUT2000/CAutInicio.cgi",
            texto=rechazo + "\nInformación sobre Clave Tributaria en el menú.",
            tiene_cookie_rut=False,
        )
        == "credencial"
    )
    assert frase_login(rechazo) == rechazo
    assert (
        clasificar_resultado_login(
            url="https://zeusr.sii.cl/AUT2000/InicioAutenticacion/IngresoRutClave.html",
            texto="Ingresar Clave Tributaria",
            tiene_cookie_rut=False,
        )
        == "desconocido"
    )
    assert (
        clasificar_resultado_login(url="https://zeusr.sii.cl/", texto="Complete el captcha", tiene_cookie_rut=False)
        == "intervencion"
    )


def test_la_importacion_distingue_proveedor_y_cliente():
    from types import SimpleNamespace

    from crud.tesoreria.sii import contraparte_de_documento

    compra = SimpleNamespace(
        direccion="RECIBIDO",
        rut_emisor=RUT_B,
        rut_receptor=RUT_A,
        razon_social="Proveedor Sur",
    )
    venta = SimpleNamespace(
        direccion="EMITIDO",
        rut_emisor=RUT_A,
        rut_receptor=RUT_CLIENTE,
        razon_social="Cliente Norte",
    )
    assert contraparte_de_documento(compra) == ("proveedor", RUT_B, "Proveedor Sur")
    assert contraparte_de_documento(venta) == ("cliente", RUT_CLIENTE, "Cliente Norte")
    propio = SimpleNamespace(
        direccion="RECIBIDO",
        rut_emisor=RUT_A,
        rut_receptor=RUT_A,
        razon_social="Misma empresa",
    )
    assert contraparte_de_documento(propio) is None


def test_el_sii_usa_el_rut_de_la_base_abierta():
    assert rut_para_consulta_sii(rut_base=RUT_A, rut_contexto=RUT_A) == RUT_A
    assert rut_para_consulta_sii(rut_base="", rut_contexto=RUT_A) == RUT_A
    with pytest.raises(ValueError):
        rut_para_consulta_sii(rut_base=RUT_A, rut_contexto=RUT_B)


def test_periodo_valido_e_invalido():
    assert parse_periodo("2026-09") == (2026, 9)
    with pytest.raises(ValueError):
        parse_periodo("2026-13")


def test_periodo_sin_informacion_no_falla(tmp_path: Path):
    archivo = _csv(
        tmp_path / "vacio.csv",
        "Nro;Tipo Doc;RUT Proveedor;Folio;Fecha Docto;Monto Neto;Monto IVA Recuperable;Monto Total",
        [],
    )
    assert leer_tabla(archivo).filas == []


def test_archivo_invalido(tmp_path: Path):
    texto = tmp_path / "pagina.csv"
    texto.write_text("<html><body>login</body></html>", encoding="utf-8")
    with pytest.raises(EstructuraInvalida):
        leer_tabla(texto)


def test_ventas_usan_el_rut_de_la_empresa(tmp_path: Path):
    archivo = _ventas(tmp_path / "ventas.csv")
    tabla = leer_tabla(archivo)
    empresa_a = normalizar_tabla(tabla, direccion="EMITIDO", rut_empresa=RUT_A, anio=2026, mes=9)
    empresa_b = normalizar_tabla(tabla, direccion="EMITIDO", rut_empresa=RUT_B, anio=2026, mes=9)
    assert empresa_a[0].documento is not None and empresa_a[0].documento.rut_emisor == RUT_A
    assert empresa_b[0].documento is not None and empresa_b[0].documento.rut_emisor == RUT_B


def test_dos_ejecuciones_no_duplican(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = _engine()
    db = _preparar(engine, 11, RUT_A, monkeypatch)
    compras = _compras(tmp_path / "compras.csv")
    ventas = _ventas(tmp_path / "ventas.csv")
    _correr(db, 11, RUT_A, tmp_path, _descarga(tmp_path, compras, ventas))
    primero = _estado(db, 11)
    assert primero["estado"] == "COMPLETADO"
    assert primero["compras_importados"] == 1
    assert primero["ventas_importados"] == 1
    db.execute(text("UPDATE fin.sii_ejecucion SET estado = 'EN_PROCESO', error_publico = NULL WHERE id = 1"))
    db.commit()
    _correr(db, 11, RUT_A, tmp_path, _descarga(tmp_path, compras, ventas))
    segundo = _estado(db, 11)
    assert segundo["compras_importados"] == 0
    assert segundo["compras_omitidos"] == 1
    assert segundo["ventas_importados"] == 0
    assert segundo["ventas_omitidos"] == 1
    total = db.execute(text("SELECT COUNT(*) FROM fin.documento_tributario")).scalar()
    assert int(total or 0) == 2


def test_documento_con_montos_invalidos_no_entra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = _engine()
    db = _preparar(engine, 11, RUT_A, monkeypatch)
    compras = _compras(tmp_path / "mal.csv", total="1")
    _correr(db, 11, RUT_A, tmp_path, _descarga(tmp_path, compras, None))
    estado = _estado(db, 11)
    assert estado["estado"] == "COMPLETADO_CON_OBSERVACIONES"
    assert estado["compras_errores"] == 1
    assert estado["compras_importados"] == 0


def test_error_de_descarga_no_importa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = _engine()
    db = _preparar(engine, 11, RUT_A, monkeypatch)

    def _falla(_runtime, **kwargs):
        raise SiiEtapaError("Descarga de Registro de Compras", "El SII no respondió dentro del tiempo esperado.")

    _correr(db, 11, RUT_A, tmp_path, _falla)
    estado = _estado(db, 11)
    assert estado["estado"] == "ERROR"
    assert "Descarga de Registro de Compras" in (estado["error_publico"] or "")
    assert "No se importaron nuevos documentos." in (estado["error_publico"] or "")
    assert CLAVE not in (estado["error_publico"] or "")
    assert int(db.execute(text("SELECT COUNT(*) FROM fin.documento_tributario")).scalar() or 0) == 0


def test_error_durante_importacion_revierte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = _engine()
    db = _preparar(engine, 11, RUT_A, monkeypatch)

    def _revienta(db_sesion, doc, *, ejecucion_id):
        raise RuntimeError(f"fallo {CLAVE}")

    monkeypatch.setattr("services.tesoreria.actualizacion.crud_sii.insertar_si_nuevo", _revienta)
    _correr(db, 11, RUT_A, tmp_path, _descarga(tmp_path, _compras(tmp_path / "c.csv"), _ventas(tmp_path / "v.csv")))
    estado = _estado(db, 11)
    assert estado["estado"] == "ERROR"
    assert CLAVE not in (estado["error_tecnico"] or "")
    assert CLAVE not in (estado["error_publico"] or "")
    assert int(db.execute(text("SELECT COUNT(*) FROM fin.documento_tributario")).scalar() or 0) == 0


def test_empresa_a_no_escribe_en_la_base_de_b(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    motor_a = _engine()
    motor_b = _engine()
    db_a = _preparar(motor_a, 11, RUT_A, monkeypatch)
    db_b = _preparar(motor_b, 22, RUT_B, monkeypatch)
    _correr(
        db_a,
        11,
        RUT_A,
        tmp_path / "a",
        _descarga(tmp_path, _compras(tmp_path / "ca.csv"), _ventas(tmp_path / "va.csv")),
    )
    assert int(db_a.execute(text("SELECT COUNT(*) FROM fin.documento_tributario")).scalar() or 0) == 2
    assert int(db_b.execute(text("SELECT COUNT(*) FROM fin.documento_tributario")).scalar() or 0) == 0
    emisor = db_a.execute(
        text("SELECT rut_emisor FROM fin.documento_tributario WHERE direccion = 'EMITIDO'")
    ).scalar()
    assert emisor == RUT_A


def test_multiempresa_no_toma_el_rut_de_otra_fuente():
    assert rut_de_empresa_activa(por_base=True, rut_contexto=RUT_A, rut_legado=RUT_B) == RUT_A
    pre = validar_precondiciones(
        autenticado=True,
        puede_actualizar=True,
        company_id=11,
        rut_empresa=RUT_A,
        anio=2026,
        mes=9,
        tiene_credencial=True,
        rut_credencial=RUT_B,
        hay_ejecucion_activa=False,
        esquema_listo=True,
    )
    assert pre.ok is False
    assert "no corresponde" in pre.mensaje


def test_sin_credencial_y_sin_permiso():
    sin_clave = validar_precondiciones(
        autenticado=True,
        puede_actualizar=True,
        company_id=11,
        rut_empresa=RUT_A,
        anio=2026,
        mes=9,
        tiene_credencial=False,
        rut_credencial="",
        hay_ejecucion_activa=False,
        esquema_listo=True,
    )
    assert sin_clave.ok is False
    assert "credenciales" in sin_clave.mensaje.lower()
    from core.rbac import usuario_puede_actualizar_sii, usuario_puede_ver_tesoreria

    rrhh = {"roles": ["RRHH"], "visibleModules": ["PRINCIPAL", "RRHH"]}
    consulta = {"roles": ["CONSULTA"], "visibleModules": ["PRINCIPAL", "FINANZAS"]}
    finanzas = {"roles": ["FINANZAS"], "visibleModules": ["PRINCIPAL", "FINANZAS"]}
    assert usuario_puede_ver_tesoreria(rrhh) is False
    assert usuario_puede_actualizar_sii(rrhh) is False
    assert usuario_puede_ver_tesoreria(consulta) is True
    assert usuario_puede_actualizar_sii(consulta) is False
    assert usuario_puede_actualizar_sii(finanzas) is True


def test_en_windows_el_navegador_usa_un_loop_que_puede_lanzar_procesos():
    import asyncio
    import sys

    from integrations.sii.client import _preparar_lanzamiento_navegador

    if sys.platform != "win32":
        _preparar_lanzamiento_navegador()
        return
    anterior = asyncio.get_event_loop_policy()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        _preparar_lanzamiento_navegador()
        assert isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy)
    finally:
        asyncio.set_event_loop_policy(anterior)


def test_la_clave_no_queda_en_claro_ni_en_el_codigo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SII_CREDENTIALS_KEY", "k" * 40)
    cifrado = encrypt_secret(CLAVE)
    assert CLAVE not in cifrado
    assert decrypt_secret(cifrado) == CLAVE
    assert CLAVE not in scrub(f"fallo {CLAVE}", CLAVE)
    for relativo in ("integrations/sii", "services/tesoreria", "routes/ui/tesoreria.py"):
        base = ROOT / relativo
        archivos = [base] if base.is_file() else list(base.rglob("*.py"))
        for archivo in archivos:
            texto = archivo.read_text(encoding="utf-8")
            assert "SII_PASSWORD" not in texto
            assert "SII_USER" not in texto
            assert "GAVAL" not in texto
    ruta = (ROOT / "routes" / "ui" / "tesoreria.py").read_text(encoding="utf-8")
    assert "company_id: int = Form" not in ruta
    sql = (ROOT / "crud" / "tesoreria" / "sii.py").read_text(encoding="utf-8")
    assert "ON CONFLICT (direccion, tipo, folio, rut_emisor) DO NOTHING" in sql
    assert "company_id = :company_id" in sql
