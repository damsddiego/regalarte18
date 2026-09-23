# Manual de conteos cíclicos
## Cómo contamos, revisamos y aprobamos ajustes en Odoo

**Odoo 18 · Versión 1.0 · 16 de septiembre de 2026**

Les comparto el manual de conteos cíclicos para operadores, Jefatura y Gerencia: cómo registrar lo contado, qué hacer con las diferencias, cuándo pedir reconteo y cómo se aplican los ajustes. El índice tiene enlaces para brincar directo a su parte, y con el buscador del PDF encuentran cualquier botón o mensaje.

> Ojo: contar o revisar no mueve el inventario. El ajuste solo se aplica cuando Gerencia aprueba y aplica la sesión.

### Cómo camina un conteo

**Captura → Revisión de Jefatura → Confirmación de Gerencia → Finalizado**

Si Jefatura pide reconteo, la sesión se devuelve a captura y el vencimiento sigue siendo el original.

### Consulta rápida

| Sección | Para qué le sirve | Página |
| --- | --- | --- |
| 1. Roles y estados | Saber quién hace qué | 2 |
| 2. Capturar una sesión | El trabajo del operador, incluido el conteo en cero | 3 |
| 3. Inventario físico | Capturar y dar seguimiento desde la lista de ajustes | 4 |
| 4. Revisar como Jefatura | Justificar, dar visto bueno y mandar a Gerencia | 5 |
| 5. Reconteos | Devolver líneas y corregir un conteo | 6 |
| 6. Cierre de Gerencia | Aplicar o cancelar con motivo | 7 |
| 7. Límite y preparación | Cómo funcionan los tres cupos por bodega | 8 |
| 8. Plazos y alertas | Qué significan el amarillo, el rojo y los feriados | 9 |
| 9. Ajustes manuales | Pedir y aprobar ajustes fuera de los cíclicos | 10 |
| 10. Configuración e historial | Responsables, calendario y auditoría | 11 |
| 11. Solución de problemas | Qué hacer cuando algo no los deja avanzar | 12 |
| 12. Ejemplo y rutina diaria | Un caso de principio a fin | 13 |

**Responsable de Jefatura en la bodega Regalarte:** admin2@regalartecr.com.

Las 39 sesiones que venían de antes quedaron canceladas el 16/09/2026, sin aplicar sus diferencias y con el historial guardado. Los conteos nuevos se consultan directo en Odoo.

<!-- pagebreak -->

# 1. Roles, accesos y estados

Entren siempre con su propio usuario y revisen que esté seleccionada la compañía correcta. Las horas de este manual están en hora de Costa Rica, así que en sus preferencias dejen la zona **America/Costa_Rica**. Si no les aparece alguna opción, me avisan y revisamos los permisos de ese usuario.

| Perfil | Qué puede hacer | Qué no puede hacer |
| --- | --- | --- |
| Operador | Capturar cantidades, escribir observaciones y enviar a revisión | Agregar productos, copiar teóricos, cancelar o aplicar ajustes |
| Jefatura / Supervisor | Preparar sesiones, asignar, revisar, justificar y pedir reconteos | Dar visto bueno a líneas que contó; el cierre siempre ocupa a Gerencia |
| Gerencia | Confirmar y aplicar sesiones; cancelar con motivo | Aprobar sesiones donde contó o recontó alguna línea |

**Regla de independencia:** en cuanto alguien registra una cantidad, queda como participante de ese conteo. Aunque después le quiten la asignación o le cambien el rol, eso no se borra. Jefatura y Gerencia pueden ser la misma persona si tiene los dos permisos y no capturó cantidades en las líneas que está revisando o aprobando. Cada línea ocupa un revisor independiente, y para aplicar la sesión completa Gerencia tiene que ser independiente de todas las líneas.

### Por dónde entrar

Los cíclicos están en **Inventario → Operaciones → Conteos Cíclicos**.

| Opción | Qué van a encontrar |
| --- | --- |
| Mis Conteos de Hoy | Las sesiones de hoy asignadas a usted, en borrador o en progreso |
| Todos los Conteos | Todo lo que puede consultar, incluidos días anteriores e historial |
| Revisión de Jefatura | Sesiones que ya se enviaron a revisión técnica |
| Pendientes de Gerencia | Sesiones listas para la confirmación final |
| Configuraciones | Reglas de selección y asignación de conteos |

