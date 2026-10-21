# docs/leasing_financiero_fase1.md

# Leasing financiero — Fase 1 (cotización)

Flujo operativo:

1. **Borrador / Cotizada** — el ejecutivo ingresa cliente, activo, pie, tasa, plazo y residual. El sistema calcula monto a financiar y la tabla de amortización. El activo queda en estado `COTIZADO` (no comprado).
2. **En evaluación** — se envía a evaluación comercial / scoring de crédito.
3. **Aprobada** — crédito o condiciones comerciales aprobadas.
4. **Acuerdo firmado** — se formaliza el contrato de leasing. Recién aquí se habilita la compra del bien.
5. **Activo pendiente de compra** — se puede emitir OC y registrar factura al proveedor.
6. **Activo adquirido** — el bien fue comprado. Recién entonces existe adquisición.

Estados de cierre: **Rechazada**, **Anulada**.

## Cálculo

- Método francés (cuota fija por periodo).
- Tasa **anual** → tasa periódica efectiva `i = (1 + r)^(1/n) − 1`.
- Tasa **mensual** → se usa como tasa del periodo (si el pago es mensual).
- Cuota con residual FV: `C = [PV·i − FV·i/(1+i)^n] / [1 − 1/(1+i)^n]`.
- Redondeo HALF UP a 2 decimales. La última cuota cierra el saldo exactamente.
- IVA referencial sobre la cuota neta cuando la operación está afecta.

## Exportación

- Excel: hojas `Resumen` y `Amortización`, archivo `leasing_financiero_cotizacion_[id]_[cliente].xlsx`.
- PDF corporativo EvaluaERP con tabla completa, encabezado, pie de página y notas legales.

## Seguridad

Rutas bajo sesión. GET de consulta y descargas: permiso de consulta. POST/PUT: permiso de mutación. Aprobación / acuerdo / adquisición: Finanzas o Admin. CSRF en formularios. Validación de negocio en backend. ORM / parámetros. Plantillas Jinja (escape automático); el simulador usa `textContent`.
