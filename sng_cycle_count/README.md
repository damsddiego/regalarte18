# Conteos cíclicos: control y aprobación (18.0.3.0.0)

## Manual de usuario

Procedimientos para Operadores, Jefatura y Gerencia, con índice y soluciones a
mensajes frecuentes: [PDF](docs/Manual_usuario_conteos_ciclicos_Regalarte.pdf),
[HTML para consulta](docs/Manual_usuario_conteos_ciclicos_Regalarte.html) y
[fuente editable](docs/manual_usuario.md). Para regenerarlos, ejecutar
`/opt/odoo18/odoo18-venv/bin/python docs/build_manual.py` desde este módulo.

## Operación

1. Jefatura crea una sesión por bodega, con sus productos y operador. Una sesión
   asignada ocupa cupo hasta aprobarla o cancelarla con motivo. Hay tres cupos
   por bodega; reasignar o quitar el operador no devuelve el cupo.
2. El operador captura cantidades y observaciones desde la sesión o desde
   **Ajustes de inventario**. Registrar cero cuenta como captura. No se aplican
   existencias durante esta etapa. El operador no agrega productos ni copia el
   teórico. Puede enviar líneas a revisión; cuando todas están contadas se envía
   la sesión a Jefatura. También dispone del botón **Enviar a Jefatura**.
3. Jefatura registra el motivo y da **Visto bueno**, o solicita un reconteo.
   El asistente de devolución permite elegir líneas; sin selección devuelve
   todas. Cambiar una cantidad invalida su visto bueno. El detalle de cada línea
   muestra capturas, autores, cantidades, motivos, revisiones y aplicación final.
4. Con todas las líneas revisadas, Jefatura pulsa **Enviar a Gerencia**.
   Gerencia confirma **Aprobar y Aplicar Ajustes**. Si cambiaron existencias
   desde la captura del teórico, se exige reconteo antes de aplicar.

Quien haya contado o recontado una línea no puede dar su visto bueno ni aprobar
la sesión que la contiene, aunque tenga permisos de Gerencia. Jefatura y
Gerencia pueden ser la misma persona si tiene ambos roles y no participó en el
conteo. Los registros de auditoría y motivos aprobados son inmutables.

Las líneas iniciales de la tercera sesión se crean junto con ella. Alcanzado el
límite, se puede completar todo lo existente, pero no agregar nuevos productos,
crear sesiones ni asignar borradores adicionales. La generación automática
separa sus productos por bodega y omite las bodegas bloqueadas, registrándolo
en el log. Conserva el número de productos seleccionado por configuración.

## Plazos y seguimiento

Se usa `America/Costa_Rica`, lunes a viernes, 07:30–17:00. El día de registro no
cuenta: se toman las dos fechas hábiles siguientes. Lunes a las 10:00 implica
advertencia el miércoles a las 07:30 y vencimiento el miércoles a las 17:00.
Después de las 17:00 se muestra rojo; hasta ese instante se muestra amarillo.
Fines de semana y feriados no cuentan. Registrar fuera de jornada usa la fecha
local del registro, con la misma regla de días siguientes.

Configurar en cada almacén el **Responsable de conteos cíclicos** y su
**Calendario de conteos y feriados**. Se excluyen los días no laborables globales
del calendario, sin tomar ausencias individuales. Si no se elige calendario,
se usa el de la compañía. Los feriados oficiales deben cargarse y mantenerse en
ese calendario: el módulo no descarga ni adivina fechas de feriados.

El reloj comienza en la primera diferencia significativa según el redondeo de
la unidad de medida. Reconteos, devoluciones y correcciones no lo reinician.
La diferencia histórica sigue pendiente de resolución incluso si un reconteo
queda en cero, hasta el cierre autorizado. No hay prórrogas ni aplicación
automática por vencimiento.

**Ajustes de inventario** abre con **Cíclicos con Diferencia Pendiente** y orden
por vencimiento ascendente. El filtro puede quitarse para registrar otros
conteos. **Conteos Vencidos** permite limitar la selección. Cantidad nativa y
línea cíclica se sincronizan; la columna **Diferencia cíclica** conserva la
comparación con el teórico del conteo, aunque luego haya movimientos.
Los colores se calculan al consultar la pantalla; actualizarla refleja el
cambio de hora. Cada cinco minutos se crea, sin duplicados, una actividad por
sesión vencida y responsable. Al resolver la sesión se cierra la actividad.

## Ajustes manuales

Se reutiliza `sng_inventory_adjustment_history` (18.0.2.1.0). Conserva su permiso
de Gerencia para solicitudes manuales; el grupo de Gerencia cíclica no concede
por sí solo permisos de aprobación manual. Los ajustes manuales no consumen
cupos cíclicos ni tienen este plazo de dos días.

El capturador se registra en servidor. Cambiar el responsable asignado, editar
el conteo desde otro usuario o enviar una solicitud desde otra cuenta no borra
sus participantes. Gerencia no puede aprobar su propio conteo. Las entradas de
aplicación automática se redirigen operativamente al flujo de cantidad contada
y aprobación de otro usuario. Una existencia ligada a una sesión abierta no
puede ajustarse por una solicitud manual independiente.

## Actualización y validación

- Ejecutar `scripts/preflight.sql` con `psql -d BASE -f RUTA` antes de actualizar.
  Revisar sesiones sin bodega, sesiones que abarcan varias bodegas, duplicados
  por existencia y coincidencias con solicitudes manuales.
- Resolver duplicados y solicitudes que colisionen. La migración detiene la
  actualización si encuentra esas ambigüedades o ubicaciones sin bodega.
  No cancela ni aplica inventario para sanearlo automáticamente.
- Revisar responsables, roles y calendario de feriados. Coordinar con Diego
  la ventana de actualización y cualquier reinicio. Configurar datos no
  autoriza a reiniciar el servicio.
- Actualizar `sng_inventory_adjustment_history,sng_cycle_count` en una copia
  de pruebas antes de producción. El nuevo módulo depende de `resource` y de
  `sng_inventory_adjustment_history`.
- La migración cuenta todas las sesiones antiguas abiertas, incluso sin
  operador. Una sesión antigua con varias bodegas ocupa cupo en cada una.
  Devuelve los pendientes de Gerencia a Jefatura. Conserva los participantes
  conocidos de la sesión, identificados como inferidos en la auditoría; si no
  se conoce ninguno, se exige una nueva captura antes de aprobar.
- Otorga una única gracia a diferencias existentes: 17:00 del segundo día
  hábil siguiente a la actualización. Guarda `sng_cycle_count.control_migrated_at`
  para no repetirla en actualizaciones posteriores. No borrar ese parámetro.
- Los conteos manuales antiguos sin autor de captura requieren volver a
  registrar la cantidad antes de aplicar directamente desde inventario.

Pruebas Odoo: `--test-enable --test-tags /sng_cycle_count,/sng_inventory_adjustment_history`.
Usar una base aislada, sin cron y con un puerto HTTP diferente al del servicio.
`scripts/check_concurrency.py` se ejecuta mediante `odoo-bin shell` y solo admite
bases con `_test_` en su nombre. Verifica dos solicitudes simultáneas con dos
cupos ocupados: una obtiene el tercero y la otra queda bloqueada; limpia sus
sesiones y deja su almacén de prueba archivado.