### Estados de la sesión

**Borrador:** preparada pero sin iniciar. Si ya tiene operador asignado, ya está ocupando cupo. **En Progreso:** se están capturando cantidades o se está haciendo un reconteo. **Revisión de Jefatura:** esperando la decisión técnica. **Pendiente de Gerencia:** todas las líneas tienen visto bueno. **Finalizado:** Gerencia confirmó y se aplicaron las diferencias autorizadas. **Cancelado:** cierre administrativo con motivo, sin aplicar las diferencias de esa sesión.

Además, cada línea tiene su propio estado de revisión: **Captura**, **Requiere revisión**, **Requiere reconteo** o **Visto bueno de Jefatura**. Que una línea tenga visto bueno no quiere decir que la sesión esté cerrada.

<!-- pagebreak -->

# 2. Operador: capturar una sesión

**Ruta:** Inventario → Operaciones → Conteos Cíclicos → Mis Conteos de Hoy.

1. Abra la sesión que le asignaron. Si es de un día anterior o es un reconteo viejo, entre por **Todos los Conteos** y búsquela por la referencia.
2. Revise **Bodega física**, fecha, operador y productos. Fíjese también en la ubicación y, cuando aplique, el lote o la serie.
3. Si está en **Borrador**, dele **Iniciar**.
4. En **Líneas de Conteo**, cuente físicamente cada producto y anote el resultado en **Cantidad Contada**, en la unidad de medida que corresponde.
5. Use **Observaciones** para todo lo que ayude a entender lo que encontró. Por ejemplo, un empaque abierto, producto en otra posición o el lote que tenía.
6. Guarde y verifique que la línea diga **Contado**. Haga lo mismo con todas.
7. Al final dele **Enviar a Jefatura** y confirme. La sesión tiene que quedar en **Revisión de Jefatura**.

### Si no hay unidades, se registra cero

**Cero también es un conteo.** Escriba 0 y guarde. Si el valor ya estaba en 0 y la línea sigue **Pendiente**, dele **Marcar Contado** para que quede registrado que sí se contó. Que una línea muestre 0 no significa que ya esté contada.

### Cómo leer la diferencia

| Cantidad teórica | Cantidad contada | Diferencia | Qué significa |
| --- | --- | --- | --- |
| 20 | 18 | -2 | Faltan 2 unidades contra el teórico |
| 20 | 23 | +3 | Sobran 3 unidades contra el teórico |
| 20 | 20 | 0 | Todo cuadra |

La cantidad teórica es la referencia del conteo, y la diferencia ya toma en cuenta el redondeo de la unidad de medida. El operador anota lo que encontró de verdad. Nunca cambie el número para que cuadre con el teórico.

### Antes de irse

- Todas las líneas quedaron contadas, también las que dieron cero.
- Las observaciones le explican a Jefatura lo que tiene que revisar.
- La sesión está en **Revisión de Jefatura**. Guardar cantidades no la envía, hay que darle al botón.

> Ojo: una vez enviada ya no se pueden editar cantidades. Si se dio cuenta de un error, avísele a Jefatura con la referencia, el producto y la corrección. Jefatura le devuelve la línea para reconteo.

<!-- pagebreak -->

# 3. Capturar y dar seguimiento desde Inventario físico

**Ruta:** Inventario → Operaciones → Ajustes → **Inventario físico**. Es la misma pantalla de Ajustes de inventario que menciona el procedimiento.

Cuando la abren, ya viene puesto el filtro **Cíclicos con Diferencia Pendiente** y las diferencias salen ordenadas por vencimiento, de la más próxima a la más lejana. El filtro **Conteos Vencidos** también está, pero no viene activado.

> Si no ven un conteo nuevo, quiten el filtro «Cíclicos con Diferencia Pendiente» con la X de la etiqueta. Una línea que todavía no tiene diferencia registrada no sale en ese filtro. Que la pantalla esté vacía no quiere decir que no haya nada por contar.

### Capturar desde esta pantalla

