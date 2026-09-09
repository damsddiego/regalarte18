# SNG Entrega de Regalías

Documento para entregar productos de obsequio (regalías) a clientes.

## Aviso por correo al crear

Al guardar una nueva regalía en **Borrador**, se encola un correo individual para
cada usuario activo con el grupo **Responsable regalías**, correo configurado y
acceso a la compañía de la regalía. Incluye solicitante, cliente, almacén, fecha,
productos, cantidades, notas y un enlace para revisar el documento.

El aviso no valida la entrega. Editar el borrador o volverlo a borrador no repite
el correo. Si no hay responsables con correo, la solicitud se guarda igualmente.
El envío usa el servidor saliente y la cola de correo de Odoo; requiere que ambos
estén operativos. No se envían avisos retroactivos por solicitudes existentes.

La plantilla **Regalías: nueva solicitud** se puede editar desde las plantillas
de correo de Odoo. Para activar esta función, actualizar el módulo a
`18.0.1.1.1` y cargar el nuevo código Python en el servicio.

El enlace usa el parámetro del sistema `web.base.url`, que debe contener la URL
de acceso a Odoo (incluido HTTPS), aunque la compañía tenga otro dominio para su
sitio web público. La actualización a `18.0.1.1.1` corrige también el enlace en
la plantilla existente.

## Qué hace al validar

1. Crea y valida una transferencia de salida (tipo de operación **Entrega de Regalías**)
   desde el almacén elegido hacia la ubicación de clientes → rebaja el inventario.
2. Crea y publica un asiento contable al **costo promedio** de cada producto:
   - Débito: cuenta de gasto de regalías (una línea por producto, con el cliente).
   - Crédito: cuenta contrapartida de inventario (una sola línea por el total).
   - Sin líneas de IVA.
3. Permite imprimir el **Comprobante de Entrega de Regalía** (PDF, sin costos —
   solo productos, cantidades y firmas).

## Configuración

Ajustes > Contabilidad > bloque **Regalías a clientes** (visible para Responsable regalías):

- **Cuenta de gasto** (obligatoria para validar)
- **Cuenta contrapartida** (obligatoria para validar)
- **Diario** (opcional; si está vacío se usa el primer diario misceláneo de la compañía)

## Seguridad

- **Usuario regalías**: crea y edita borradores, imprime.
- **Responsable regalías**: además valida (rebaja stock + asiento), configura cuentas
  y ve los costos.

## Reversar una regalía entregada

Los documentos entregados quedan bloqueados. Para reversar:

1. Contabilidad: reversar el asiento desde el propio asiento (botón Reversar).
2. Inventario: crear una devolución de la transferencia `REG-OUT/...` asociada.
