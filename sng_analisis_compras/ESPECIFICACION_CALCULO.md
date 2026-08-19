# Análisis de Compras — Especificación del cálculo

**Módulo:** `sng_analisis_compras` · **Versión:** 18.0.1.5.0 · **Fecha:** 28 de julio de 2026

Este documento explica, paso a paso y con ejemplos, cómo el reporte *Análisis de
Compras* (menú Compras / Ventas / Inventario → Análisis de Compras) calcula cada
columna, en especial el **sugerido de compra**.

---

## 1. Idea general

El reporte responde una pregunta: **¿cuánto debo comprar de cada producto para
cubrir X meses de venta, considerando lo que ya tengo y lo que ya pedí?**

La fórmula central es:

```
Sugerido de compra        = Promedio de venta mensual × (Meses de cobertura + Plazo de llegada en meses)
Sugerido menos existencias = Sugerido de compra − Inventario actual − En órdenes de compra
```

Si "Sugerido menos existencias" es positivo, esa es la cantidad que falta
comprar. Si es negativo o cero, no hace falta comprar.

---

## 2. Parámetros que ingresa el usuario

| Parámetro | Qué controla | Valor típico |
|---|---|---|
| **Fecha desde / Fecha hasta** | El rango de ventas que se usa para calcular el promedio mensual. | El mes pasado, o los últimos 3 meses |
| **Meses de cobertura** | Cuántos meses de venta futura debe cubrir la compra. Acepta decimales (1.5 = mes y medio). | 1 – 3 |
| **Incluir tiempo de llegada** | Si está marcado (viene marcado por defecto), suma al período a cubrir el tiempo que tarda el proveedor en entregar. Ver sección 6. | Marcado |
| **Incluir no entregado en el promedio** | Si está marcado, la demanda no atendida (pedido y no entregado por falta de stock) se suma a las ventas para calcular el promedio. Desmarcado (por defecto), la columna "No entregado" es solo informativa. Ver sección 6b. | Desmarcado |
| **Compañías / Grupo de almacenes / Almacenes / Bodegas** | Limitan el alcance del reporte. Vacío = todo. Ver "Ventas de todos los almacenes" para qué limita exactamente el filtro de almacenes. | Según necesidad |
| **Ventas de todos los almacenes** | Solo aparece al filtrar por grupo/almacenes. Marcado (por defecto): el filtro de almacenes limita únicamente el inventario y las compras en camino; las ventas se toman de todos los almacenes. Desmarcado: el filtro también limita las ventas. | Marcado |
| **Productos / Código / Proveedores** | Limitan los productos del reporte. Vacío = todos los productos comprables y almacenables. | Según necesidad |
| **Solo con ventas** | Oculta productos sin ventas en el rango. | Desmarcado |
| **Umbral desviación estándar / Meses mínimos** | Configuración de la marca "venta atípica" (sección 8). | 2.0 / 2 |

---

## 3. De dónde salen las ventas

- Se cuentan **solo facturas de cliente contabilizadas** (validadas). Los
  pedidos de venta sin facturar y las facturas en borrador **no** cuentan.
- Las **notas de crédito restan**: si se facturaron 10 y se devolvieron 2, la
  venta neta es 8.
- La fecha que manda es la **fecha de la factura**.
- Con el check **"Ventas de todos los almacenes"** marcado (el valor por
  defecto), el filtro de grupo/almacenes **no** se aplica a las ventas: se
  cuentan las de toda la empresa, y solo el inventario y las compras en camino
  se limitan a los almacenes elegidos.
- Si se desmarca, cada línea de factura se atribuye al almacén siguiendo la
  cadena: factura → pedido de venta → entrega de bodega. Una factura manual sin
  pedido ni entrega no tiene almacén identificable y queda fuera del conteo.
- El filtro de **Bodegas** sí aplica siempre a las ventas (usa la bodega de
  venta del pedido/entrega, con respaldo en la configurada en el cliente).

### Columnas de historial ("Hace 6m" … "Hace 1m")

Muestran la venta neta de cada uno de los últimos 6 meses calendario.
**"Hace 1m" es el mes de la "Fecha hasta"** y se muestra el mes completo.
En el Excel exportado las columnas llevan el nombre real del mes (ej. "Junio 2026").
"Total 6m" es la suma de las seis.

Nota: el historial de 6 meses es informativo; el promedio para el sugerido se
calcula **solo con el rango Fecha desde–Fecha hasta** (sección 4).

---

## 4. Promedio de venta mensual ("Prom/mes")

```
Promedio mensual = Venta neta del rango ÷ Meses del rango
Meses del rango  = días del rango ÷ 30
```

Ejemplo: rango del 1 al 30 de junio (30 días = 1.0 mes) con 90 unidades
facturadas → promedio de 90/mes. Un rango de 45 días cuenta como 1.5 meses.