1. Quite el filtro inicial si necesita ver líneas que todavía no tienen diferencia.
2. Busque el producto y revise ubicación, lote y **Sesión cíclica**. Tenga cuidado de no trabajar sobre otra existencia del mismo producto.
3. Escriba la **Cantidad contada** y, cuando haga falta, el motivo en **Motivo del ajuste**. Guarde la fila.
4. Con **Revisar cíclico** abre el detalle de la línea y confirma lo que quedó registrado.
5. Seleccione las líneas cíclicas contadas y dele **Enviar cíclicos a revisión**. También puede abrir una línea con **Revisar cíclico** y darle **Enviar a revisión**.
6. Cuando todas las líneas de la sesión están contadas, ese envío pasa la sesión a **Revisión de Jefatura**. Si le faltan líneas, termínelas y vuelva a enviar.

La sesión y esta lista trabajan sobre **el mismo conteo**, así que no hay que digitar las cantidades dos veces. Si un cero no quedó registrado, abra la sesión y use **Marcar Contado**.

### Columnas para dar seguimiento

| Columna | Para qué sirve |
| --- | --- |
| Sesión cíclica | Dice a qué documento pertenece esa existencia |
| Diferencia cíclica | Compara lo capturado contra el teórico de la sesión |
| Revisión cíclica | Muestra si ocupa revisión, reconteo o si ya tiene visto bueno |
| Vence el | Fecha y hora límite para resolver la diferencia |

Si alguna columna no se ve, actívela en el selector de columnas de la lista. La **Diferencia cíclica** puede no coincidir con la diferencia normal de Odoo si hubo movimientos después.

Para ver lo urgente, active **Conteos Vencidos** y refresque la pantalla. Si una diferencia existió y después quedó en cero, puede seguir apareciendo en pendientes hasta que se cierre la sesión. Las líneas cíclicas siguen su propio flujo de revisión. El botón **Solicitar aprobación** es solo para ajustes manuales aparte.

<!-- pagebreak -->

# 4. Jefatura: revisar y dar visto bueno

**Ruta:** Inventario → Operaciones → Conteos Cíclicos → **Revisión de Jefatura**.

1. Abra la sesión y revise cantidades, diferencias, observaciones y vencimientos.
2. Si necesita ver quién participó, capturas anteriores o decisiones ya tomadas, use **Detalle y auditoría** en la línea.
3. Decida si el conteo está bien sustentado o si hay que recontar. El sistema no tiene una tolerancia que decida por usted, esa decisión es suya.
4. Si da el visto bueno, llene **Justificación de Jefatura**, guarde y dele **Visto bueno**.
5. Verifique que la línea quede en **Visto bueno de Jefatura**. Esto va en todas las líneas, también las que no tienen diferencia.
6. Con todas contadas y aprobadas técnicamente, dele **Enviar a Gerencia**.
7. Confirme que la sesión quedó en **Pendiente de Gerencia**.

### Qué poner en la justificación

La idea es que cualquier otra persona lea la justificación y entienda por qué se aceptó el resultado. Anote qué verificó y a qué conclusión llegó. Si hay documentos de respaldo, ponga la referencia.

**Un ejemplo, solo si de verdad fue lo que se verificó:** «Se revisaron ubicación y lote con el operador y se contrastó el documento interno indicado en las observaciones. Se acepta el conteo de 18 unidades; no se requiere reconteo por los antecedentes verificados».

La justificación es obligatoria en cada visto bueno, aunque ya haya habido un reconteo. No escriba nada que no haya comprobado.

### Si hay que recontar

Escriba el motivo en **Justificación de Jefatura** de la línea y dele **Recontar**. En el detalle de la línea el botón se llama **Solicitar reconteo**. Para devolver varias líneas de un solo golpe, use **Devolver para Reconteo** en la sesión (lo explico en la página 6).

### Si Jefatura contó

Quien contó o recontó una línea no la puede revisar. Tiene que hacerlo otra persona autorizada que no haya registrado cantidades en esa línea. Ojo que **Copiar Teórico** o agregar un producto con cantidad también cuentan como participación, no sirven para brincarse la regla.

> El visto bueno técnico todavía no mueve existencias, no libera el cupo y no detiene el vencimiento. Para cerrar, siempre falta la confirmación de Gerencia.

<!-- pagebreak -->

# 5. Pedir y atender un reconteo

El reconteo sirve para volver a verificar lo físico y dejar una captura nueva. Las capturas anteriores no se pierden, quedan en la auditoría.

