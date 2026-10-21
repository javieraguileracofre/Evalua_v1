# Motor profesional de Valor Residual — Leasing Operativo

**Versión del modelo:** `RV-2026.10.01`

## Objetivo

Estimar, al cotizar Leasing Operativo:

| Concepto | Significado |
|----------|-------------|
| PRECIO_COMPRA | Costo de adquisición |
| VALOR_MERCADO_ACTUAL | Precio de mercado ponderado hoy |
| VALOR_RESIDUAL (escenarios) | Valor comercial proyectado al término |
| VALOR_LIBRO | BOOK_VALUE según política contable |
| VALOR_TRIBUTARIO | TAX_VALUE (normativa SII / LIR) |
| VALOR_RECUPERO_NETO | Venta esperada − costos |
| RESULTADO_ESPERADO_VENTA | Recupero vs valor libro |
| DEAL_SCORE / decisión | Calidad económica de la operación |

Estos conceptos **no se mezclan**.

## Arquitectura

```
routes/api/lop.py  (sin lógica financiera)
        ↓
services/leasing_operativo/residual_value_service.py
        ├── market_data/ (providers, comparator, valuation)
        ├── depreciation_service.py   (BOOK / TAX / MARKET)
        ├── reconditioning_service.py
        ├── sale_recovery_service.py
        ├── residual_risk_service.py
        ├── lease_profitability_service.py
        ├── tax_rules_cl.py
        └── accounting_bridge.py
        ↓
cotizacion_flota.estimar_residual_unidad  →  simulador UI
```

## Mercado

Proveedores desacoplados:

- `ChileautosProvider` (peso default 50%)
- `MercadoLibreAutosProvider` (30%)
- `YapoAutosProvider` (20%) — importación/autorizada/manual; **sin scraping anti-bot**
- `AutocosmosProvider` (0% por defecto) — respaldo auditable (links/fotos)

Pesos en política `residual_value_v1.market_data_weights` (administrable).

Comparables conservan `url`, `image_url` (proxy CSP) y `comparability_score`.

## API

Prefijo canónico: `/api/comercial/leasing-operativo`

Alias: `/api/leasing` (mismos paths)

| Método | Path |
|--------|------|
| POST | `/residual-value/calculate` |
| POST | `/residual-value/market-search` |
| GET | `/residual-value/{cotizacion_id}` |
| GET | `/residual-value/{cotizacion_id}/comparables` |
| GET | `/residual-value/{cotizacion_id}/scenarios` |
| GET | `/residual-value/{cotizacion_id}/profitability` |
| POST | `/residual-value/override` |

## Persistencia

- `leasing_op_residual_value_curve`
- `leasing_op_market_valuation_snapshot`
- `leasing_op_residual_override`
- Política `residual_value_v1`

Migración: `db/psql/139_leasing_operativo_residual_engine.sql` + Alembic `0003_lop_residual_engine`.

## Override manual

Si el usuario cambia el residual respecto del modelo:

1. `MANUAL_OVERRIDE = true`
2. Advertencia en UI
3. Registro en `leasing_op_residual_override` (usuario, fecha, valores, motivo)

## Contabilidad

`accounting_bridge` prepara payload; **no** genera asientos definitivos hasta validar naturaleza tributaria del `tipo_contrato`.

## Integración UI

Simulador: `/comercial/leasing-operativo/simulador` — paso 3 «Análisis de Valor Residual».

Se mantienen links de cotizaciones/avisos e imágenes como respaldo auditable.
