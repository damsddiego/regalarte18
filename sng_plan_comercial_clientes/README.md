# SNG Plan Comercial Clientes

## Objetivo

Este modulo permite construir un plan comercial anual o por rangos personalizados usando ventas historicas, DPP y metas segmentadas.

Sirve para:

- clasificar clientes por importancia comercial
- segmentarlos por comportamiento de pago
- distribuir una meta anual protegida
- dar seguimiento al avance real contra la meta
- exportar el plan a Excel

## Donde encontrarlo

Menu principal:

- `Ventas > Plan Comercial > Planes Comerciales`

Reporte de lineas:

- `Ventas > Plan Comercial > Reportes > Analisis de Lineas`

## Que hace el modulo

Cada plan trabaja con:

- un modo `Anual`, basado en `Ano Base` y `Ano Objetivo`
- o un modo `Personalizado`, con rangos base y objetivo de igual duracion
- una compania
- reglas de segmentacion por venta
- reglas de segmentacion por DPP
- una meta total protegida o un factor global

Con esto el modulo genera una linea por cliente comercial y calcula:

- venta base
- participacion
- porcentaje acumulado
- segmento por venta
- DPP
- segmento DPP
- segmento final `Venta X / DPP Y`
- meta del periodo
- meta acumulada a la fecha
- meta mensual
- incremento
- venta acumulada actual
- promedio mensual
- crecimiento mensual
- cumplimiento

## Flujo recomendado de uso

### 1. Crear el plan

Ir a `Ventas > Plan Comercial > Planes Comerciales` y crear un registro nuevo.

Completar al menos:

- `Nombre`
- `Compania`
- `Tipo de Periodo`
- los anos base y objetivo, o los dos rangos de fechas personalizados

## 2. Definir la meta

Hay dos formas:

### Opcion A. Usar factor global

Activar `Usar Factor Global`.

Puede trabajar de dos maneras:

- definiendo `Factor Global`
- o definiendo `Meta Total Manual` o `Presupuesto Total`

Si define `Meta Total Manual` o `Presupuesto Total`, el sistema calcula automaticamente el `Factor Crecimiento Real` con base en la `Venta Base Total`.

Ejemplo:

- Venta Base Total = 1,000,000
- Meta Total Manual = 1,200,000
- Factor Crecimiento Real = 1.20

### Opcion B. Usar factores por segmento

Desactivar `Usar Factor Global`.

Entonces el sistema usa:

- `Factor Segmento A`
- `Factor Segmento B`
- `Factor Segmento C`

Esto permite que los clientes mas importantes tengan una meta distinta al resto.

## 3. Configurar segmentacion

### Segmentacion por venta

Los clientes se ordenan de mayor a menor venta base.

Luego se calcula:

- `Participacion`: porcentaje del cliente sobre la venta base total
- `% Acumulado`: suma acumulada de participacion

Y se asigna el segmento:

- `A` hasta el limite configurado en `Limite Segmento A`
- `B` hasta el limite configurado en `Limite Segmento B`
- `C` el resto

Configuracion sugerida similar al Excel:

- `Limite Segmento A = 70%`
- `Limite Segmento B = 90%`

### Segmentacion por DPP

El DPP mide cuantos dias tarda el cliente en pagar.

Se clasifica asi:

- `DPP A` si el DPP es menor o igual al `Limite DPP A`
- `DPP B` si el DPP es menor o igual al `Limite DPP B`
- `DPP C` si supera el `Limite DPP B`
- `Sin DPP` si no hay historial suficiente

Configuracion sugerida similar al Excel:

- `Limite DPP A = 30`
- `Limite DPP B = 45`
- `Etiqueta Sin DPP = Sin DPP`

## 4. Cargar clientes

Usar el boton `Cargar clientes`.

Esto hace lo siguiente:

- busca clientes con ventas en el periodo base
- consolida por cliente comercial
- crea una linea por cliente
- elimina del plan clientes que ya no tengan ventas en ese periodo

## 5. Calcular el plan