### Jefatura o Gerencia: devolver líneas

1. Abra la sesión en **Revisión de Jefatura** o **Pendiente de Gerencia**.
2. Dele **Devolver para Reconteo**.
3. En **Líneas a recontar**, escoja solo las líneas que hay que repetir.
4. En **Motivo de devolución** sea concreto: qué producto, ubicación, lote o situación tiene que revisar el operador.
5. Dele **Devolver**. La sesión regresa a **En Progreso** y las líneas escogidas quedan pendientes de captura, con revisión **Requiere reconteo**.

> Ojo: si deja «Líneas a recontar» vacío, se devuelven todas las líneas. Cuando el reconteo es parcial, escoja las que ocupa.

También se puede devolver una sola línea con **Recontar** o **Solicitar reconteo**, poniendo el motivo. Si esa línea ya tiene visto bueno y la justificación está bloqueada, use el asistente **Devolver para Reconteo** para dejar el motivo nuevo. Quien pide la revisión tiene que ser independiente de la captura de esa línea.

### Operador: hacer el reconteo

1. Abra la sesión. Si no es de hoy, búsquela en **Todos los Conteos**.
2. Lea el motivo de devolución y ubique las líneas que piden reconteo.
3. Vuelva a contar físicamente. Anote la nueva **Cantidad Contada**, aunque dé lo mismo que antes, y ponga observaciones del reconteo.
4. Verifique que las líneas digan **Contado**. Si la cantidad no cambió y la línea sigue pendiente, use **Marcar Contado**. Aplica igual cuando el resultado es cero.
5. Guarde y dele **Enviar a Jefatura**. Jefatura tiene que volver a justificar y revisar esas líneas antes de mandar otra vez a Gerencia.

### Qué se mantiene y qué cambia

| Se mantiene | Cambia |
| --- | --- |
| La primera diferencia y el vencimiento original | El teórico se refresca con la existencia actual al pedir el reconteo |
| Las capturas anteriores y quién las hizo | Queda la cantidad nueva y el usuario que la capturó |
| El cupo de la sesión | La línea devuelta ocupa un visto bueno nuevo |

Si alguien cambia una cantidad en una etapa que permite captura, el visto bueno anterior se cae. Y un reconteo que da diferencia cero tampoco cierra la sesión solo.

Si a Gerencia le sale el mensaje de que las existencias cambiaron, tiene que devolver esas líneas antes de aprobar. No hagan una solicitud manual aparte para resolverlo.

<!-- pagebreak -->

# 6. Gerencia: aplicar o cancelar

**Ruta:** Inventario → Operaciones → Conteos Cíclicos → **Pendientes de Gerencia**.

### Aprobar y aplicar ajustes

1. Abra la sesión y revise productos, cantidades, diferencias y las justificaciones de Jefatura.
2. Si necesita más sustento, vea el detalle y los reportes.
3. Revise que usted no haya capturado ninguna línea. Si participó, la sesión la tiene que aprobar otra persona con permiso de Gerencia.
4. Si hace falta verificar algo más, use **Devolver para Reconteo** con las líneas y el motivo.
5. Si todo está bien, dele **Aprobar y Aplicar Ajustes** y confirme el aviso.
6. Verifique que la sesión quede **Finalizado**, con el aprobador y la fecha registrados.

Al confirmar se aplican las diferencias autorizadas, el historial se conserva y se libera el cupo. Las líneas sin diferencia también se cierran. Antes de aplicar, el sistema revisa que las existencias no hayan cambiado desde que se tomó el teórico. Si cambiaron, no deja completar la aprobación.

### Si sale un conflicto de existencias

No le vuelva a dar aprobar sin revisar. Lea qué productos indica el mensaje, devuelva esas líneas para reconteo y espere a que Jefatura las revise de nuevo. No aprobamos nada con existencias desactualizadas.

### Cancelación administrativa

Cancelar es para dejar sin efecto una sesión abierta cuando hay una decisión administrativa que lo justifique.

1. Abra la sesión desde **Todos los Conteos**.
2. Llene **Motivo de cancelación** y guarde.
3. Dele **Cancelar** en la parte de arriba de la sesión y confirme.
4. Verifique que quede **Cancelado** y que el motivo aparezca en el historial de mensajes.

