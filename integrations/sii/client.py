# integrations/sii/client.py
# -*- coding: utf-8 -*-
"""Automatiza el navegador del SII. No evade CAPTCHA, MFA ni ClaveÚnica."""
from __future__ import annotations

import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from integrations.sii.auth_result import clasificar_resultado_login, frase_login
from integrations.sii.errors import SiiCredencialInvalida, SiiEtapaError, SiiIntervencionRequerida
from integrations.sii.rut import rut_para_formulario
from integrations.sii.selectors import (
    LOGIN_CLAVE,
    LOGIN_RUT,
    LOGIN_SUBMIT,
    MESES,
    PATRONES_DESCARGA,
    TEXTOS_SIN_DOCUMENTOS,
)

logger = logging.getLogger("evalua.sii")

StepCallback = Callable[[str], None]
InterventionCallback = Callable[[str], bool]


def _abrir_navegador(playwright, *, headless: bool):
    """Chrome normal. El SII rechaza la clave si detecta el navegador de automatización."""
    opciones = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled"],
        "ignore_default_args": ["--enable-automation"],
    }
    try:
        return playwright.chromium.launch(channel="chrome", **opciones)
    except Exception:
        logger.info("SII | no se encontró Chrome instalado; se usa el navegador incluido")
        return playwright.chromium.launch(**opciones)


def _preparar_lanzamiento_navegador() -> None:
    """Uvicorn en Windows deja un SelectorEventLoop, que no puede crear Chromium."""
    if sys.platform != "win32":
        return
    import asyncio

    if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy):
        return
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@dataclass(frozen=True)
class SiiRuntime:
    login_url: str
    rcv_url: str
    headless: bool
    timeout_ms: int
    download_timeout_ms: int


@dataclass(frozen=True)
class ResultadoDescarga:
    compras: Path | None
    ventas: Path | None
    compras_vacio: bool
    ventas_vacio: bool