**Ajuste por inicio de operaciones:** el sistema tiene registrada la fecha en
que se empezó a facturar en Odoo (parámetro configurable, hoy **1 de abril de
2026**). Si el rango elegido empieza antes de esa fecha, el promedio se calcula
solo desde esa fecha, para que los meses sin datos no bajen artificialmente el
promedio. Ejemplo: rango enero–junio 2026 → el promedio divide entre 3 meses
(abril–junio), no entre 6.

---

## 5. Inventario y compras en camino

- **Inv. Actual:** existencia física en bodegas internas (de los almacenes o
  bodegas filtrados; si no se filtró, todas).
- **En OC (órdenes de compra):** cantidad **pendiente de recibir** en órdenes de
  compra confirmadas: cantidad pedida menos cantidad ya recibida. Una OC en
  borrador o cancelada no cuenta.

Ambas se restan del sugerido: lo que ya tengo y lo que ya viene en camino no
hay que volver a comprarlo.

---

## 6. Plazo de llegada del proveedor (columna "Plazo llegada (meses)")

Cada producto tiene en su pestaña **Compra** una lista de proveedores; el
sistema toma el **proveedor principal** (el primero de la lista) y lee su
**Plazo de entrega** en días, cargado según el maestro de proveedores:

| Origen del proveedor | Plazo de entrega | En meses |
|---|---|---|
| Costa Rica | 30 días | 1.0 |
| Estados Unidos | 90 días | 3.0 |
| China | 180 días | 6.0 |

**Por qué se suma a la cobertura:** cuando se hace un pedido a un proveedor que
tarda 6 meses, durante esos 6 meses de viaje se sigue vendiendo. La compra debe
alcanzar para el **tránsito + la cobertura deseada**. Por eso:

```
Sugerido = Promedio mensual × (Meses de cobertura + Plazo en meses)
```

- Si el producto **no tiene proveedor** asignado, o su plazo es 0, el plazo es
  0 y el sugerido queda igual que antes (solo cobertura).
- Si se **desmarca** "Incluir tiempo de llegada" en el wizard, todos los plazos
  se tratan como 0 (útil para comparar con el cálculo anterior).
- El plazo mostrado se redondea a 1 decimal en pantalla, pero el cálculo usa el
  valor exacto (días ÷ 30).

---

## 6b. Demanda no atendida (columna "No entregado")

Cuando un cliente pide 100 y solo se le entregan 60 porque no había stock, la
política comercial es facturar lo entregado y no generar órdenes parciales: los
40 restantes son **venta perdida** y no aparecen en ninguna factura, por lo que
el promedio de ventas los ignora y el sugerido queda corto justo en los
productos con más faltantes.

La columna "No entregado" mide esa demanda perdida:

```
No entregado = cantidad pedida − cantidad entregada − cantidad devuelta
```

por línea de pedido **confirmado** cuya fecha de pedido cae en el rango del
análisis, sin entregas pendientes, y nunca menor que cero.

- **Las devoluciones no cuentan como faltante**: si se entregaron 10 y el
  cliente devolvió 2, la entrega del pedido queda en 8, pero esas 2 piezas sí
  salieron de bodega — no fue un faltante de stock. Por eso se descuentan.
  (La nota de crédito de la devolución ya resta esas 2 de la venta facturada;
  contarlas también como "no entregado" las castigaría doble.)
- Pedidos cancelados no cuentan.
- La demanda que nunca se registró (el vendedor no metió el pedido porque vio
  que no había stock) no deja rastro y no puede medirse.

**El check "Incluir no entregado en el promedio"** (desmarcado por defecto)
controla si esta cantidad entra al cálculo:

```
Con el check:  Promedio mensual = (Venta facturada + No entregado) ÷ meses
```

y ese promedio corregido alimenta el sugerido y los meses de inventario. La
marca de "venta atípica" siempre se evalúa sobre lo facturado, para comparar
contra la historia con la misma vara.

Recomendación: mantenerlo desmarcado un tiempo y observar la columna; cuando
compras valide que los números reflejan faltantes reales, activarlo.

---

## 7. Ejemplo completo

Producto importado de China, corriendo el reporte con junio 2026 y cobertura 1:

| Dato | Valor |
|---|---|
| Venta neta de junio | 300 unidades |
| Meses del rango | 1.0 |
| **Promedio mensual** | **300** |
| Plazo del proveedor | 180 días → 6.0 meses |
| Meses de cobertura | 1.0 |
| Inventario actual | 800 |
| En órdenes de compra | 400 |

```
Sugerido            = 300 × (1.0 + 6.0) = 2,100
Sugerido − existencias = 2,100 − 800 − 400 = 900   ← cantidad a comprar
```