Al cancelar, los registros se conservan, se retiran las propuestas pendientes de esa sesión y se libera el cupo sin aplicar diferencias. Esto solo lo puede hacer Gerencia. Una sesión ya finalizada no se cancela para deshacer un ajuste; si hay que corregir algo después, se hace con un procedimiento nuevo y autorizado.

> Ojo: el «Cancelar» de la ventana de reconteo o de agregar producto solo cierra esa ventana. Para cancelar la sesión se usa el botón de arriba y hay que dejar el motivo.

El permiso para aprobar cíclicos y el de aprobar ajustes manuales son distintos. Si una persona tiene que manejar los dos procesos, pidan a administración que revise que tenga ambos accesos.

<!-- pagebreak -->

# 7. Los tres cupos y la preparación de sesiones

El límite es de **tres sesiones abiertas por bodega física**, no de tres productos. Una sesión empieza a ocupar cupo desde que se le asigna un operador por primera vez, y lo sigue ocupando hasta que se cierra o se cancela con autorización.

| Situación | Qué pasa |
| --- | --- |
| Dos sesiones con cupo | Se puede asignar una tercera |
| Tres sesiones con cupo | Se bloquean sesiones nuevas, asignaciones que ocupen cupo y productos adicionales |
| Tres sesiones y una pide reconteo | Se puede recontar, revisar y finalizar lo que ya estaba asignado |
| Cambiar o quitar el operador | El cupo no se libera |
| Una sesión finalizada o cancelada | Libera su cupo |
| Otra bodega tiene espacio | Puede seguir con sus propios conteos |

### Mensaje del límite

> Bloqueo de Inventario: Tienes 3 o más conteos cíclicos pendientes de revisión/cierre. Debes resolver y aplicar las diferencias pendientes antes de iniciar un nuevo ciclo.

Si les sale, busquen las sesiones abiertas en **Todos los Conteos**, fíjense en la bodega y prioricen las que están esperando reconteo, Jefatura o Gerencia. No todas las que ocupan cupo tienen diferencias o están vencidas. Y por favor, no creen otra bodega ni reasignen usuarios para intentar liberar espacio.

### Generación automática

Las configuraciones activas escogen los productos y el operador. La generación separa las sesiones por bodega y crea cada una ya con todas sus líneas, por eso la tercera sí se puede crear completa. Si una bodega está bloqueada se la salta y sigue con las demás. Si esperaban una sesión y no salió, revisen los cupos y consulten a Jefatura. Que se libere un cupo no quiere decir que se genere otra sesión en ese momento.

### Preparación manual por Jefatura

1. Antes de crear una sesión manual vacía, revise que haya menos de dos sesiones ocupando cupo. Si ya hay dos, use la generación automática con sus líneas completas o resuelva primero alguna sesión abierta.
2. Entre a **Todos los Conteos → Nuevo** y llene fecha, configuración, **Bodega física** y **Operador Asignado**. Guarde.
3. Mientras la bodega tenga menos de tres cupos ocupados, use **Agregar Producto**. Llene producto, ubicación de esa bodega, lote o serie si aplica, cantidad física y observaciones, y dele **Agregar**.

El asistente registra esa cantidad como captura de quien lo usa, aunque sea cero. Esa persona va a necesitar otro revisor y otro aprobador para la línea. No usen cantidades inventadas de relleno. Dejar el operador vacío no se salta el límite, porque la primera captura inicia la sesión y ocupa cupo. A una tercera sesión ya asignada no se le pueden agregar productos hasta que se libere espacio.

<!-- pagebreak -->

# 8. Dos días hábiles: vencimientos y alertas

El plazo arranca con la primera diferencia. El sistema no cuenta el día en que se registró (fecha local) y toma **los dos días hábiles siguientes**. No son 48 horas de trabajo.

El calendario es de lunes a viernes, de **07:30 a 17:00**, en hora **America/Costa_Rica**, sin contar los feriados configurados. La regla es la misma si la diferencia se registra de noche, un fin de semana o un feriado.

| Indicador | Cuándo | Qué hay que hacer |
| --- | --- | --- |
| Sin amarillo ni rojo | Antes de las 07:30 del segundo día hábil | Avanzar con captura y revisión; todavía puede estar pendiente |
| Amarillo | De 07:30 a 17:00 del segundo día hábil | Darle prioridad y conseguir el cierre de Gerencia |
| Rojo / Vencido | Después de las 17:00 de ese día | Atenderlo ya y completar lo que falte del flujo |

