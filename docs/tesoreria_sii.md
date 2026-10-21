# Tesorería — actualización de compras y ventas desde el SII

Módulo de EvaluaERP para ver las facturas de compra y de venta de la empresa activa y cargarlas desde el Registro de Compras y Ventas del Servicio de Impuestos Internos.

La carga usa un navegador real (Playwright + Chromium). No simula el sitio con `requests` y no intenta saltarse CAPTCHA, ClaveÚnica ni un segundo factor.

## 1. Dependencias instaladas

```text
pip install -r requirements.txt
python -m playwright install chromium
```

Se agrega `playwright` a `requirements.txt`. Chromium se descarga aparte y no viaja en el repositorio.

## 2. Variables de configuración

| Variable | Uso | Valor por defecto |
| --- | --- | --- |
| `SII_LOGIN_URL` | Página de clave tributaria | URL oficial observada en zeusr.sii.cl |
| `SII_RCV_URL` | Registro de Compras y Ventas | `https://www4.sii.cl/consdcvinternetui/#/index` |
| `SII_HEADLESS` | `true` oculta el navegador; `false` lo muestra | `true` |
| `SII_TIMEOUT` | Segundos de espera de navegación | `45` |
| `SII_DOWNLOAD_TIMEOUT` | Segundos de espera de cada descarga | `120` |
| `SII_CREDENTIALS_KEY` | Clave para cifrar la clave tributaria | Si falta, se usa `SECRET_KEY` |

No ponga la clave tributaria en `.env` ni en el código. Se guarda cifrada en la base de la empresa.

## 3. Cómo configurar las credenciales SII

1. Inicie sesión en EvaluaERP y seleccione la empresa.
2. Abra **Tesorería → Clave SII**.
3. El RUT que se usa es el de esa empresa. No se puede ingresar el RUT de otra.
4. Escriba la clave tributaria y guarde.

La pantalla no vuelve a mostrar la clave. En la base queda en `fin.sii_credencial.secreto_cifrado`.

## 4. Cómo ejecutar en desarrollo

En el `.env` de la máquina local:

```text
SII_HEADLESS=false
SII_TIMEOUT=60
```

Levante EvaluaERP como de costumbre, entre a Tesorería, elija el período contable y pulse **Actualizar compras y ventas**. Con el navegador visible puede ver el flujo y, si el SII pide una validación, completarla usted y pulsar **Continuar**.

Aplique antes la migración `0013_tesoreria_sii` (`alembic upgrade head` o el arranque de desarrollo que ya migra).

## 5. Cómo ejecutar en producción

```text
SII_HEADLESS=true
```

El proceso corre en el servidor, en un hilo del propio EvaluaERP. No hace falta Celery ni Redis. Si el SII pide CAPTCHA o un segundo factor, la ejecución queda en `REQUIERE_INTERVENCION_USUARIO` y no importa documentos: en un servidor sin pantalla no se puede completar esa validación. En ese caso hay que correr la actualización desde el equipo donde EvaluaERP tiene navegador visible.

## 6. Cómo funciona la descarga

1. Se valida usuario, permiso, empresa activa, período y que la credencial sea de esa empresa.
2. Playwright abre la página de clave tributaria observada el 12 de octubre de 2026: formulario `#rutcntr` / `#clave`, botón `#bt_ingresar`.
3. Si aparece cookie `RUT_NS`, entra al Registro de Compras y Ventas, elige año y mes y descarga compras y ventas.
4. El HTML autenticado de ese registro no se pudo inspeccionar sin credenciales (el sitio redirige al login). Los botones se buscan por el texto «Consultar», «Compra», «Venta» y «Descargar». Si el SII cambia la pantalla, la ejecución se detiene con un mensaje de esa etapa.

## 7. Cómo se almacenan los archivos

Quedan en el almacenamiento de la empresa, no se borran al terminar:

```text
storage/sii/{empresa}/{aaaa-mm}/          (instalación de una sola base)
storage/companies/{codigo}/sii/{empresa}/{aaaa-mm}/
```

Cada ejecución guarda `compras_original_{id}` y `ventas_original_{id}` con nombre, hash SHA-256, tamaño y ruta en `fin.sii_archivo`.

## 8. Cómo se evita la duplicación

El libro interno `fin.documento_tributario` ya es único por dirección (compra o venta), tipo, folio y RUT emisor. Una segunda actualización del mismo período omite esos documentos y los cuenta como «ya existentes». No se generan asientos contables.

En ventas, el RUT emisor es el de la empresa activa. En compras, el RUT emisor es el del proveedor y el receptor es la empresa activa.

## 9. Cómo revisar errores

La pantalla de la ejecución muestra la etapa en lenguaje claro. El detalle técnico queda en `fin.sii_ejecucion.error_tecnico` y en el log `evalua.sii`, con el formato `SII | empresa=… | ejecución=…`. La clave tributaria no se escribe en ese log ni en la pantalla.

## 10. Limitaciones conocidas

- No se evade CAPTCHA, MFA ni ClaveÚnica. Si el SII los pide, hace falta una persona frente al navegador.
- El registro autenticado puede cambiar de botones sin aviso. Los textos de navegación están centralizados en `integrations/sii/selectors.py`.
- Solo se importan filas cuyos montos cuadran (neto + exento + IVA + otros impuestos reconocidos = total). Una fila con impuestos que el archivo no separa queda como error de esa fila y no se inserta.
- No hay sincronización diaria, bancos, Previred ni contabilización automática.
- Cada empresa usa su propia base. La actualización no acepta un identificador de empresa en el formulario.