def descargar_libros(
    runtime: SiiRuntime,
    *,
    rut: str,
    clave: str,
    anio: int,
    mes: int,
    dest: Path,
    company_id: int,
    ejecucion_id: int,
    on_step: StepCallback | None = None,
    al_intervenir: InterventionCallback | None = None,
) -> ResultadoDescarga:
    """Abre el SII, autentica y descarga los dos libros del período."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SiiEtapaError(
            "Conexión iniciada",
            "Falta Playwright en este equipo. Instálelo y descargue Chromium antes de actualizar.",
        ) from exc

    def paso(codigo: str) -> None:
        if on_step is not None:
            on_step(codigo)

    dest.mkdir(parents=True, exist_ok=True)
    paso("conexion")
    logger.info(
        "SII | empresa=%s | ejecución=%s | rut=%s | login iniciado",
        company_id,
        ejecucion_id,
        rut_para_formulario(rut),
    )
    _preparar_lanzamiento_navegador()
    with sync_playwright() as playwright:
        browser = _abrir_navegador(playwright, headless=runtime.headless)
        context = browser.new_context(accept_downloads=True, locale="es-CL")
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        page.set_default_timeout(runtime.timeout_ms)
        try:
            _autenticar(
                page,
                context,
                runtime,
                rut=rut,
                clave=clave,
                company_id=company_id,
                ejecucion_id=ejecucion_id,
                al_intervenir=al_intervenir,
                timeout=PlaywrightTimeout,
            )
            paso("auth")
            logger.info("SII | empresa=%s | ejecución=%s | login exitoso", company_id, ejecucion_id)
            _abrir_registro(page, runtime, timeout=PlaywrightTimeout)
            _elegir_periodo(page, anio, mes, timeout_ms=runtime.timeout_ms, timeout=PlaywrightTimeout)
            paso("periodo")
            logger.info(
                "SII | empresa=%s | ejecución=%s | período=%s-%02d",
                company_id,
                ejecucion_id,
                anio,
                mes,
            )
            compras, compras_vacio = _descargar_lado(
                page,
                lado="compras",
                dest=dest / f"compras_original_{ejecucion_id}",
                runtime=runtime,
                timeout=PlaywrightTimeout,
            )
            paso("compras")
            logger.info("SII | empresa=%s | ejecución=%s | compras descargadas", company_id, ejecucion_id)
            ventas, ventas_vacio = _descargar_lado(
                page,
                lado="ventas",
                dest=dest / f"ventas_original_{ejecucion_id}",
                runtime=runtime,
                timeout=PlaywrightTimeout,
            )
            paso("ventas")
            logger.info("SII | empresa=%s | ejecución=%s | ventas descargadas", company_id, ejecucion_id)
            return ResultadoDescarga(
                compras=compras,
                ventas=ventas,
                compras_vacio=compras_vacio,
                ventas_vacio=ventas_vacio,
            )
        finally:
            context.close()
            browser.close()


def _autenticar(page, context, runtime: SiiRuntime, *, rut: str, clave: str, company_id: int, ejecucion_id: int, al_intervenir, timeout) -> None:
    try:
        page.goto(runtime.login_url, wait_until="domcontentloaded")
        page.locator(LOGIN_RUT).fill(rut_para_formulario(rut))
        page.locator(LOGIN_CLAVE).fill(clave)
        _enviar_login(page, runtime, timeout)
    except SiiEtapaError:
        raise
    except timeout as exc:
        raise SiiEtapaError(
            "Autenticación",
            "El SII no respondió dentro del tiempo esperado.",
        ) from exc
    except Exception as exc:
        raise SiiEtapaError(
            "Autenticación",
            "No se pudo enviar el formulario de clave tributaria.",
        ) from exc
    _exigir_sesion(
        page,
        context,
        company_id=company_id,
        ejecucion_id=ejecucion_id,
        al_intervenir=al_intervenir,
        runtime=runtime,
    )


def _enviar_login(page, runtime: SiiRuntime, timeout) -> None:
    """El botón del SII valida y llama form.submit(); el onsubmit cancela el clic."""
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=runtime.timeout_ms):
            page.evaluate("() => { ejecuta_opcion(); }")
    except Exception as exc:
        if "CAutInicio" in (page.url or ""):
            return
        alerta = _alerta_formulario(page)
        if alerta:
            raise SiiEtapaError("Autenticación", alerta) from exc
        if isinstance(exc, timeout):
            raise SiiEtapaError(
                "Autenticación",
                "El SII no respondió dentro del tiempo esperado.",
            ) from exc
        raise SiiEtapaError(
            "Autenticación",
            "No se pudo enviar el formulario de clave tributaria.",
        ) from exc


def _alerta_formulario(page) -> str:
    try:
        texto = page.locator("#alert_placeholder").inner_text(timeout=1000)
    except Exception:
        return ""
    return " ".join((texto or "").split())[:400]


def _exigir_sesion(page, context, *, company_id: int, ejecucion_id: int, al_intervenir, runtime: SiiRuntime) -> None:
    resultado, texto = _clasificar_pagina(page, context)
    if resultado == "ok":
        return
    if resultado == "intervencion":
        if runtime.headless or al_intervenir is None:
            raise SiiIntervencionRequerida(
                "Autenticación",
                "El SII solicitó una validación adicional. EvaluaERP no intenta saltarse ese control. "
                "Ejecute la actualización con el navegador visible (SII_HEADLESS=false), complete la "
                "validación en la ventana y pulse Continuar.",
            )
        logger.info(
            "SII | empresa=%s | ejecución=%s | requiere intervención del usuario",
            company_id,
            ejecucion_id,
        )
        continuo = al_intervenir(
            "El SII pidió una validación adicional en la ventana del navegador. "
            "Complétela usted y luego pulse Continuar. EvaluaERP no resuelve CAPTCHA ni segundo factor."
        )
        if not continuo or _clasificar_pagina(page, context)[0] != "ok":
            raise SiiIntervencionRequerida(
                "Autenticación",
                "La validación adicional del SII no quedó completada. No se importaron documentos.",
            )
        return
    if resultado == "credencial":
        raise SiiCredencialInvalida(
            "Autenticación",
            frase_login(texto) or "El SII no aceptó el RUT o la clave tributaria de la empresa.",
        )
    raise SiiEtapaError(
        "Autenticación",
        frase_login(texto) or "No se pudo confirmar el ingreso al SII.",
    )


def _clasificar_pagina(page, context) -> tuple[str, str]:
    try:
        texto = page.locator("body").inner_text(timeout=5000)
    except Exception:
        texto = ""
    cookies = context.cookies()
    tiene = any(cookie.get("name") == "RUT_NS" and cookie.get("value") for cookie in cookies)
    return clasificar_resultado_login(url=page.url, texto=texto, tiene_cookie_rut=tiene), texto


def _abrir_registro(page, runtime: SiiRuntime, *, timeout) -> None:
    try:
        page.goto(runtime.rcv_url, wait_until="domcontentloaded")
    except timeout as exc:
        raise SiiEtapaError(
            "Registro de Compras y Ventas",
            "El SII no abrió el registro dentro del tiempo esperado.",
        ) from exc
    if "IngresoRutClave" in page.url or "CAutInicio" in page.url:
        raise SiiEtapaError(
            "Registro de Compras y Ventas",
            "La sesión del SII no permitió abrir el Registro de Compras y Ventas.",
        )


def _elegir_periodo(page, anio: int, mes: int, *, timeout_ms: int, timeout) -> None:
    """El registro es AngularJS: el <select> aparece antes de que existan las opciones."""
    valor_mes = f"{mes:02d}"
    valor_anio = str(anio)
    try:
        page.wait_for_function(
            """([mes, anio]) => {
              const opciones = [...document.querySelectorAll('select option')];
              const tiene = (esperado) => opciones.some((opcion) => {
                const valor = (opcion.value || '').trim();
                const texto = (opcion.textContent || '').trim();
                return valor === esperado || texto.toLowerCase() === esperado.toLowerCase();
              });
              return tiene(mes) && tiene(anio);
            }""",
            arg=[valor_mes, valor_anio],
            timeout=timeout_ms,
        )
    except Exception as exc:
        raise SiiEtapaError(
            "Período seleccionado",
            "No se encontró el selector de período en el Registro de Compras y Ventas. "
            "El SII puede haber cambiado esa pantalla.",
        ) from exc
    mes_ok = _marcar_select(page, "#periodoMes", valor_mes, MESES[mes])
    anio_ok = _marcar_select(page, "select[ng-model='periodoAnho']", valor_anio, valor_anio)
    if not mes_ok:
        mes_ok = _elegir_en_selects(page, [valor_mes, str(mes), MESES[mes]])
    if not anio_ok:
        anio_ok = _elegir_en_selects(page, [valor_anio])
    if not anio_ok or not mes_ok:
        raise SiiEtapaError(
            "Período seleccionado",
            "No se encontró el selector de período en el Registro de Compras y Ventas. "
            "El SII puede haber cambiado esa pantalla.",
        )
    _aplicar_modelo_angular(page)
    consultar = page.get_by_role("button", name=re.compile(r"^\s*consultar\s*$", re.IGNORECASE))
    if consultar.count():
        try:
            consultar.first.click()
            page.locator("#tabCompra, #tabVenta").first.wait_for(state="visible", timeout=timeout_ms)
        except timeout:
            return
        except Exception:
            return


def _marcar_select(page, selector: str, valor: str, etiqueta: str) -> bool:
    control = page.locator(selector)
    try:
        if control.count() == 0:
            return False
        control.first.select_option(value=valor)
        return True
    except Exception:
        try:
            control.first.select_option(label=etiqueta)
            return True
        except Exception:
            return False


def _aplicar_modelo_angular(page) -> None:
    """AngularJS no siempre escucha el change que dispara Playwright."""
    try:
        page.evaluate(
            """() => {
              const tocar = (el) => {
                if (!el) return;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                const angular = window.angular;
                if (!angular || !angular.element) return;
                const scope = angular.element(el).scope();
                if (scope && scope.$applyAsync) scope.$applyAsync();
              };
              tocar(document.querySelector('#periodoMes'));
              tocar(document.querySelector("select[ng-model='periodoAnho']"));
            }"""
        )
    except Exception:
        return


def _elegir_en_selects(page, valores: list[str]) -> bool:
    selects = page.locator("select")
    try:
        cantidad = selects.count()
    except Exception:
        return False
    buscados = {valor.strip().lower() for valor in valores if valor.strip()}
    for indice in range(cantidad):
        select = selects.nth(indice)
        options = select.locator("option")
        try:
            total = options.count()
        except Exception:
            continue
        for opcion in range(total):
            nodo = options.nth(opcion)
            valor = (nodo.get_attribute("value") or "").strip()
            etiqueta = (nodo.text_content() or "").strip()
            if valor.lower() in buscados or etiqueta.lower() in buscados:
                select.select_option(value=valor)
                return True
    return False


def _abrir_pestana(page, lado: str) -> None:
    if lado == "compras":
        pestana = page.locator("#tabCompra")
        resumen = re.compile(r"resumen registro de compras", re.IGNORECASE)
    else:
        pestana = page.locator("a").filter(has_text=re.compile(r"^\s*venta\s*$", re.IGNORECASE))
        resumen = re.compile(r"resumen registro de ventas", re.IGNORECASE)
    if pestana.count() == 0:
        return
    pestana.first.click()
    try:
        page.get_by_text(resumen).first.wait_for(state="visible", timeout=15000)
    except Exception:
        return


def _descargar_lado(page, *, lado: str, dest: Path, runtime: SiiRuntime, timeout) -> tuple[Path | None, bool]:
    etapa = "Descarga de Registro de Compras" if lado == "compras" else "Descarga de Registro de Ventas"
    try:
        _abrir_pestana(page, lado)
    except Exception as exc:
        raise SiiEtapaError(etapa, "No se pudo abrir la sección del registro.") from exc
    _esperar_panel(page, runtime.timeout_ms)
    if _periodo_sin_documentos(page):
        return None, True
    boton = _boton_descarga(page)
    if boton is None:
        if _periodo_sin_documentos(page):
            return None, True
        raise SiiEtapaError(
            etapa,
            "No se encontró la descarga del registro. El SII puede haber cambiado esa pantalla.",
        )
    try:
        with page.expect_download(timeout=runtime.download_timeout_ms) as descarga_info:
            boton.click()
        descarga = descarga_info.value
    except timeout as exc:
        if _periodo_sin_documentos(page):
            return None, True
        raise SiiEtapaError(etapa, "El SII no respondió dentro del tiempo esperado.") from exc
    except Exception as exc:
        raise SiiEtapaError(etapa, "El SII no entregó el archivo del registro.") from exc
    sufijo = Path(descarga.suggested_filename or "").suffix.lower() or ".csv"
    if sufijo not in {".csv", ".txt", ".xlsx", ".xls"}:
        sufijo = ".csv"
    destino = dest.with_suffix(sufijo)
    descarga.save_as(str(destino))
    return destino, False


def _esperar_panel(page, timeout_ms: int) -> None:
    aviso = re.compile(
        r"descargar detalles|no hay información de registro|no hay informacion de registro",
        re.IGNORECASE,
    )
    try:
        page.get_by_text(aviso).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        return


def _boton_descarga(page):
    """El detalle trae el RUT de cada proveedor o cliente. El resumen no."""
    candidatos = page.locator("button, a, input[type='button'], input[type='submit']")
    for patron in PATRONES_DESCARGA:
        coincidencias = candidatos.filter(has_text=patron)
        try:
            cantidad = coincidencias.count()
        except Exception:
            continue
        for indice in range(cantidad):
            boton = coincidencias.nth(indice)
            nombre = (boton.text_content() or boton.get_attribute("value") or "").lower()
            if "resumen" in nombre or "boleta" in nombre:
                continue
            return boton
    return None


def _periodo_sin_documentos(page) -> bool:
    try:
        texto = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        return False
    return any(marca in texto for marca in TEXTOS_SIN_DOCUMENTOS)
