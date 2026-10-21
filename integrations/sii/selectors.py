# integrations/sii/selectors.py
# -*- coding: utf-8 -*-
"""Selectores del SII centralizados.

Login observado el 2026-10-12 en
https://zeusr.sii.cl/AUT2000/InicioAutenticacion/IngresoRutClave.html
El formulario #myform publica RUT (#rutcntr) y clave tributaria (#clave)
hacia /cgi_AUT2000/CAutInicio.cgi. No había CAPTCHA en ese HTML.
El JS validaAut copia el cuerpo y el dígito a #rut y #dv antes de enviar.
La sesión exitosa deja la cookie RUT_NS.

El Registro de Compras y Ventas (www4.sii.cl/consdcvinternetui/#/index),
observado el 2026-10-12 ya autenticado, es AngularJS. Los períodos viven en
#periodoMes (valores 01–12) y select[ng-model=periodoAnho]. El <select>
aparece con la opción vacía antes de que Angular cargue los meses y años.
"""
from __future__ import annotations

import re

LOGIN_FORM = "#myform"
LOGIN_RUT = "#rutcntr"
LOGIN_CLAVE = "#clave"
LOGIN_RUT_OCULTO = "#rut"
LOGIN_DV_OCULTO = "#dv"
LOGIN_SUBMIT = "#bt_ingresar"

MESES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)

PATRON_CONSULTAR = re.compile(r"consultar", re.IGNORECASE)
PATRON_COMPRAS = re.compile(r"\bcompras?\b", re.IGNORECASE)
PATRON_VENTAS = re.compile(r"\bventas?\b", re.IGNORECASE)
PATRONES_DESCARGA = (
    re.compile(r"descargar\s+detalles", re.IGNORECASE),
    re.compile(r"descargar\s+detalle", re.IGNORECASE),
    re.compile(r"descargar", re.IGNORECASE),
)

TEXTOS_SIN_DOCUMENTOS = (
    "no se encontraron",
    "sin informacion",
    "sin información",
    "no existen registros",
    "no hay documentos",
    "no hay información de registro",
    "no hay informacion de registro",
    "no registra información",
    "no registra informacion",
    "sin movimientos",
)
