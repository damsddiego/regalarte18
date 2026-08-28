# Changelog - sng_customer_statement v18.0.1.2.0

## Fecha: 2026-06-30

## Requerimiento

Que el reporte de Estado de Cuenta "tome en cuenta" los pagos en
**proceso de pago** sobre las facturas (estado `account.payment.state = 'in_process'`,
que en la factura se refleja como `payment_state = 'in_payment'` → "En proceso de pago").

## Contexto técnico (Odoo 18)

En Odoo 18 el modelo de pagos cambió: un `account.payment` puede estar en estado
`in_process` (dinero recibido en cuenta transitoria, aún **sin confirmar en banco**).
Cuando ese pago ya está conciliado con la factura, la factura queda con
`amount_residual = 0` y `payment_state = 'in_payment'`.

En `RegalarteProd` todas las facturas "En proceso de pago" ya tenían saldo 0 y
conciliación parcial → **el reporte ya las contaba como pagadas** (saldo correcto).
Lo que faltaba era **distinguirlas**: un pago en proceso se veía idéntico a uno
ya confirmado en banco, porque la consulta de conciliaciones ni siquiera traía
`account.payment.state`.

## Decisión

Mantener el saldo en 0 (la factura sale **pagada** al cliente) y agregar un
**marcado informativo** "En proceso de pago", sin alterar ningún total existente.

## Cambios

### `wizard/customer_statement_wizard.py`
- `_fetch_reconciliations_sql`: la consulta ahora trae `ap_ctr.state AS counterpart_pay_status`
  (estado real del `account.payment`) en ambos SELECT del UNION.
- `_compute_report_structure`: por factura se calcula `amount_in_process` = suma de
  pagos aplicados cuyo `account.payment.state = 'in_process'`. Se acumula a nivel de
  cliente (`total_in_process`) y a `grand_totals`. **No** se descuenta del aplicado
  ni se suma al saldo (es informativo).
- `_build_report_lines` (resumen) y `_create_detail_report_lines` (detalle):
  - Resumen: la línea del cliente lleva `amount_in_process`.
  - Detalle: la línea hija del pago en proceso se etiqueta
    "Pago en proceso de pago", lleva `amount_in_process` y `payment_state = 'in_process'`;
    la factura padre se marca con leyenda "En proceso de pago".
- XLSX: hoja de detalle etiqueta los pagos en proceso; hoja de resumen agrega
  la columna "En Proceso de Pago" (al final, informativa).

### `models/customer_statement.py`
- Nuevo campo `amount_in_process` en `customer.statement.report.line` (informativo).
- Nuevo total `total_in_process` en la cabecera `customer.statement.report`.

### Vistas (`views/customer_statement_views.xml`)
- Columna sumable `amount_in_process` en la lista de líneas.
- Medida "En Proceso" en la vista pivot.
- Campo en el formulario de línea y total en el formulario de cabecera.

### Reporte PDF (`report/customer_statement_template.xml`)
- Detalle: etiqueta "Pago en proceso de pago" y estado "En proceso de pago".
- Resumen: subtexto "en proceso: X" bajo Total Pagado y fila en el Resumen General.
- Notas actualizadas.

## Impacto en datos

No cambia ningún saldo ni total previo. Es 100% aditivo: agrega una dimensión
informativa "En Proceso de Pago". Las facturas en proceso siguen contando como
pagadas (saldo 0), como se solicitó.

## Aplicar

```bash
python odoo18/odoo-bin -c /etc/odoo18.conf -u sng_customer_statement -d RegalarteProd --stop-after-init
sudo systemctl restart odoo18
```
