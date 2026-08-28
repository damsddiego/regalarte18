# Changelog - sng_customer_statement v18.0.1.3.0

## Cambios

- Se agregó el logo de la compañía al encabezado del PDF.
- Se redujo el margen superior del PDF de 52 mm a 7 mm mediante un formato de
  papel propio, aprovechando el espacio que antes quedaba en blanco.
- Se agregaron al PDF los siguientes datos de `res.partner`:
  - Nombre comercial (`commercial_name`).
  - Código de cliente (`unique_id`).
  - Ruta (`sales_route_id`).
  - Primer correo no vacío del campo `email`, cuando contiene valores separados por `;`.
  - Vendedor asignado (`assigned_salesperson_id`).
  - Plazo de pago (`property_payment_term_id`).
- Los datos se cargan en bloque para todos los clientes y se muestran tanto en
  el modo resumen como en el modo detalle.
