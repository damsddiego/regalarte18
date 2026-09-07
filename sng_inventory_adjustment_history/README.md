# Historial y aprobación de ajustes de inventario

## Flujo operativo

1. En **Inventario → Operaciones → Ajustes → Solicitudes de ajuste**, crear una
   solicitud, seleccionar la existencia, registrar el conteo físico y justificar
   el motivo. Se conserva como **Borrador**, sin cambiar existencias.
2. Pulsar **Solicitar aprobación**. El sistema conserva la cantidad anterior,
   el conteo, la discrepancia y una estimación del costo, y pasa a **Por aprobar**.
   Genera un correo en la cola de Odoo con el detalle y un enlace autenticado.
3. Gerencia abre la solicitud y pulsa **Aprobar y aplicar**, o escribe el motivo
   de rechazo y pulsa **Rechazar**. La aprobación aplica el movimiento y la
   valoración; el rechazo no cambia existencias.

También se puede registrar la cantidad contada y el **Motivo del ajuste** en
**Inventario físico**, y pulsar **Solicitar aprobación** para una o varias filas.
Para productos sin existencias registradas, primero se puede crear la fila de
conteo en Inventario físico. Cada existencia genera su propia solicitud.

La discrepancia se calcula como conteo físico menos cantidad anterior. El costo
del correo de solicitud es estimado; el costo definitivo queda en el historial
al aplicar, para almacenes incluidos en grupos, como en el módulo original.

## Permisos

- **Inventario / Usuario**: registra borradores, consulta sus solicitudes y las
  envía a Gerencia. No puede aplicar ajustes, incluso mediante asistentes,
  importación con aplicación automática o llamadas al servidor.
- **Gerencia: aprobar y aplicar ajustes de inventario**: consulta todas las
  solicitudes de sus compañías, ve costos, aprueba, rechaza y puede aplicar
  ajustes manuales. Es un permiso independiente; ser administrador de Inventario
  no lo concede automáticamente. Puede aprobar solicitudes propias, según el
  criterio de separación únicamente por permisos.

El control de aplicación manual cubre todos los almacenes, aunque no tengan
grupo. Se mantienen las operaciones internas con `sudo()`: por ejemplo,
`sng_cycle_count` valida primero su propio permiso de Gerencia y después aplica
el inventario por esa vía. No se modifica el flujo de conteos cíclicos.

## Correos

En el grupo de almacenes se configuran **Correos de Gerencia para aprobación**.
Si está vacío, se usan los **Correos de alerta de ajustes** existentes. Si no
hay destinatarios en los grupos, se usan los correos de los usuarios activos con
permiso de aprobación y acceso a la compañía. Si tampoco existen, se informa
el error y la solicitud permanece en borrador.

Se usa el **Correo remitente de alertas** configurado, con respaldo al correo
de la compañía y luego al del usuario. Los correos de aprobación se conservan
para consulta técnica y son enviados por el gestor de la cola de Odoo. El enlace
no aplica el ajuste directamente: requiere autenticación y permiso de Gerencia.

## Controles de aprobación

- Motivo obligatorio y conteo físico no negativo.
- Una sola solicitud pendiente por existencia.
- Conteo y motivo inmutables después de enviarlos a aprobación.
- Bloqueo de edición del conteo nativo mientras hay una solicitud pendiente.
- Bloqueo de registros durante aprobación y comprobación de las existencias:
  si difieren de la cantidad anterior, se debe rechazar y registrar otro conteo.
- Prevención de aplicación repetida y registro del solicitante y aprobador.
- Los quants referenciados se conservan durante la limpieza automática para
  no perder la referencia de la solicitud.

## Activación

Actualizar `sng_inventory_adjustment_history` a **18.0.2.0.0** y cargar el nuevo
código en los procesos de Odoo. Coordinar con Diego cualquier reinicio del
servicio. Asignar el permiso de Gerencia a los usuarios aprobadores; el módulo
no concede ese permiso a ningún usuario de producción automáticamente.
