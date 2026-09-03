# SNG Envío de Mercadería

Módulo Odoo 18 para conservar una auditoría histórica de cada envío antes de
imprimir el documento de mercadería.

## Información auditada

- Orden de venta y traslado.
- Caja actual y total de cajas.
- Método habitual del contacto de entrega al momento de crear el registro.
- Método utilizado realmente y si fue asignado o cambiado.
- Persona que alistó la orden.
- Actualización opcional del método habitual del cliente.
- Confirmaciones e impresiones registradas.

Los valores visibles en el reporte se copian al documento para evitar que una
modificación posterior del cliente altere el histórico.

## Integración móvil

El modelo `sng.envio.mercaderia` expone los siguientes métodos públicos por RPC:

- `mobile_get_defaults(source_model, source_id)`
- `mobile_create_or_get(...)`
- `mobile_confirm(audit_id)`
- `mobile_set_customer_default(audit_id, actor_partner_id)`
- `mobile_register_print(audit_id, actor_partner_id)`
- `mobile_get_pdf(audit_id)`

`mobile_create_or_get` exige una clave única generada por la aplicación para que
un reintento de red no duplique el documento.

## Seguridad

Asignar al usuario técnico de la aplicación el grupo **Usuario auditoría de
envíos**. Los registros confirmados no permiten modificar los datos auditados.
