# Fuentes normativas — depreciación y leasing (Chile)

Documento de respaldo del motor residual LOP. **Fuentes primarias SII / LIR** (no blogs).

## Separación obligatoria

| Capa | Uso en EvaluaERP |
|------|------------------|
| BOOK_VALUE | Política contable interna (lineal / vida útil / residual contable) |
| TAX_VALUE | Parámetros tributarios con `fuente_normativa`, `articulo`, `circular`, vigencias |
| MARKET_VALUE | Estimación económica de mercado (no normativa) |

## Arrendamiento operativo vs leasing financiero

| tipo_contrato | Deprecia arrendador | Art. 37 bis |
|---------------|---------------------|-------------|
| ARRENDAMIENTO_OPERATIVO | Sí (bien en patrimonio) | No |
| LEASING_FINANCIERO | No (tratamiento art. 37 bis) | Sí |
| ARRENDAMIENTO_CON_OPCION_COMPRA | No (equivalente financiero) | Sí |

**No** se reutiliza automáticamente la lógica de leasing financiero para un verdadero arrendamiento operativo.

## Fuentes prioritarias consultadas

1. **Ley sobre Impuesto a la Renta — Art. 31 y Art. 31 N°5**  
   Cuota anual de depreciación de bienes del activo inmovilizado en uso en el giro, sobre valor neto revalorizado (art. 41).

2. **Circular SII N°53 de 2020**  
   Limitaciones de gasto en adquisición/arrendamiento de automóviles, station wagons y similares cuando no es giro habitual; excepciones cuando el giro es adquisición/arrendamiento de automóviles.

3. **Art. 37 bis LIR (Ley 21.420) + Circular SII N°5 de 2024**  
   Contratos de arrendamiento con opción de compra / leasing financiero celebrados desde 01-01-2023: el arrendatario reconoce el bien como activo tributario y deprecia; el arrendador reconoce renta de intereses (no arriendos).  
   **Vigencia:** contratos desde 1° de enero de 2023.

4. Jurisprudencia administrativa SII relativa a art. 31 N°5 (depreciación sobre valor neto revalorizado).

## Parámetros en sistema

Archivo: `services/leasing_operativo/tax_rules_cl.py`  
Override vía política `residual_value_v1.tax_rules`.

Cada regla expone:

- `fuente_normativa`
- `articulo`
- `circular`
- `fecha_vigencia`
- `fecha_actualizacion`

## Advertencia

Las vidas útiles y porcentajes residuales tributarios del motor son **parametrizables** y deben validarse con la tabla de vidas útiles SII / asesoría tributaria de la empresa antes de contabilizar asientos definitivos.
