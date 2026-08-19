# Revision de configuracion de comisiones

## Caso revisado

Liquidacion: `Alberto Carrillo - June 2026`

Linea revisada:

- Conciliacion parcial: `account.partial.reconcile,2482`
- Factura: `00100001010000019891`
- Pago: `PBNK2/2026/00039`
- Fecha de aplicacion: `2026-06-26`
- Fecha de vencimiento: `2026-07-17`
- Dias vencidos: `-21`
- Bucket aplicado actualmente: `PLAZO 5`
- Porcentaje aplicado actualmente: `0%`

La factura no estaba vencida. Por eso el sistema la clasifica como `not_due`.

## Como calcula el modulo

El modulo calcula los dias vencidos asi:

```text
dias_vencidos = fecha_aplicacion_pago - fecha_vencimiento_factura
```

Regla interna:

- Si `dias_vencidos <= 0`, usa el bucket de tipo `not_due`.
- Si `dias_vencidos > 0`, usa un bucket de tipo `overdue` segun el rango de dias.

Por eso una factura pagada antes del vencimiento no cae en `1-45 dias`; cae en el bucket especial `not_due`.

## Configuracion esperada

### Antiguedad de cobro

| Condicion | Tipo esperado | Rango esperado | Comision base esperada |
| --- | --- | ---: | ---: |
| No vencido | `not_due` | `<= 0 dias` | `2%` |
| 0 - 45 dias / Plazo 1 | `overdue` | `1 - 45` | `2%` |
| 46 - 60 dias / Plazo 2 | `overdue` | `46 - 60` | `1.5%` |
| 61 - 90 dias / Plazo 3 | `overdue` | `61 - 90` | `1%` |
| Mas de 90 dias / Plazo 4 | `overdue` | `91 - 999` | `0%` |

### Cumplimiento de venta

| Cumplimiento de venta | Pago de comision esperado |
| --- | ---: |
| 110% o mas | 115% |
| 105% a 109% | 110% |
| 100% a 104% | 100% |
| 95% a 99% | 95% |
| 90% a 94% | 90% |
| 85% a 89% | 80% |
| 80% a 84% | 70% |
| 75% a 79% | 60% |
| 70% a 74% | 50% |
| Menos de 70% | 0% |

## Configuracion actual encontrada

Plan: `COMISIONES`

Vigencia:

- Inicio: `2026-04-01`
- Fin: `2026-12-31`
- Estado: `active`

### Antiguedad actual

| ID | Nombre actual | Tipo actual | Rango actual | Comision actual | Sirve |
| ---: | --- | --- | ---: | ---: | --- |
| 99 | `PLAZO 1` | `overdue` | `1 - 45` | `2%` | Si |
| 100 | `PLAZO 2` | `overdue` | `46 - 60` | `1.5%` | Si |
| 101 | `PLAZO 3` | `overdue` | `61 - 90` | `1%` | Si |
| 102 | `PLAZO 4` | `overdue` | `91 - 999` | `0%` | Si |
| 104 | `PLAZO 5` | `not_due` | `0 - 0` | `0%` | No |

### Cumplimiento actual

| ID | Nombre actual | Rango actual | Pago actual | Sirve |
| ---: | --- | ---: | ---: | --- |
| 51 | `CUMPLIMIENTO 1` | `110 - 200` | `115%` | Parcial |
| 73 | `CUMPLIMIENTO 2` | `105 - 109` | `110%` | Parcial |
| 74 | `CUMPLIMIENTO 3` | `100 - 104` | `100%` | Parcial |
| 75 | `CUMPLIMIENTO 4` | `95 - 99` | `95%` | Parcial |
| 76 | `CUMPLIMIENTO 5` | `90 - 94` | `90%` | Parcial |
| 77 | `CUMPLIMIENTO 6` | `85 - 89` | `80%` | Parcial |
| 78 | `CUMPLIMIENTO 7` | `80 - 84` | `70%` | Parcial |
| 79 | `CUMPLIMIENTO 8` | `75 - 79` | `60%` | Parcial |
| 80 | `CUMPLIMIENTO 9` | `70 - 74` | `50%` | Parcial |
| 81 | `CUMPLIMIENTO 10` | `0 - 69` | `0%` | Parcial |