Usar el boton `Calcular plan`.

El sistema calculara todas las columnas del plan.

Si cambia el periodo, factores o limites, el plan vuelve a borrador y debe usar `Calcular plan`. Para nuevas facturas sin cambios de configuracion puede usar:

- `Recalcular metricas`

## 6. Revisar el resultado

En la pestana `Lineas` puede revisar cliente por cliente.

Campos principales:

- `Venta Base`: venta neta del periodo base
- `Participacion`: peso del cliente sobre la venta base total
- `Acumulado`: porcentaje acumulado para asignar segmento A, B o C
- `DPP`: dias promedio de pago
- `Segmento Final`: combinacion de segmento de venta y DPP
- `Meta`: meta total calculada para el periodo
- `Meta a la Fecha`: proporcion de la meta segun los meses calendario transcurridos
- `Meta Mensual`: meta del periodo dividida entre los meses calendario que toca el rango
- `Venta Actual`: venta acumulada del periodo objetivo hasta la fecha actual
- `Cumplimiento`: venta actual / meta a la fecha
- `Desviacion vs Meta`: cumplimiento menos 1

Interpretacion rapida:

- valor positivo en `Desviacion vs Meta`: va por encima de la meta
- valor negativo: va por debajo
- `Crecimiento Mensual`: promedio mensual actual menos meta mensual

## Como se calculan los datos

### Ventas

Las ventas se calculan con facturas publicadas y notas de credito:

- `move_type in ('out_invoice', 'out_refund')`
- `state = posted`
- se usa `amount_total_signed`

Las notas de credito restan ventas dentro del periodo.

### Venta Base

Es la venta neta del periodo base anual o personalizado.

### Venta Actual

Es la venta acumulada del periodo objetivo hasta la fecha actual o hasta el final del rango.

Si el periodo objetivo aun no inicia, la venta actual y la meta a la fecha seran `0`.

### DPP

El DPP reutiliza la logica del modulo de metricas del cliente.

Criterio usado:

- solo facturas de cliente publicadas y pagadas
- la fecha de la factura debe estar dentro del periodo base del plan
- se toma la fecha del cobro que termina de saldar la factura
- si hubo varios pagos, se usa la ultima fecha de conciliacion de cobro real

## Exportar a Excel

Usar el boton `Exportar Excel`.

El archivo incluye:

- las columnas principales del plan
- la meta segmentada
- venta acumulada
- cumplimiento
- parametros laterales de control

Esto permite comparar facilmente contra el modelo de segmentacion usado por el equipo comercial.

## Estados del plan

- `Borrador`: editable
- `Calculado`: ya tiene resultados
- `Cerrado`: no permite modificaciones

Si necesita reabrirlo:

- usar `Pasar a borrador`

## Recomendaciones de uso

- usar un solo plan por compania y por combinacion de periodos
- revisar primero los limites de segmentacion antes de calcular
- definir si la meta total vendra de presupuesto o de crecimiento esperado
- usar `Recalcular metricas` si hubo cambios contables o nuevas facturas
- cerrar el plan cuando ya fue aprobado

## Limitaciones actuales

- la columna `Presupuesto Objetivo` esta lista para uso manual, pero no tiene aun importacion masiva desde Excel
- si en la base no existen ventas del ano base, no se cargaran lineas
- el resultado depende de la calidad de los datos contables y de conciliacion

## Caso de uso recomendado

1. Crear plan 2026.
2. Definir `Ano Base = 2025`.
3. Definir `Ano Objetivo = 2026`.
4. Colocar `Meta Total Manual` o `Presupuesto Total`.
5. Revisar limites de segmentacion y DPP.
6. Cargar clientes.
7. Calcular plan.
8. Revisar lineas y ajustar si hace falta.
9. Exportar a Excel.
10. Cerrar plan cuando quede aprobado.

## Soporte funcional

Si un usuario no ve el menu, debe revisar:

- que tenga permisos del grupo del modulo
- que el modulo este instalado y actualizado
- que este dentro de la compania correcta