El mismo producto compradole a un proveedor local (plazo 1 mes) sugeriría
300 × (1+1) = 600, y con inventario 800 no habría que comprar nada.

---

## 8. Columnas de diagnóstico

### Meses Inv. (meses de inventario)

```
Meses de inventario = Inventario actual ÷ Promedio mensual
```

Cuántos meses dura el stock actual al ritmo de venta del rango. Colores:

- 🔴 **Rojo** — más de 12 meses: sobrestock.
- 🟠 **Naranja** — hay inventario pero no hubo ventas en el rango: producto muerto.
- 🟢 **Verde** — 3 meses o menos: stock bajo, atención.

Ojo: este indicador **no** incluye el plazo de llegada; es solo una foto del
stock vs. la venta. Un producto de China con 5 meses de inventario aparece sin
color, pero como tarda 6 meses en reponerse, el sugerido sí pedirá compra.

### Venta atípica

Marca los productos cuyo promedio del rango es inusualmente alto comparado con
su propia historia (desde inicio de operaciones hasta la "Fecha desde"). Se
calcula con desviación estándar: si el promedio actual supera el promedio
histórico + 2 desviaciones (umbral configurable), se marca "Sí". Sirve para no
comprar de más por un pico puntual (una venta grande única, una feria). Se
necesitan al menos 2 meses de historia; con menos, nunca se marca.

**La marca es informativa: el sugerido no se ajusta solo.** Ante una venta
atípica, el comprador decide si confía en el promedio o lo modera.

---

## 9. Orden y totales

- Las filas se ordenan por "Sugerido menos existencias" de mayor a menor: lo
  más urgente de comprar aparece primero.
- La fila TOTAL del Excel suma las columnas de cantidades. "Meses Inv.",
  "Plazo llegada" y "Venta atípica" no se suman porque un total no tiene sentido.
- La columna Costo solo la ven los usuarios con el permiso de ver costos.

---

## 10. Preguntas frecuentes

**¿Por qué el sugerido de los productos de China es tan alto?**
Porque cubre 6 meses de tránsito además de la cobertura pedida. Es el
comportamiento esperado: pedir hoy lo que se venderá mientras llega el pedido.

**¿Por qué un producto no muestra plazo de llegada?**
No tiene proveedor asignado en la pestaña Compra, o su proveedor tiene plazo de
entrega 0. Asignar el proveedor con su plazo corrige el cálculo.

**¿Puedo ver el cálculo como era antes?**
Sí: desmarcar "Incluir tiempo de llegada" en el wizard.

**¿El reporte cambia algo en el sistema?**
No. Es solo lectura: no crea órdenes de compra ni modifica inventario.

**¿Qué pasa si el rango incluye meses anteriores a abril 2026?**
Se ignoran para el promedio (no había facturación en Odoo); solo se promedia
desde el inicio de operaciones.

---

## 11. Modelo de inventario ajustado (v1.5.0)

