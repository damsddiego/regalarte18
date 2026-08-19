# Manual de usuario — Entregas de Regalías a Clientes

Cómo registrar la entrega de productos de obsequio: rebajo de inventario,
asiento contable y comprobante de entrega. (Módulo `sng_entrega_regalias`, Odoo 18.)

## 1. ¿Qué es una regalía?

Una **regalía** es la entrega de uno o varios productos a un cliente **sin cobro**
(obsequio, cortesía, promoción). El documento deja el registro completo en un solo
paso al validarlo:

- **Inventario**: rebaja el stock del almacén elegido mediante una transferencia
  de salida (referencia `REG-OUT/…`).
- **Contabilidad**: publica un asiento al **costo promedio** de cada producto —
  débito a la cuenta de gasto de regalías y crédito a la cuenta contrapartida de
  inventario. No lleva IVA.
- **Comprobante**: genera un PDF de entrega con espacio para firmas, pensado para
  que el cliente firme de recibido.

Se accede desde el menú principal **Regalías → Entregas de Regalías**.

## 2. Roles y permisos

Se asignan a cada empleado en **Ajustes → Usuarios** (sección «Inventario»):

| Grupo | Qué puede hacer |
|---|---|
| **Usuario regalías** | Crear y editar borradores, cancelarlos e imprimir el comprobante. No ve los costos. |
| **Responsable regalías** | Todo lo anterior, y además: **validar** las entregas (rebaja stock y contabiliza), ver costos y totales, configurar las cuentas contables y eliminar borradores. |

## 3. Configuración inicial (una sola vez)

La hace un **Responsable regalías** antes de validar la primera entrega, en
**Ajustes → Contabilidad**, bloque **«Regalías a clientes»**:

| Campo | Obligatorio | Para qué sirve |
|---|---|---|
| **Cuenta de gasto** | Sí | Se debita con el costo de los productos regalados (p. ej. gasto de mercadeo u obsequios). |
| **Cuenta contrapartida** | Sí | Se acredita por el mismo total; normalmente la cuenta de inventario. |
| **Diario** | No | Diario misceláneo del asiento. Si queda vacío, se usa el primer diario misceláneo de la compañía. |

> **Nota**: si las cuentas no están configuradas, el sistema no deja validar y
> muestra un mensaje indicando exactamente qué falta. Los borradores sí se pueden
> crear sin configuración.

## 4. Crear una regalía

1. Entrá a **Regalías → Entregas de Regalías** y hacé clic en **Nuevo**.
2. Elegí el **Cliente** que recibe el obsequio.
3. Elegí el **Almacén** del que sale la mercadería. La **Fecha** se propone con el
   día de hoy (podés cambiarla; es la fecha del asiento).
4. En la pestaña **Productos**, agregá una línea por cada producto con su
   **Cantidad**. Solo aparecen productos almacenables (con inventario).
5. Si querés, anotá el motivo en la pestaña **Notas** (aparece también en el
   comprobante impreso).
6. Guardá. El documento recibe un número `REG/2026/0001` y queda en estado
   **Borrador**.

Mientras esté en borrador podés editarlo libremente: cambiar cliente, almacén,
líneas o eliminarlo.

## 5. Validar la entrega

Solo el **Responsable regalías** ve el botón **Validar**. Al confirmarlo, en un
solo paso:

1. Se crea y valida la **transferencia de salida** (`REG-OUT/…`) del almacén
   elegido hacia el cliente: el stock queda rebajado de inmediato.
2. Se publica el **asiento contable**: una línea de débito por producto (costo
   promedio × cantidad, con el cliente como tercero) contra un solo crédito a la
   cuenta contrapartida. La referencia del asiento es el número de la regalía.
3. El documento pasa a **Entregado** y queda **bloqueado**: ya no se puede editar
   ni eliminar.

Arriba del formulario aparecen dos accesos directos: **Transferencia** (el
movimiento de inventario) y **Asiento** (visible solo para el Responsable).

> **Nota**: el costo se **congela al momento de validar** con el costo promedio
> vigente del producto. Si el costo del producto cambia después, la regalía ya
> entregada no se ve afectada.

## 6. Imprimir el comprobante

Desde el documento, menú **Imprimir → Comprobante de Entrega de Regalía**. El PDF
incluye:

- Logo y datos de la compañía, número de documento y fecha.
- Datos del cliente (nombre, identificación, dirección) y almacén de origen.
- La lista de productos con código, cantidad y unidad — **sin costos ni precios**:
  es un comprobante de entrega para el cliente.
- Las notas del documento y dos espacios de firma: *Entregado por* y *Recibido por*.

Se puede imprimir en cualquier estado, pero lo usual es imprimirlo ya validado
para que el cliente firme al recibir.

## 7. Cancelar o reversar

### Si todavía está en borrador

Usá el botón **Cancelar**. No pasa nada en inventario ni contabilidad. Un
documento cancelado se puede reactivar con **Volver a borrador**.

### Si ya fue entregado

Los documentos entregados no se pueden modificar. Si una entrega se registró por
error, la corrección la hace el área contable en dos pasos:

1. **Contabilidad**: abrir el asiento (botón **Asiento**) y usar **Reversar asiento**.
2. **Inventario**: abrir la transferencia (botón **Transferencia**) y crear una
   **Devolución** para que la mercadería regrese al almacén.

> **Importante**: hacé siempre los dos pasos. Si solo se reversa el asiento, el
> inventario queda rebajado; si solo se devuelve la mercadería, el gasto queda
> registrado.

## 8. Mensajes frecuentes

| Mensaje | Qué significa / qué hacer |
|---|---|
| «Configura primero las regalías en Ajustes de Contabilidad…» | Faltan la cuenta de gasto o la contrapartida. Un Responsable debe completarlas (sección 3). |
| «Solo el Responsable de regalías puede validar entregas.» | Tu usuario tiene el grupo Usuario regalías. Pedile a un Responsable que valide, o al administrador que te asigne el grupo. |
| «La regalía debe tener al menos una línea de producto.» / «…cantidad mayor que cero.» | Agregá productos y verificá que ninguna línea tenga cantidad 0. |
| «Solo se pueden regalar productos almacenables…» | Alguna línea tiene un servicio o consumible. Las regalías solo aplican a productos con inventario. |
| «No puedes modificar una regalía ya entregada.» | El documento está bloqueado. Si hay que corregirlo, seguí el procedimiento de reversa (sección 7). |
