# Historial y aprobación de ajustes de inventario

## Flujo operativo

1. En **Inventario → Operaciones → Ajustes → Solicitudes de ajuste**, crear una
   solicitud, elegir la **bodega** (ubicación interna) y agregar una línea por
   producto contado: conteo físico y motivo justificado por línea. Se conserva
   como **Borrador**, sin cambiar existencias.
2. Pulsar **Solicitar aprobación**. Cada línea conserva la cantidad anterior,
   el conteo, la discrepancia y una estimación del costo, y la solicitud pasa a
   **Por aprobar**. Se genera un solo correo en la cola de Odoo con la tabla de
   líneas y un enlace autenticado a la solicitud.
3. Gerencia abre la solicitud y pulsa **Aprobar y aplicar** (aplica todas las
   líneas pendientes en una sola transacción) o escribe la observación y pulsa
   **Rechazar** (rechaza todas las pendientes). La aprobación es siempre por
   solicitud completa; no hay aprobación por línea. Desde **Rechazar línea**
   puede excluir una línea y después aprobar el resto con el mismo botón.

### Ajuste por diferencia

El conteo guarda la **cantidad al contar** (lo que decía el sistema en ese
momento) y la **discrepancia** (conteo físico − cantidad al contar). Al aprobar
no se impone el conteo físico: cada línea queda en **existencia actual +
discrepancia**, con las existencias bloqueadas durante la aprobación. Así los
despachos o entradas ocurridos entre el conteo y la aprobación no se pierden
(ejemplo: sistema 76, contado 70, hoy 58 → queda 52).

**Recalcular existencias** (solicitud pendiente, solo aprobadores) refresca las
columnas *Existencia actual* y *Cantidad resultante*, marca en amarillo las
líneas cuyo stock cambió desde el conteo y deja el detalle en el chatter. No
modifica el conteo registrado ni reenvía correo.

Único bloqueo: si la cantidad resultante sería negativa (el faltante detectado
supera lo que queda hoy), la aprobación se detiene indicando la línea; se
rechaza esa línea y se aprueba el resto.

Todas las líneas de una solicitud pertenecen a la misma bodega. Si el producto
aún no tiene existencia en esa bodega, el sistema crea la existencia en cero al
guardar la línea, la cantidad anterior queda en 0 y el ajuste se aplica al
aprobar. Solo se admiten productos con rastreo de inventario; los productos con
lote o serie requieren indicar el lote en la línea.

También se puede registrar la cantidad contada y el **Motivo del ajuste** en
**Inventario físico**, y pulsar **Solicitar aprobación** para una o varias filas:
se crea una solicitud por ubicación con las filas seleccionadas como líneas.

La discrepancia se calcula como conteo físico menos cantidad anterior. El costo
del correo de solicitud es estimado; el costo definitivo queda en el historial
al aplicar, para almacenes incluidos en grupos, como en el módulo original.

### Modelos

- `sng.inventory.adjustment.batch`: cabecera (bodega, líneas, estado calculado a
  partir de las líneas, revisión de Gerencia). Es lo que muestra el menú.
- `sng.inventory.adjustment.request`: línea (existencia, producto, conteo,
  motivo, estado). `sng_cycle_count` y `sng_inventario_movil` siguen
  consultando este modelo por `quant_id` y `state`; `sng_cycle_count` hereda
  `create` y llama a `_sng_resolve_quant_vals` para bloquear la existencia aun
  cuando la línea llega con producto en vez de existencia.
- El historial (`sng.inventory.adjustment.history`) enlaza la línea y la cabecera.

## Permisos

- **Inventario / Usuario**: registra borradores, consulta sus solicitudes y las
  envía a Gerencia. No puede aplicar ajustes, incluso mediante asistentes,
  importación con aplicación automática o llamadas al servidor.
- **Gerencia: aprobar y aplicar ajustes de inventario**: consulta todas las
  solicitudes de sus compañías, ve costos, aprueba, rechaza y puede aplicar
  ajustes manuales. Es un permiso independiente; ser administrador de Inventario
  no lo concede automáticamente. No puede aprobar ni aplicar conteos en los que
  participó. Se conserva al capturador real aunque cambie el responsable asignado.
  La edición con aplicación automática requiere usar cantidad contada y aprobación
  independiente; no permite capturar y aplicar en una sola operación.

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
- Una sola línea pendiente por existencia y un solo producto por solicitud.
- Las líneas solo se agregan o quitan en borrador; la bodega no cambia con líneas.
- Conteo y motivo inmutables después de enviarlos a aprobación.
- Bloqueo de edición del conteo nativo mientras hay una solicitud pendiente.
- Bloqueo de registros durante aprobación; el ajuste se aplica por diferencia
  sobre la existencia actual y solo se detiene si el resultado sería negativo.
- Prevención de aplicación repetida y registro del solicitante y aprobador.
- Los quants referenciados se conservan durante la limpieza automática para
  no perder la referencia de la solicitud.

## Activación

Actualizar `sng_inventory_adjustment_history` a **18.0.3.1.0** y `sng_cycle_count`
a **18.0.3.0.1**, y cargar el nuevo código en los procesos de Odoo. La migración
`migrations/18.0.3.0.0/post-migrate.py` crea una cabecera por cada solicitud
existente conservando bodega, estado y revisión. Coordinar con Diego cualquier
reinicio del servicio. Asignar el permiso de Gerencia a los usuarios aprobadores;
el módulo no concede ese permiso a ningún usuario de producción automáticamente.
