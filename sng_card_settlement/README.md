# SNG Card Settlement

## Documentación

- Guía técnica y funcional: `README.md`
- Guía para usuario final: `GUIA_USUARIO.md`

## Resumen

Este módulo permite manejar pagos de clientes con tarjeta donde:

- la factura queda pagada de inmediato,
- el pago se registra contra una cuenta puente del método de pago,
- al día siguiente se genera una sola liquidación bancaria,
- la liquidación crea un único asiento con depósito neto y deducciones.

## Objetivo contable

Cuando un cliente paga con tarjeta, el banco no deposita el total bruto de cada transacción. Normalmente rebaja:

- comisión bancaria,
- IVA sobre comisión,
- retenciones,
- otros cargos.

Este módulo separa ambos momentos:

1. Pago del cliente: cancela la factura.
2. Liquidación del banco: registra el depósito neto y las deducciones en un solo asiento.

## Configuración

### 1. Configuración contable de liquidación TC

En **Contabilidad > Configuración > Ajustes > Liquidación de tarjetas** configurar:

- diarios fuente donde se registran los cobros con tarjeta,
- bancos destino permitidos para el depósito neto,
- cuentas puente que se acreditan al liquidar,
- cuentas permitidas para deducciones.

Para Regalarte, la cuenta puente esperada es **Transitoria cobro TC** y las cuentas de deducción deben limitarse a las usadas para renta anticipada, impuesto de ventas por pagar y comisión bancaria datafono.

### 2. Método de pago

En el diario bancario, pestaña **Incoming Payments**:

- seleccionar el método de pago que represente tarjeta,
- configurar **Outstanding Receipts Account** con la cuenta puente,
- activar **Liquidación de tarjeta**.

### 3. Diario bancario

El diario debe tener configurada su cuenta bancaria por defecto, ya que esa cuenta recibe el débito del depósito neto.

## Flujo operativo

### Registro del pago

Al registrar un pago de cliente con un método marcado como liquidación de tarjeta:

- el pago queda asociado a la cuenta puente del método,
- la factura pasa a estado `paid`,
- el pago queda pendiente de liquidación bancaria.

El diario usado al registrar el pago puede ser un diario puente distinto del banco real. El banco del depósito se define al momento de liquidar.

### Generación de la liquidación

Desde **Contabilidad > Accounting > Liquidaciones de tarjeta**:

1. Abrir **Generar liquidación diaria**.
2. Seleccionar:
   - banco,
   - fecha de transacción,
   - fecha de liquidación.
3. Revisar los pagos propuestos.
4. Agregar deducciones:
   - concepto,
   - cuenta contable,
   - monto.
5. Confirmar la liquidación.

## Asiento generado

La liquidación crea un solo asiento contable con esta lógica:

- débito a la cuenta bancaria del diario por el neto depositado,
- débito a cada cuenta de deducción,
- crédito a una o varias cuentas puente según los pagos incluidos.

Luego el módulo reconcilia automáticamente las líneas de cuenta puente contra los pagos liquidados.

## Modelos principales

- `account.payment.method.line`
  - `is_card_settlement`

- `account.payment`
  - `card_settlement_id`
  - `is_card_settlement_required`

- `sng.card.settlement`
- `sng.card.settlement.deduction`
- `sng.card.settlement.wizard`

## Validaciones

El módulo valida que:

- solo entren pagos de cliente,
- el pago esté publicado,
- el método de pago esté marcado para liquidación,
- el diario fuente esté configurado para liquidación de tarjeta,
- la cuenta puente del pago esté configurada para liquidación de tarjeta,
- el pago no haya sido liquidado antes,
- el pago pertenezca a la fecha y moneda seleccionadas,
- el banco destino esté configurado para liquidación de tarjeta,
- las deducciones usen solo cuentas configuradas para liquidación de tarjeta,
- las deducciones tengan cuenta y monto positivo,
- el neto no sea negativo.

## Menús y vistas

El módulo agrega:

- configuración en métodos de pago del diario,
- referencia de liquidación en pagos,
- menú de **Liquidaciones de tarjeta**,
- wizard para generar la liquidación diaria.

## Pruebas realizadas

Verificado en `RegalarteTest`:

- instalación del módulo,
- carga de vistas,
- actualización del módulo,
- pruebas automáticas del flujo base.

## Notas

- El módulo no cubre POS en esta versión.
- La liquidación se registra como asiento directo, no como extracto bancario.
- El banco real del depósito se define en la liquidación; el pago puede haberse registrado previamente en un diario puente.
- No incluye reversión funcional propia; si una liquidación publicada debe corregirse, la corrección se hace con reversión contable estándar.