### Ejemplos en hora de Costa Rica

| Primera diferencia | Alerta amarilla | Vence |
| --- | --- | --- |
| Lunes 21/09/2026, 10:00 | Miércoles 23/09, 07:30 | Miércoles 23/09, 17:00 |
| Viernes 18/09/2026, 18:00 | Martes 22/09, 07:30 | Martes 22/09, 17:00 |
| Sábado 19/09/2026, 10:00 | Martes 22/09, 07:30 | Martes 22/09, 17:00 |
| Lunes 14/09/2026, 10:00; martes 15 feriado | Jueves 17/09, 07:30 | Jueves 17/09, 17:00 |

### Lo que no cambia con un reconteo

- El vencimiento original no se reinicia por editar, devolver o recontar.
- En esta versión no hay prórrogas.
- El visto bueno de Jefatura no detiene el plazo, todavía falta Gerencia.
- Si una diferencia después queda en cero, sigue pendiente hasta el cierre autorizado.
- El rojo no aplica ni cancela nada solo. Simplemente avisa, y se puede seguir resolviendo.

Los colores y filtros se calculan al momento de consultar, entonces refresquen la pantalla para ver la hora actual. Hay un proceso que corre cada cinco minutos y le crea una actividad al responsable de Jefatura por cada sesión vencida, sin duplicarla. La actividad se cierra cuando se resuelve la sesión. Marcar la actividad como hecha no cierra el conteo.

Ya están cargados los 12 feriados oficiales de 2026 en el calendario de conteos. Los de los años siguientes los tiene que cargar administración. El periodo de gracia que se dio al arrancar fue solo para la transición, no es una prórroga para conteos nuevos.

<!-- pagebreak -->

# 9. Ajustes manuales fuera de un cíclico

Estos ajustes van por **Solicitudes de ajuste** y los aprueba Gerencia. No ocupan cupos de cíclicos ni tienen el vencimiento de dos días hábiles. Aquí tampoco se vale aprobarse uno mismo.

### Operador: solicitar desde Inventario físico

1. Abra **Inventario → Operaciones → Ajustes → Inventario físico**.
2. Quite **Cíclicos con Diferencia Pendiente** para ver existencias que no están en ese filtro.
3. Revise producto, ubicación y lote, y fíjese que la línea no tenga una **Sesión cíclica** abierta.
4. Anote la **Cantidad contada** y el **Motivo del ajuste**, explicando bien la diferencia. Guarde.
5. Dele **Solicitar aprobación** en la fila, o seleccione solo las líneas manuales que corresponden y use el botón de arriba.
6. Revise que la solicitud quedó **Por aprobar**. Las existencias todavía no cambian.

La otra forma es entrar a **Inventario → Operaciones → Ajustes → Solicitudes de ajuste**, crear un registro, escoger **Existencia a contar**, anotar **Conteo físico** y **Motivo justificado**, guardar y darle **Solicitar aprobación**. Para un mismo caso usen solo una de las dos vías.

### Gerencia: decidir la solicitud

1. Entre a **Solicitudes de ajuste** y ponga el filtro **Por aprobar**.
2. Revise producto, ubicación, cantidad anterior, conteo, diferencia y justificación. Si tiene permiso de costos, vea también la estimación.
3. Si está bien y usted no participó en el conteo, dele **Aprobar y aplicar** y confirme. Tiene que quedar **Aprobado y aplicado**.
4. Si no procede, escriba el motivo en **Motivo de rechazo / observación de Gerencia** y dele **Rechazar**. El ajuste no se aplica.

El costo que se ve antes de aplicar es solo una estimación. Para la trazabilidad real, revisen los movimientos y el historial del registro ya aprobado.

### Casos a los que hay que ponerles atención

**Las existencias cambiaron:** Gerencia rechaza la solicitud pendiente y se registra un conteo nuevo. **Ya hay una solicitud pendiente:** revisen esa, no dupliquen el trámite. **No se sabe quién capturó:** vuelva a registrar la cantidad con el usuario de la persona que contó.