## Que sirve

- Los buckets vencidos de `1 - 45`, `46 - 60`, `61 - 90` y `91 - 999` tienen los porcentajes correctos.
- El modulo calcula correctamente los dias vencidos usando la fecha de aplicacion contra la fecha de vencimiento.
- El caso revisado tiene `-21` dias vencidos, por lo que correctamente entra en el bucket `not_due`.
- Los porcentajes de cumplimiento estan cargados con los valores esperados: `115`, `110`, `100`, `95`, `90`, `80`, `70`, `60`, `50`, `0`.

## Que no sirve

### 1. Bucket de no vencido mal configurado

El bucket `not_due` esta configurado como:

```text
PLAZO 5 | not_due | 0%
```

Esto provoca que las facturas pagadas antes o en la fecha de vencimiento queden con comision `0%`.

Debe estar configurado como:

```text
No vencido | not_due | 2%
```

### 2. Nombre del bucket confunde la revision

El nombre `PLAZO 5` hace parecer que la factura cayo en un rango vencido incorrecto.

En realidad no cayo en un rango vencido; cayo en `not_due`, pero ese bucket esta mal nombrado.

### 3. Rangos de cumplimiento con huecos decimales

Los rangos actuales terminan en enteros. Ejemplo:

```text
105 - 109
100 - 104
```

Si el cumplimiento es `104.75%`, no entra en `100 - 104` ni en `105 - 109`.

Para evitar huecos, los rangos deben usar decimales:

```text
105 - 109.9999
100 - 104.9999
95 - 99.9999
```

### 4. Primer rango de cumplimiento tiene tope 200

La regla `110% o mas` esta configurada como `110 - 200`.

Si un vendedor supera `200%`, no entra en ninguna regla. Lo recomendable es ampliar el tope, por ejemplo:

```text
110 - 9999
```

## Impacto detectado

Para lineas con bucket `PLAZO 5` y dias vencidos `<= 0`:

| Alcance | Lineas | Base CRC | Comision actual | Comision si fuera 2% |
| --- | ---: | ---: | ---: | ---: |
| Alberto Carrillo - June 2026 | 67 | 13,423,192.18 | 0.00 | 268,463.84 |
| Allan Matamoros Ventas - June 2026 | 62 | 14,627,759.13 | 0.00 | 292,555.18 |
| Total historico encontrado | 225 | 46,171,265.61 | 0.00 | 923,425.31 |

## Correccion recomendada

### Paso 1. Corregir bucket no vencido

Actualizar la regla `104`:

```text
Nombre: No vencido
Tipo: not_due
Comision base: 2%
```

### Paso 2. Revisar rangos de cumplimiento

Actualizar los rangos para evitar huecos:

| Regla | Desde | Hasta | Pago |
| --- | ---: | ---: | ---: |
| 110% o mas | 110 | 9999 | 115 |
| 105% a 109% | 105 | 109.9999 | 110 |
| 100% a 104% | 100 | 104.9999 | 100 |
| 95% a 99% | 95 | 99.9999 | 95 |
| 90% a 94% | 90 | 94.9999 | 90 |
| 85% a 89% | 85 | 89.9999 | 80 |
| 80% a 84% | 80 | 84.9999 | 70 |
| 75% a 79% | 75 | 79.9999 | 60 |
| 70% a 74% | 70 | 74.9999 | 50 |
| Menos de 70% | 0 | 69.9999 | 0 |

### Paso 3. Regenerar liquidaciones afectadas

Despues de corregir la configuracion, regenerar las liquidaciones en borrador para que recalculen las lineas:

- `Alberto Carrillo - June 2026`
- `Allan Matamoros Ventas - June 2026`
- Cualquier otra liquidacion que tenga lineas con `PLAZO 5` / `not_due`

## Conclusion

El codigo esta clasificando correctamente el caso revisado como no vencido.

El problema es de configuracion: el bucket `not_due` existe, pero esta nombrado como `PLAZO 5` y tiene `0%` de comision. Eso hace que pagos antes del vencimiento no generen comision.