Desde la versión 1.5.0 el reporte incluye una segunda familia de columnas,
réplica del análisis de compras de Excel de julio 2026 ("Análisis Compras
Inventario Odoo"). **No reemplaza al sugerido clásico** (secciones 1–6): ambas
convivencias permiten comparar. La diferencia de fondo: el modelo ajustado
pesa más la venta reciente y agrega un colchón estadístico (stock de
seguridad) según qué tan variable es la demanda.

### 11.1 Demanda mensual ponderada

En vez del promedio simple del rango, toma los **últimos 4 meses** del
historial (siendo "mes 1" el mes de la Fecha hasta) con pesos decrecientes:

```
Demanda ponderada = mes 1 × 0.40 + mes 2 × 0.30 + mes 3 × 0.20 + mes 4 × 0.10
```

Dos ajustes automáticos:

- **Mes parcial:** si la Fecha hasta no cierra el mes (ej. corte al día 21),
  la venta de ese mes se extrapola a 30 días (venta ÷ 21 × 30) antes de
  ponderar. *(Mejora sobre el Excel original, que extrapolaba solo en la
  desviación y ponderaba el mes incompleto tal cual, subestimando la demanda.)*
  Nota: la extrapolación asume que la Fecha hasta es el corte real de las
  ventas (el uso normal: correr el reporte con fecha de hoy). Con una Fecha
  hasta antigua sobre una base que ya tiene ventas posteriores, el mes se
  cuenta completo y además se extrapola, inflando la demanda.
- **Meses pre-operaciones:** los meses anteriores al inicio de operaciones
  (abril 2026) se excluyen y los pesos restantes se renormalizan para seguir
  sumando 1. *(El Excel los incluía en cero, arrastrando la demanda hacia abajo.)*

### 11.2 Desviación y coeficiente de variación

```
Desv. demanda   = desviación estándar poblacional de esos mismos meses (mes parcial extrapolado)
Coef. variación = Desv. demanda ÷ Demanda ponderada        (0 si la demanda es 0)
```

Un coeficiente sobre el **umbral (0.5)** marca la demanda como inestable: el
promedio es poco confiable y conviene revisar antes de comprar.

### 11.3 Stock de seguridad, punto de reorden y stock objetivo

```
Stock disponible        = Inventario actual + En órdenes de compra
Stock proyectado        = Stock disponible − Demanda ponderada × Plazo llegada (meses)
Stock seguridad         = Z × Desv. demanda × √Plazo llegada          (Z = 1.65 ≈ 95% servicio)
Punto de reorden        = Demanda ponderada × Plazo + Stock seguridad
Stock objetivo          = Demanda ponderada × (Plazo + Cobertura) + Stock seguridad
Necesidad neta          = Stock objetivo − Stock disponible
Cobertura (meses)       = Stock disponible ÷ Demanda ponderada
Exceso unidades         = max(0, Stock disponible − Stock objetivo)
```

Con "Incluir tiempo de llegada" desmarcado el plazo es 0: el stock de
seguridad y el punto de reorden quedan en 0 y el objetivo cubre solo la
cobertura pedida.

### 11.4 Compra sugerida ajustada y MOQ

```
Compra sugerida ajustada = Necesidad neta redondeada HACIA ARRIBA al múltiplo del MOQ
                           (0 si la necesidad es negativa o cero)
```

El **MOQ** es la *Cantidad mínima* de la línea del proveedor principal en la
pestaña Compra del producto (mínimo 1 si no está configurada). *(Mejora sobre
el Excel, que usaba un MOQ global de 1 para todos los productos.)*

### 11.5 Clase ABC

Por **venta valorizada** (Total 6m × precio actual) acumulada de mayor a menor:

- **A** — productos que acumulan hasta el 80% de la venta valorizada.
- **B** — hasta el 95%.
- **C** — el resto (incluye productos sin venta).

El producto de mayor venta siempre es A, aunque por sí solo supere el 80%
(caso de reportes con pocos productos filtrados).

### 11.6 Riesgo / Estado y acción recomendada

Cascada en orden de prioridad (la primera condición que se cumple gana):

| Estado | Condición | Acción recomendada |
|---|---|---|
| **DATOS INCOMPLETOS** | costo ≤ 0 o precio ≤ 0 | Corregir costo, precio, proveedor, plazo y MOQ |
| **QUIEBRE PROYECTADO** | stock proyectado < 0, o disponible = 0 (con demanda ≥ 0) | Prioridad alta: emitir RFQ/OC y revisar alternativa local |
| **REORDENAR** | disponible ≤ punto de reorden | Comprar cantidad sugerida ajustada |
| **EXCESO** | disponible > stock objetivo × factor de exceso (1.5) | Detener compra y activar plan de rotación |
| **DEMANDA INESTABLE** | coef. variación > umbral (0.5) | Revisar venta atípica y ajustar stock de seguridad |
| **SALUDABLE** | ninguna de las anteriores | Mantener monitoreo |

Caso especial: disponible en 0 con demanda ponderada **negativa** (más
devoluciones que ventas) no es quiebre; cae a las reglas siguientes.

Estas reglas se validaron contra el Excel original: 666 de 666 filas dan el
mismo estado.

Ojo: sin filtros, el reporte incluye todo el catálogo comprable/almacenable y
los productos abandonados (costo 0 y precio 0, sin ventas) salen como DATOS
INCOMPLETOS en masa. Para un análisis de compras operativo, marcar **"Solo
con ventas"** o filtrar por proveedor.

### 11.7 Parámetros del wizard (grupo "Modelo de inventario ajustado")

| Parámetro | Default | Uso |
|---|---|---|
| Factor de servicio (Z) | 1.65 | Multiplica la desviación en el stock de seguridad (≈95% de nivel de servicio) |
| Umbral coef. variación | 0.5 | Sobre este valor la demanda se marca inestable |
| Factor de exceso | 1.5 | El estado Exceso exige disponible > objetivo × factor |

### 11.8 Diferencias documentadas vs. el Excel original

1. **Mes parcial:** se extrapola a 30 días también en la demanda ponderada
   (el Excel solo lo hacía en la desviación) — sección 11.1.
2. **Meses pre-operaciones:** se excluyen con renormalización de pesos — 11.1.
3. **MOQ por producto** (cantidad mínima del proveedor) en vez de MOQ global 1 — 11.4.
4. Columnas de costo (margen, valor inventario, valor exceso) visibles solo
   con el permiso de ver costos, igual que la columna Costo.

Pendientes conocidos (señalados también en el propio Excel): descontar el
stock **reservado** del disponible y usar la **fecha ETA real** de cada OC en
vez del plazo genérico del proveedor.
