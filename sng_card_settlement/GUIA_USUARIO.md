# Guía de Usuario

## Objetivo

Este módulo se usa cuando el cliente paga con tarjeta y el banco no deposita el monto completo de cada pago, sino un neto después de comisiones, impuestos, retenciones u otros cargos.

Con este proceso:

- la factura del cliente queda pagada de inmediato,
- el pago queda pendiente de liquidación bancaria,
- al día siguiente se genera una sola liquidación por banco y fecha,
- el sistema crea un único asiento contable por el depósito neto y las deducciones.

## Quién usa esta opción

La opción está pensada para usuarios de contabilidad con permisos para crear y publicar movimientos contables.

## Configuración inicial

Antes de usar la liquidación diaria, valide esta configuración una sola vez.

### 1. Configurar liquidación de tarjetas

Ruta sugerida:

- `Contabilidad > Configuración > Ajustes > Liquidación de tarjetas`

Complete estos campos:

- `Diarios fuente`: diarios donde se registran los cobros con tarjeta.
- `Bancos destino`: bancos donde se registra el depósito neto.
- `Cuentas puente`: cuentas transitorias usadas por los pagos de tarjeta.
- `Cuentas de deducción`: cuentas permitidas para comisiones, impuestos y retenciones.

Si esta configuración está incompleta, el sistema no permitirá generar la liquidación.

### 2. Configurar el diario bancario

Ruta sugerida:

- `Contabilidad > Configuración > Diarios`

En el diario del banco:

- confirme que el diario sea de tipo `Banco`,
- confirme que tenga cuenta bancaria por defecto,
- revise que el método de pago de entrada para tarjeta esté disponible.

### 3. Configurar el método de pago de tarjeta

Dentro del mismo diario bancario, en la sección de cobros de entrada:

- marque la opción `Liquidación de tarjeta`,
- configure la `Outstanding Receipts Account` o cuenta puente.

Esa cuenta puente es donde quedará registrado temporalmente el pago, mientras el banco hace el depósito real.

## Flujo operativo

## Paso 1. Registrar el pago del cliente con tarjeta

Cuando registre un pago de cliente:

- use el diario puente definido para cobros con tarjeta,
- use el método de pago configurado para tarjeta,
- confirme y publique el pago como lo hace normalmente.

Resultado esperado:

- la factura queda en estado `Pagada`,
- el pago queda pendiente de liquidación,
- todavía no se reconoce el depósito bancario neto.

Nota:

- el diario usado al registrar el pago puede ser distinto del banco real donde luego entrará el depósito,
- el banco real se define en la liquidación diaria.

## Paso 2. Generar la liquidación diaria

Ruta:

- `Contabilidad > Contabilidad > Liquidaciones de tarjeta > Generar liquidación diaria`

Se abrirá una ventana con estos campos principales:

- `Compañía`
- `Banco`
- `Fecha de transacción`
- `Fecha de liquidación`

Comportamiento del sistema:

- al elegir el banco y la fecha de transacción, el sistema propone automáticamente los pagos elegibles,
- por defecto, la fecha de transacción se calcula como un día antes de la fecha de liquidación,
- si algún pago no debe incluirse, puede quitarlo manualmente de la lista.

## Paso 3. Revisar los pagos propuestos

En la sección `Pagos` verá los pagos que cumplen estas condiciones:

- son pagos de cliente,
- son cobros de entrada,
- están publicados,
- pertenecen a un diario fuente configurado para liquidación de tarjeta,
- usan un método marcado como `Liquidación de tarjeta`,
- usan una cuenta puente configurada para liquidación de tarjeta,
- corresponden a la fecha de transacción indicada,
- coinciden con la moneda del banco elegido para la liquidación,
- todavía no han sido liquidados.

Revise especialmente:

- cantidad de pagos,
- clientes,
- montos,
- fecha.

## Paso 4. Registrar las deducciones del banco

En la sección `Deducciones` agregue una línea por cada rebaja que aplique el banco.

Ejemplos:

- comisión bancaria,
- IVA sobre comisión,
- renta retenida,
- otros cargos.

Cada línea debe tener:

- `Concepto`
- `Cuenta contable`
- `Monto`

Reglas:

- solo se pueden elegir cuentas configuradas como deducción de tarjeta,
- el monto debe ser mayor que cero,
- cada línea debe tener cuenta contable,
- el neto no puede quedar negativo.

## Paso 5. Generar la liquidación

Presione `Generar`.

El sistema hará esto automáticamente:

- creará la liquidación,
- generará un solo asiento contable,
- registrará el depósito neto en la cuenta del banco,
- registrará las deducciones en sus cuentas contables,
- cancelará la cuenta puente contra los pagos incluidos,
- marcará esos pagos como ya liquidados.

## Qué asiento contable genera el sistema

La lógica del asiento es:

- débito a la cuenta bancaria del diario por el neto depositado,
- débitos a las cuentas de deducción,
- créditos a la cuenta puente de tarjeta por el monto bruto de los pagos.

Si en los pagos seleccionados existen varias cuentas puente, el sistema genera una línea de crédito por cada cuenta puente.

## Cómo consultar una liquidación ya generada

Ruta:

- `Contabilidad > Contabilidad > Liquidaciones de tarjeta`

Desde esa pantalla puede revisar:

- referencia,
- fecha de transacción,
- fecha de liquidación,
- banco,
- bruto,
- deducciones,
- neto,
- estado.

Al abrir una liquidación también puede ver:

- pagos incluidos,
- deducciones registradas,
- asiento contable generado.

## Cómo saber si un pago ya fue liquidado

Abra el pago del cliente y revise la sección `Liquidación de tarjeta`.

Ahí podrá ver:

- si el pago requiere liquidación,
- cuál liquidación quedó asociada.

## Validaciones y mensajes comunes

### No hay pagos seleccionados para liquidar

Causa probable:

- no existen pagos de tarjeta pendientes para esa fecha y moneda,
- el pago quedó con otra fecha,
- el pago está en otra moneda,
- el pago ya fue liquidado antes.

### El depósito neto no puede ser negativo

Causa probable:

- las deducciones superan el monto bruto de los pagos seleccionados.

### Solo se permiten pagos de cliente publicados, pendientes de liquidar, de la misma fecha y moneda

Causa probable:

- se intentó incluir un pago que no corresponde a la fecha,
- se intentó incluir un pago con otra moneda,
- el pago no está publicado,
- el pago no fue hecho con método de tarjeta,
- el pago ya pertenece a otra liquidación.

### El diario bancario debe tener una cuenta bancaria por defecto

Causa probable:

- el diario del banco no está completamente configurado.

## Recomendaciones de uso

- Genere una liquidación por banco y por fecha de transacción.
- Revise el comprobante del banco antes de cargar las deducciones.
- No mezcle pagos de fechas distintas en una misma liquidación.
- Si un pago no aparece, revise primero la fecha, la moneda y el método de pago usado.

## Correcciones

En esta versión, una liquidación publicada no se edita ni se elimina.

Si se registró con error:

- revise el asiento contable generado,
- haga la reversión contable según el procedimiento interno,
- luego vuelva a generar la liquidación correcta.

## Resumen rápido

1. Registrar el pago del cliente con método de tarjeta.
2. Verificar que la factura quede pagada.
3. Ir a `Liquidaciones de tarjeta`.
4. Abrir `Generar liquidación diaria`.
5. Elegir banco y fechas.
6. Revisar pagos propuestos.
7. Agregar deducciones.
8. Generar la liquidación.
