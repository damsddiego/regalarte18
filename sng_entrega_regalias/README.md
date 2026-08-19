# SNG Entrega de Regalías

Documento para entregar productos de obsequio (regalías) a clientes.

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