> Ojo: si la existencia pertenece a un cíclico abierto, se resuelve desde su sesión. No se puede usar una solicitud manual para brincarse a Jefatura o el cierre del cíclico, y los botones masivos tampoco se lo saltan.

<!-- pagebreak -->

# 10. Configuración, reportes e historial

### Jefatura: reglas de generación

**Ruta:** Inventario → Operaciones → Conteos Cíclicos → **Configuraciones**.

Antes de tocar una configuración, revísela bien. **Activo** la pone a participar en la generación. **Operador Asignado** define quién recibe la tarea, y asignarlo ocupa cupo desde que se crea la sesión. **Productos por Día**, **Método de Selección**, ubicaciones y categorías limitan qué se escoge. **Días Mínimos entre Conteos** controla cada cuánto se repite un producto.

No cambien criterios para salir de un bloqueo de cupos; primero se cierra lo pendiente. Las sesiones nuevas traen ubicaciones de una sola bodega, aunque la configuración abarque varias.

### Administración de Inventario: responsable y calendario

En **Inventario → Configuración → Almacenes**, abra la bodega y busque **Control de conteos cíclicos**. Esta parte ocupa permisos de administración de Inventario.

| Campo | Cómo está en Regalarte al 16/09/2026 |
| --- | --- |
| Responsable de conteos cíclicos | admin2@regalartecr.com |
| Calendario de conteos y feriados | Conteos cíclicos Regalarte — Costa Rica |
| Zona y jornada | America/Costa_Rica; lunes a viernes, 07:30 a 17:00 |
| Feriados cargados | Los 12 días oficiales de 2026 |

Si hay que cambiar al responsable, escojan un usuario activo, con permiso de Jefatura y acceso a la compañía de esa bodega. Cambiar el campo no le da esos permisos a la persona. Los feriados de cada año se cargan en los días no laborables generales de este calendario; no los confundan con las ausencias de cada persona.

### Consultar la auditoría

Desde una línea use **Detalle y auditoría**, o **Revisar cíclico** si está en Inventario físico. Ahí sale la primera diferencia, el vencimiento, quién participó, la revisión y la aplicación, con todas las capturas y motivos. Todo eso queda como historial y no se corrige borrando eventos.

En la sesión, la sección **Auditoría** y el historial de mensajes muestran el envío, la aprobación y las decisiones. En **Todos los Conteos** pueden buscar por referencia y ver sesiones finalizadas o canceladas; si no aparece, quiten los filtros de fecha o estado.

### Reportes

En una sesión, entren a **Imprimir** y ahí están **Discrepancias de Conteo (PDF)** y **Discrepancias de Conteo (Excel)**. Jefatura además tiene **Conteo Valorizado (PDF)** y **Conteo Valorizado (Excel)**. Los reportes son de apoyo: bajarlos no aprueba ni aplica nada.

<!-- pagebreak -->

# 11. Mensajes y solución de problemas

| Lo que les sale | Qué hacer |
| --- | --- |
| «Tienes 3 o más conteos cíclicos pendientes…» | Revisar las sesiones abiertas de esa bodega y terminar reconteos, revisión y cierre. Cancelar con motivo solo lo hace Gerencia |
| Mis Conteos de Hoy está vacío | Buscar en Todos los Conteos. Puede ser de otro día o ya estar en revisión; revisar también el operador asignado |
| Inventario físico no muestra un conteo nuevo | Quitar Cíclicos con Diferencia Pendiente y los demás filtros. Revisar producto, ubicación, compañía y permisos |
| «Registre todas las cantidades…» o línea Pendiente | Capturar las líneas que faltan. Si es un cero que no quedó registrado, usar Marcar Contado |
| «Indique la justificación de Jefatura…» | Escribir y guardar la Justificación de Jefatura antes del Visto bueno |
| «Quien contó o recontó no puede revisar ni aplicar…» | Pedirle a otra persona independiente con el permiso que lo haga; cambiar de rol no borra la participación |
| «Falta el visto bueno de Jefatura» | Revisar todas las líneas, también las de diferencia cero y las devueltas para reconteo |
| «El stock cambió después de capturar el teórico…» | Devolver esas líneas para reconteo y repetir la revisión; no aplicar por otro botón |
| «Esta existencia pertenece a un conteo cíclico abierto…» | Abrir la sesión y terminar el flujo del cíclico, sin solicitud manual aparte |
| «Ya existe una solicitud por aprobar…» | Ir a Solicitudes de ajuste y resolver la que está pendiente antes de crear otra |
| «Registre nuevamente la cantidad para identificar al capturador» | Registrar y guardar la cantidad con el usuario real de quien contó, y volver a solicitar aprobación |
| Línea en rojo después de recontar | El plazo original sigue igual. Terminar revisión y aprobación final; el reconteo no da más tiempo |
| Diferencia cero, pero sigue en pendientes | Hubo una diferencia antes que no se cerró. Completar el flujo hasta Finalizado o una cancelación autorizada |
| «Otro proceso está revisando estas existencias…» | Refrescar y volver a intentar cuando termine la otra operación. Si se repite, me avisan |
| No aparece un botón o no deja editar | Revisar el perfil y el estado de la sesión. Si está en revisión, hay que devolverla para cambiar cantidades |

### Qué mandarme cuando ocupen ayuda

Para poder ayudarles rápido, mándenme la **referencia de la sesión o de la solicitud**, la bodega, el producto, la ubicación o lote, el usuario, qué estaban intentando hacer y el mensaje completo. Si mandan pantallazo, que se vea el estado y los filtros. Y si algo sale raro, antes de repetir la operación revisen cómo quedó guardado.

<!-- pagebreak -->

# 12. Ejemplo completo y rutina diaria

### Ejemplo: faltan dos unidades

**El caso:** una sesión de Regalarte tiene un producto con teórico de 20 unidades. El operador cuenta 18 el lunes 21/09/2026 a las 10:00. Durante el ejemplo no hay otros movimientos de ese producto.

1. **Operador:** anota 18, pone sus observaciones y guarda. Odoo registra diferencia -2 con vencimiento el miércoles 23/09/2026 a las 17:00.
2. **Operador:** termina las demás líneas y le da **Enviar a Jefatura**.
3. **Jefatura:** revisa. Si acepta el resultado, deja su justificación y le da **Visto bueno**. Si quiere confirmarlo, pide reconteo con motivo.
4. **Si hubo reconteo:** el operador registra el resultado nuevo y vuelve a enviar. El vencimiento sigue siendo el miércoles a las 17:00, y Jefatura revisa otra vez.
5. **Jefatura:** con todas las líneas aprobadas técnicamente, le da **Enviar a Gerencia**.
6. **Gerencia (independiente):** revisa y le da **Aprobar y Aplicar Ajustes**. Si el conteo aceptado sigue en 18, se aplica la diferencia de -2, la sesión queda **Finalizado** y se libera el cupo.

Si el reconteo hubiera dado 20, igual hay que completar el cierre; simplemente no habría nada físico que ajustar en esa línea. Y si las existencias hubieran cambiado, el sistema obliga a recontar antes de aprobar.

### Rutina del operador

- Ver las tareas de hoy y si hay reconteos de días anteriores.
- Revisar producto, ubicación y lote antes de capturar.
- Anotar lo real, aunque sea cero, con observaciones que sirvan.
- Confirmar que el envío a Jefatura sí quedó hecho.

### Rutina de Jefatura

- Revisar **Revisión de Jefatura** y **Conteos Vencidos**.
- Priorizar por **Vence el**; los amarillos y rojos van primero.
- En cada línea, decidir con motivo: visto bueno o reconteo.
- Mandar a Gerencia las sesiones completas y estar pendiente de los cupos.

### Rutina de Gerencia

- Revisar **Pendientes de Gerencia** y las solicitudes manuales **Por aprobar**.
- Confirmar que no participó en la captura.
- Aplicar lo autorizado, devolver lo que ocupa reconteo o rechazar con motivo la solicitud manual.
- Verificar el estado final. Cerrar la actividad o bajar un reporte no reemplaza la aprobación.

Cualquier duda con el proceso me escriben. Quedo atento. Saludos, **Diego Mora**

**Referencia del calendario 2026:** MTSS, CARTA-MTSS-DAJ-AER-1076-2025, disponible en https://www.mtss.go.cr/temas-laborales/feriados/feriados_calendario_2026.pdf. Este manual describe los controles y nombres de pantalla de la versión vigente al 16/09/2026; lo que cada quien puede hacer depende de sus permisos.
